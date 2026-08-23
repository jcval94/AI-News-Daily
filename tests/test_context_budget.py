from __future__ import annotations

import json
import unittest

from pipeline.context_budget import (
    build_context_budget,
    build_selected_news_index,
    optimize_agent_state,
)


def _item(news_id: str, index: int, raw: str) -> dict:
    return {
        "news_id": news_id,
        "source_file": "2026-08-21.txt",
        "source_locator": f"2026-08-21.txt#item-{index}",
        "item_index": index,
        "title": f"Story {index}",
        "date": "2026-08-21",
        "date_origin": "field",
        "source": "Primary",
        "url": f"https://example.com/{index}",
        "url_quality": "article",
        "category": "research",
        "summary": f"Summary {index}",
        "why_it_matters": f"Why {index}",
        "raw_content": raw,
    }


class ContextBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.discovery = {
            "schema_version": 1,
            "items": [
                _item("2026-08-21:1", 1, "RAW ONE"),
                _item("2026-08-21:2", 2, "RAW TWO"),
                _item("2026-08-21:3", 3, "RAW THREE"),
            ],
        }
        self.selection = {
            "items": [
                {
                    **self.discovery["items"][0],
                    "selection_reason": "anchor",
                },
                {
                    **self.discovery["items"][2],
                    "selection_reason": "contrast",
                },
            ],
            "discarded_duplicates": [],
            "selection_notes": [],
        }

    def test_selected_index_deduplicates_bodies_without_dropping_discovery(self) -> None:
        index = build_selected_news_index(self.selection)
        self.assertEqual(len(index["items"]), 2)
        self.assertEqual(index["items"][0]["selected_news_index"], 1)
        self.assertNotIn("raw_content", index["items"][0])
        self.assertNotIn("summary", index["items"][0])
        self.assertEqual(index["items"][0]["selection_reason"], "anchor")

        discovery_json = json.dumps(self.discovery, ensure_ascii=False)
        budget = build_context_budget(self.selection, discovery_json)
        self.assertEqual(json.loads(budget["news_text_json"]), self.discovery)
        self.assertEqual(budget["manifest"]["discovery_item_count"], 3)
        self.assertEqual(budget["manifest"]["discovery_item_count_after"], 3)
        self.assertEqual(budget["manifest"]["removed_source_items"], 0)
        self.assertTrue(budget["manifest"]["all_discovery_sources_preserved"])
        self.assertEqual(budget["manifest"]["selected_exact_source_matches"], 2)

    def test_refiner_drops_only_duplicate_plain_script_state(self) -> None:
        state = {
            "draft_script": "plain narration",
            "sectioned_draft_script": "<!--SECTION:opening-->plain narration",
            "selected_news": json.dumps(self.selection, ensure_ascii=False),
            "news_text": json.dumps(self.discovery, ensure_ascii=False),
            "episode_plan": json.dumps({"beats": []}, ensure_ascii=False),
            "review": json.dumps({"problems": []}, ensure_ascii=False),
        }
        optimized, summary = optimize_agent_state("script_refiner", state)
        self.assertTrue(summary["applied"])
        self.assertTrue(summary["source_integrity_verified"])
        self.assertNotIn("draft_script", optimized)
        self.assertIn("sectioned_draft_script", optimized)
        self.assertEqual(json.loads(optimized["news_text"]), self.discovery)
        self.assertNotIn("raw_content", json.loads(optimized["selected_news"])["items"][0])

    def test_integrity_mismatch_fails_open(self) -> None:
        broken = json.loads(json.dumps(self.discovery))
        broken["items"][0]["raw_content"] = "CHANGED"
        state = {
            "selected_news": json.dumps(self.selection, ensure_ascii=False),
            "news_text": json.dumps(broken, ensure_ascii=False),
        }
        optimized, summary = optimize_agent_state("script_critic", state)
        self.assertIs(optimized, state)
        self.assertFalse(summary["applied"])
        self.assertIn("fail_open_reason", summary)


if __name__ == "__main__":
    unittest.main()
