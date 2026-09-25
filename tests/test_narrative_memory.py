from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.narrative_memory import (
    NarrativeMemoryItem,
    gate_reasons,
    load_memory,
    load_usage_history,
    rank_candidates,
    resolve_selected_memory,
)


def _item(item_id: str = "toyota-war", mechanism: str = "agility_vs_scale") -> dict:
    return {
        "id": item_id,
        "title": "A verified unusual historical case",
        "one_liner": "A surprising case whose structure can illuminate a modern problem.",
        "summary": "A sufficiently detailed verified summary that can be safely used as contextual evidence.",
        "verified_claims": ["A source-backed fact."],
        "uncertainties": ["The analogy does not establish identical causality."],
        "sources": ["https://example.org/source"],
        "period": "1980s",
        "location": "Example",
        "domains": ["history"],
        "mechanisms": [mechanism],
        "useful_for": ["small systems versus large systems"],
        "analogy_mapping": "Map the structural trade-off, not the literal historical details.",
        "analogy_limits": "Do not claim the two domains are causally equivalent.",
        "surprise_score": 9,
        "explanatory_score": 9,
        "analogy_potential": 9,
        "visual_score": 8,
        "sourceability_score": 8,
        "source_quality_score": 9,
        "confidence": 9,
        "semantic_duplicate_risk": "low",
        "source_kind": "scheduled_research",
        "created_at": "2026-09-24",
        "status": "approved",
    }


class NarrativeMemoryTests(unittest.TestCase):
    def test_gate_rejects_pajita_even_if_valid_json(self) -> None:
        data = _item()
        data["surprise_score"] = 6
        item = NarrativeMemoryItem.model_validate(data)
        self.assertIn("surprise_below_gate", gate_reasons(item))

    def test_loader_quarantines_invalid_and_duplicate_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.jsonl"
            good = _item()
            bad = _item("weak-case")
            bad["source_quality_score"] = 4
            path.write_text(
                "\n".join([json.dumps(good), json.dumps(good), json.dumps(bad), "{bad json"]) + "\n",
                encoding="utf-8",
            )
            items, issues = load_memory(path)
            self.assertEqual([item.id for item in items], ["toyota-war"])
            self.assertTrue(any("duplicate_id" in issue for issue in issues))
            self.assertTrue(any("quarantined:weak-case" in issue for issue in issues))
            self.assertTrue(any("invalid_line" in issue for issue in issues))

    def test_cooldown_is_soft_and_available_items_rank_first(self) -> None:
        items = [
            NarrativeMemoryItem.model_validate(_item("recent")),
            NarrativeMemoryItem.model_validate(_item("fresh", "technology_requires_redesign")),
        ]
        usage = {
            "recent": {"times_used": 1, "last_used_at": "2026-09-01", "episodes_used": ["2026-09-01"]}
        }
        ranked = rank_candidates(items, "technology redesign small systems", usage, date(2026, 9, 24))
        self.assertEqual(ranked[0]["id"], "fresh")
        self.assertEqual(ranked[1]["id"], "recent")
        self.assertTrue(ranked[1]["retrieval"]["cooldown_active"])

    def test_cooldown_candidate_remains_available_as_fallback(self) -> None:
        items = [NarrativeMemoryItem.model_validate(_item("recent"))]
        usage = {
            "recent": {"times_used": 1, "last_used_at": "2026-09-20", "episodes_used": ["2026-09-20"]}
        }
        ranked = rank_candidates(items, "small systems", usage, date(2026, 9, 24))
        self.assertEqual([item["id"] for item in ranked], ["recent"])
        self.assertTrue(ranked[0]["retrieval"]["cooldown_active"])

    def test_usage_is_derived_only_from_approved_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved = root / "2026-09-01"
            approved.mkdir()
            (approved / "run_state.json").write_text('{"status":"approved"}', encoding="utf-8")
            (approved / "episode_plan.json").write_text(
                '{"narrative_parallels":[{"memory_id":"case-a","purpose":"x","role":"analogy","limits":"y"}]}',
                encoding="utf-8",
            )
            rejected = root / "2026-09-02"
            rejected.mkdir()
            (rejected / "run_state.json").write_text('{"status":"script_not_approved"}', encoding="utf-8")
            (rejected / "episode_plan.json").write_text(
                '{"narrative_parallels":[{"memory_id":"case-b"}]}',
                encoding="utf-8",
            )

            usage = load_usage_history(root, date(2026, 9, 24))
            self.assertEqual(usage["case-a"]["times_used"], 1)
            self.assertNotIn("case-b", usage)

    def test_plan_requires_at_least_one_selection(self) -> None:
        with self.assertRaises(ValueError):
            resolve_selected_memory({"narrative_parallels": []}, [_item("allowed")])

    def test_plan_can_select_primary_memory_without_opening_contract(self) -> None:
        candidates = [_item("allowed")]
        plan = {
            "primary_memory_id": "allowed",
            "narrative_parallels": [
                {
                    "memory_id": "allowed",
                    "role": "historical_mirror",
                    "placement": "narrative_turn",
                    "purpose": "Reencuadrar el argumento.",
                    "limits": "No asumir causalidad idéntica.",
                }
            ],
        }
        selected = resolve_selected_memory(plan, candidates)
        self.assertEqual([item["id"] for item in selected], ["allowed"])

    def test_plan_can_only_select_from_retrieved_set(self) -> None:
        candidates = [_item("allowed")]
        plan = {
            "opening_memory_id": "outside",
            "narrative_parallels": [
                {"memory_id": "outside", "role": "analogy", "purpose": "x", "limits": "y"}
            ]
        }
        with self.assertRaises(ValueError):
            resolve_selected_memory(plan, candidates)


if __name__ == "__main__":
    unittest.main()
