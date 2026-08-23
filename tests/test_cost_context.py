from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from pipeline.run_cost_optimized import compact_agent_state


class CostContextTests(unittest.TestCase):
    def _state(self) -> dict[str, str]:
        names = ["TRACES", "AQCat", "AQPotency", "Harness"]
        items = []
        for index, name in enumerate(names, start=1):
            items.append(
                {
                    "news_id": f"2026-08-21:{index}",
                    "source_file": "2026-08-21.txt",
                    "source_locator": f"2026-08-21.txt#item-{index}",
                    "item_index": index,
                    "title": f"Story about {name}",
                    "date": "2026-08-21",
                    "source": "Example",
                    "url": f"https://example.com/{index}",
                    "url_quality": "article",
                    "category": "research",
                    "summary": (f"Summary {name} " * 40).strip(),
                    "why_it_matters": (f"Why {name} " * 30).strip(),
                    "raw_content": (f"RAW FACTUAL SOURCE {name} " * 80).strip(),
                    "selection_reason": (f"Selection reason {name} " * 20).strip(),
                }
            )
        selection = {"items": items}
        plan = {
            "evidence": [
                {
                    "evidence_id": "traces_benchmark",
                    "selected_news_index": 1,
                    "role": "anchor",
                    "argument_role": "evidence",
                    "narrative_function": "Anchor the claim",
                },
                # Deliberately reproduce the historical mismatch from the audited run.
                {
                    "evidence_id": "aqpotency_predictions",
                    "selected_news_index": 4,
                    "role": "support",
                    "argument_role": "limit_case",
                    "narrative_function": "Complicate the claim",
                },
                {
                    "evidence_id": "aqcat_tool_use",
                    "selected_news_index": 3,
                    "role": "contrast",
                    "argument_role": "bridge",
                    "narrative_function": "Bridge the claim",
                },
            ],
            "beats": [
                {"beat_id": "b1", "evidence_ids": ["traces_benchmark"]},
                {"beat_id": "b2", "evidence_ids": ["aqpotency_predictions"]},
                {"beat_id": "b3", "evidence_ids": ["aqcat_tool_use"]},
            ],
        }
        # validate_episode_plan only needs the evidence/beat fields used by its structural checks.
        return {
            "selected_news": json.dumps(selection),
            "news_text": json.dumps({"items": items}),
            "episode_plan": json.dumps(plan),
            "draft_script": "Draft",
        }

    def test_conservative_mode_reconciles_and_keeps_unused_editorial_context(self) -> None:
        state = self._state()
        compacted, stats = compact_agent_state(
            SimpleNamespace(name="script_critic"), state, mode="conservative"
        )

        self.assertIsNotNone(stats)
        self.assertEqual(stats["evidence_reconciliation_count"], 2)
        self.assertEqual(stats["used_evidence_indices"], [1, 2, 3])
        self.assertEqual(stats["selected_item_count"], 4)
        self.assertEqual(stats["used_evidence_item_count"], 3)
        self.assertGreater(stats["context_char_reduction_pct"], 20)

        selected = json.loads(compacted["selected_news"])
        evidence = json.loads(compacted["news_text"])
        plan = json.loads(compacted["episode_plan"])

        indices = {
            item["evidence_id"]: item["selected_news_index"]
            for item in plan["evidence"]
        }
        self.assertEqual(indices["aqpotency_predictions"], 3)
        self.assertEqual(indices["aqcat_tool_use"], 2)

        # Conservative mode keeps all selected stories visible as editorial context.
        self.assertEqual(len(selected["items"]), 4)
        self.assertEqual(selected["items"][3]["title"], "Story about Harness")
        self.assertIn("Summary Harness", selected["items"][3]["summary"])
        self.assertFalse(selected["items"][3]["planned_evidence"])

        # But raw factual payload is retained only for the three intended evidence items.
        self.assertEqual(
            [item["selected_news_index"] for item in evidence["items"]], [1, 2, 3]
        )
        self.assertIn("RAW FACTUAL SOURCE TRACES", compacted["news_text"])
        self.assertIn("RAW FACTUAL SOURCE AQCat", compacted["news_text"])
        self.assertIn("RAW FACTUAL SOURCE AQPotency", compacted["news_text"])
        self.assertNotIn("RAW FACTUAL SOURCE Harness", compacted["news_text"])

        # Selection rationale is editorial bookkeeping, not factual evidence.
        self.assertNotIn("Selection reason", compacted["selected_news"])
        self.assertEqual(len(stats["retained_evidence_sha256"]), 3)

    def test_strict_mode_hides_unused_headlines(self) -> None:
        state = self._state()
        compacted, stats = compact_agent_state(
            SimpleNamespace(name="script_refiner"), state, mode="strict"
        )
        self.assertIsNotNone(stats)
        selected = json.loads(compacted["selected_news"])
        unused = selected["items"][3]
        self.assertTrue(unused["omitted_unused_evidence"])
        self.assertNotIn("title", unused)
        self.assertGreater(
            stats["context_char_reduction_pct"],
            compact_agent_state(
                SimpleNamespace(name="script_refiner"), state, mode="conservative"
            )[1]["context_char_reduction_pct"],
        )

    def test_seo_compacts_selection_but_does_not_invent_news_text(self) -> None:
        state = self._state()
        state.pop("news_text")
        compacted, stats = compact_agent_state(
            SimpleNamespace(name="seo_master"), state, mode="conservative"
        )
        self.assertIsNotNone(stats)
        self.assertNotIn("news_text", compacted)
        self.assertLess(len(compacted["selected_news"]), len(state["selected_news"]))

    def test_planning_agents_keep_full_context(self) -> None:
        state = self._state()
        compacted, stats = compact_agent_state(
            SimpleNamespace(name="editorial_director"), state, mode="strict"
        )
        self.assertIsNone(stats)
        self.assertEqual(compacted, state)

    def test_malformed_plan_fails_open(self) -> None:
        state = self._state()
        state["episode_plan"] = json.dumps(
            {
                "evidence": [{"evidence_id": "bad", "selected_news_index": 99}],
                "beats": [{"beat_id": "b1", "evidence_ids": ["bad"]}],
            }
        )
        compacted, stats = compact_agent_state(
            SimpleNamespace(name="script_refiner"), state, mode="conservative"
        )
        self.assertIsNone(stats)
        self.assertEqual(compacted, state)

    def test_off_mode_is_exact_noop(self) -> None:
        state = self._state()
        compacted, stats = compact_agent_state(
            SimpleNamespace(name="script_critic"), state, mode="off"
        )
        self.assertIsNone(stats)
        self.assertEqual(compacted, state)


if __name__ == "__main__":
    unittest.main()
