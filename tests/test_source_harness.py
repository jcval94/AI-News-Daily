from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.run_source_harness import _run_agent_with_source_harness
from pipeline.source_harness import build_source_harness, build_source_harness_from_state


class SourceHarnessTests(unittest.IsolatedAsyncioTestCase):
    def _selection(self) -> dict:
        return {
            "items": [
                {
                    "news_id": "2026-08-20:3",
                    "source_file": "2026-08-20.txt",
                    "source_locator": "2026-08-20.txt#item-3",
                    "item_index": 3,
                    "title": "SandboxAQ hace disponible AQCat en Claude Science mediante MCP",
                    "date": "2026-08-20",
                    "date_origin": "field",
                    "source": "SandboxAQ",
                    "url": "https://example.com/aqcat",
                    "url_quality": "article",
                    "category": "investigacion / agentes",
                    "summary": "AQCat permite consultar un modelo cientifico especializado.",
                    "why_it_matters": "Conecta lenguaje natural con simulacion cientifica.",
                    "raw_content": "RAW EXACT AQCAT\nFuente: SandboxAQ\nResumen: evidencia exacta",
                    "selection_reason": "Buen ejemplo de herramienta cientifica verificable.",
                },
                {
                    "news_id": "2026-08-20:4",
                    "source_file": "2026-08-20.txt",
                    "source_locator": "2026-08-20.txt#item-4",
                    "item_index": 4,
                    "title": "SandboxAQ lanza AQPotency para cribado virtual",
                    "date": "2026-08-20",
                    "date_origin": "field",
                    "source": "SandboxAQ",
                    "url": "https://example.com/aqpotency",
                    "url_quality": "article",
                    "category": "investigacion / producto",
                    "summary": "AQPotency estima potencia molecular.",
                    "why_it_matters": "Puede reducir experimentacion temprana.",
                    "raw_content": "RAW EXACT AQPOTENCY\nFuente: SandboxAQ\nResumen: evidencia exacta",
                    "selection_reason": "Caso complementario para descubrimiento cientifico.",
                },
            ],
            "discarded_duplicates": ["dup"],
            "selection_notes": ["shortlist editorial"],
        }

    def test_build_harness_is_index_plus_exact_selected_sources(self) -> None:
        selection = self._selection()
        harness = build_source_harness(
            selection,
            discovery_item_count=18,
            discovery_context_chars=12000,
        )

        index = harness["selected_news"]
        sources = harness["news_text"]
        manifest = harness["manifest"]

        self.assertEqual(index["context_scope"], "selected_story_index")
        self.assertEqual(sources["context_scope"], "selected_exact_sources")
        self.assertEqual(len(index["items"]), 2)
        self.assertEqual(len(sources["items"]), 2)
        self.assertNotIn("raw_content", index["items"][0])
        self.assertNotIn("summary", index["items"][0])
        self.assertEqual(sources["items"][0]["raw_content"], selection["items"][0]["raw_content"])
        self.assertEqual(sources["items"][1]["raw_content"], selection["items"][1]["raw_content"])
        self.assertEqual(index["items"][0]["selection_reason"], selection["items"][0]["selection_reason"])
        self.assertEqual(manifest["discovery_item_count"], 18)
        self.assertEqual(manifest["selected_item_count"], 2)
        self.assertEqual(manifest["omitted_after_selection_count"], 16)
        self.assertTrue(manifest["guarantees"]["exact_raw_content_for_every_selected_story"])
        self.assertFalse(manifest["guarantees"]["embeddings_or_vector_database"])
        self.assertGreater(manifest["runtime_context_char_reduction_pct"], 0)

    def test_state_harness_drops_unselected_discovery_material(self) -> None:
        selection = self._selection()
        full_discovery = {
            "items": selection["items"]
            + [
                {
                    "news_id": "2026-08-20:99",
                    "source_locator": "2026-08-20.txt#item-99",
                    "raw_content": "RAW REJECTED HARNESS STORY",
                }
            ]
        }
        state = {
            "selected_news": json.dumps(selection),
            "news_text": json.dumps(full_discovery),
            "other_state": "keep-me",
        }

        compacted, manifest = build_source_harness_from_state(state)
        self.assertIsNotNone(manifest)
        self.assertEqual(compacted["other_state"], "keep-me")
        self.assertNotIn("RAW REJECTED HARNESS STORY", compacted["news_text"])
        self.assertIn("RAW EXACT AQCAT", compacted["news_text"])
        self.assertIn("RAW EXACT AQPOTENCY", compacted["news_text"])

    async def test_director_receives_harness_and_reconciles_evidence(self) -> None:
        selection = self._selection()
        state = {
            "selected_news": json.dumps(selection),
            "news_text": json.dumps(
                {
                    "items": selection["items"]
                    + [
                        {
                            "news_id": "2026-08-20:99",
                            "source_locator": "2026-08-20.txt#item-99",
                            "raw_content": "RAW REJECTED STORY",
                        }
                    ]
                }
            ),
        }
        captured = {}
        trace = []

        async def fake_original(agent, initial_state, prompt, *, step, trace, iteration=None):
            captured.update(initial_state)
            trace.append(
                {
                    "step": step,
                    "agent": agent.name,
                    "iteration": iteration,
                    "status": "success",
                    "usage": {},
                }
            )
            return {
                "episode_plan": {
                    "evidence": [
                        {
                            "evidence_id": "aqpotency",
                            "selected_news_index": 1,
                        }
                    ],
                    "beats": [
                        {
                            "beat_id": "evidence",
                            "evidence_ids": ["aqpotency"],
                        }
                    ],
                }
            }

        with patch("pipeline.run_source_harness._ORIGINAL_RUN_AGENT", side_effect=fake_original):
            result = await _run_agent_with_source_harness(
                SimpleNamespace(name="editorial_director"),
                state,
                "plan",
                step="plan_episode",
                trace=trace,
                iteration=1,
            )

        self.assertNotIn("RAW REJECTED STORY", captured["news_text"])
        self.assertIn("RAW EXACT AQCAT", captured["news_text"])
        self.assertIn("RAW EXACT AQPOTENCY", captured["news_text"])
        captured_index = json.loads(captured["selected_news"])
        self.assertNotIn("raw_content", captured_index["items"][0])
        self.assertEqual(result["episode_plan"]["evidence"][0]["selected_news_index"], 2)
        self.assertEqual(trace[-1]["source_harness"]["selected_item_count"], 2)
        self.assertEqual(trace[-1]["evidence_reconciliation"]["changed_count"], 1)

    def test_missing_selection_fails_open(self) -> None:
        state = {"news_text": "full catalog"}
        compacted, manifest = build_source_harness_from_state(state)
        self.assertEqual(compacted, state)
        self.assertIsNone(manifest)


if __name__ == "__main__":
    unittest.main()
