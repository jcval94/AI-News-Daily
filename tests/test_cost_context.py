from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from pipeline.run_cost_optimized import compact_agent_state


class CostContextTests(unittest.TestCase):
    def _state(self) -> dict[str, str]:
        items = []
        for index in range(1, 5):
            items.append(
                {
                    "news_id": f"2026-08-21:{index}",
                    "source_file": "2026-08-21.txt",
                    "source_locator": f"2026-08-21.txt#item-{index}",
                    "item_index": index,
                    "title": f"Story {index}",
                    "date": "2026-08-21",
                    "source": "Example",
                    "url": f"https://example.com/{index}",
                    "url_quality": "article",
                    "category": "research",
                    "summary": (f"Summary {index} " * 40).strip(),
                    "why_it_matters": (f"Why {index} " * 30).strip(),
                    "raw_content": (f"RAW FACTUAL SOURCE {index} " * 80).strip(),
                    "selection_reason": (f"Selection reason {index} " * 20).strip(),
                }
            )
        selection = {"items": items}
        plan = {
            "evidence": [
                {
                    "evidence_id": "anchor",
                    "selected_news_index": 1,
                    "role": "anchor",
                    "argument_role": "evidence",
                    "narrative_function": "Anchor the claim",
                },
                {
                    "evidence_id": "contrast",
                    "selected_news_index": 3,
                    "role": "contrast",
                    "argument_role": "counterexample",
                    "narrative_function": "Complicate the claim",
                },
            ]
        }
        return {
            "selected_news": json.dumps(selection),
            "news_text": json.dumps({"items": items}),
            "episode_plan": json.dumps(plan),
            "draft_script": "Draft",
        }

    def test_repeated_agents_receive_only_planned_factual_evidence(self) -> None:
        state = self._state()
        compacted, stats = compact_agent_state(SimpleNamespace(name="script_critic"), state)

        self.assertIsNotNone(stats)
        self.assertGreater(stats["context_char_reduction_pct"], 50)
        self.assertEqual(stats["selected_item_count"], 4)
        self.assertEqual(stats["used_evidence_item_count"], 2)

        selected = json.loads(compacted["selected_news"])
        evidence = json.loads(compacted["news_text"])

        # Keep all four positions so episode_plan.selected_news_index remains exact.
        self.assertEqual(len(selected["items"]), 4)
        self.assertEqual(selected["items"][0]["selected_news_index"], 1)
        self.assertTrue(selected["items"][1]["omitted_unused_evidence"])
        self.assertEqual(selected["items"][2]["selected_news_index"], 3)
        self.assertTrue(selected["items"][3]["omitted_unused_evidence"])

        # Raw factual source is retained for every used evidence item and nowhere else.
        self.assertEqual([item["selected_news_index"] for item in evidence["items"]], [1, 3])
        self.assertIn("RAW FACTUAL SOURCE 1", evidence["items"][0]["raw_content"])
        self.assertIn("RAW FACTUAL SOURCE 3", evidence["items"][1]["raw_content"])
        self.assertNotIn("RAW FACTUAL SOURCE 2", compacted["news_text"])
        self.assertNotIn("RAW FACTUAL SOURCE 4", compacted["news_text"])

        # Selection rationale is not a factual source and is deliberately not resent.
        self.assertNotIn("Selection reason", compacted["selected_news"])

    def test_planning_agents_keep_full_context(self) -> None:
        state = self._state()
        compacted, stats = compact_agent_state(SimpleNamespace(name="editorial_director"), state)
        self.assertIsNone(stats)
        self.assertEqual(compacted, state)

    def test_malformed_plan_fails_open(self) -> None:
        state = self._state()
        state["episode_plan"] = json.dumps(
            {"evidence": [{"evidence_id": "bad", "selected_news_index": 99}]}
        )
        compacted, stats = compact_agent_state(SimpleNamespace(name="script_refiner"), state)
        self.assertIsNone(stats)
        self.assertEqual(compacted, state)


if __name__ == "__main__":
    unittest.main()
