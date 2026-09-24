from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.narrative_memory_dashboard import build_dashboard, build_report


def memory_item(item_id: str, mechanism: str, *, source_kind: str = "scheduled_research") -> dict:
    return {
        "id": item_id,
        "title": f"Verified narrative case {item_id}",
        "one_liner": "A surprising verified case that exposes a reusable structural mechanism.",
        "summary": "A sufficiently detailed verified summary that can be reused as contextual evidence in a future essay.",
        "verified_claims": ["A source-backed factual claim."],
        "uncertainties": ["The analogy does not establish identical causality."],
        "sources": ["https://example.org/source"],
        "period": "1980s",
        "location": "Example",
        "domains": ["history", "technology"],
        "mechanisms": [mechanism],
        "useful_for": ["AI systems"],
        "analogy_mapping": "Use only the structural trade-off between the two systems.",
        "analogy_limits": "Do not claim causal equivalence between historical and AI contexts.",
        "surprise_score": 9.0,
        "explanatory_score": 8.5,
        "analogy_potential": 9.0,
        "visual_score": 8.0,
        "sourceability_score": 8.0,
        "source_quality_score": 9.0,
        "confidence": 9.0,
        "semantic_duplicate_risk": "low",
        "source_kind": source_kind,
        "created_at": "2026-09-24",
        "status": "approved",
    }


class NarrativeMemoryDashboardTests(unittest.TestCase):
    def _write_episode(
        self,
        scripts_root: Path,
        episode_date: str,
        *,
        status: str,
        memory_ids: list[str],
    ) -> None:
        episode = scripts_root / episode_date
        episode.mkdir(parents=True)
        (episode / "run_state.json").write_text(
            json.dumps({"status": status}),
            encoding="utf-8",
        )
        (episode / "episode_plan.json").write_text(
            json.dumps(
                {
                    "narrative_parallels": [
                        {
                            "memory_id": memory_id,
                            "role": "analogy",
                            "purpose": "Explain the structure.",
                            "limits": "Preserve the analogy boundary.",
                        }
                        for memory_id in memory_ids
                    ]
                }
            ),
            encoding="utf-8",
        )

    def test_report_separates_inventory_usage_and_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "narrative_memory.jsonl"
            memory.write_text(
                "\n".join(
                    [
                        json.dumps(memory_item("used-case", "agility_vs_scale")),
                        json.dumps(memory_item("fresh-case", "technology_requires_redesign", source_kind="editorial_seed")),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            scripts = root / "scripts"
            self._write_episode(
                scripts,
                "2026-09-01",
                status="approved",
                memory_ids=["used-case"],
            )
            self._write_episode(
                scripts,
                "2026-09-02",
                status="script_not_approved",
                memory_ids=["fresh-case"],
            )

            report = build_report(
                memory_path=memory,
                scripts_root=scripts,
                as_of=date(2026, 9, 24),
                cooldown_days=90,
            )

            self.assertEqual(report["metrics"]["approved_items"], 2)
            self.assertEqual(report["metrics"]["used_items"], 1)
            self.assertEqual(report["metrics"]["unused_items"], 1)
            self.assertEqual(report["metrics"]["cooldown_items"], 1)
            self.assertEqual(report["metrics"]["available_items"], 1)
            self.assertEqual(report["metrics"]["unique_mechanisms"], 2)
            self.assertEqual(report["metrics"]["scheduled_research_items"], 1)
            self.assertEqual(report["metrics"]["editorial_seed_items"], 1)

            rows = {item["id"]: item for item in report["items"]}
            self.assertEqual(rows["used-case"]["times_used"], 1)
            self.assertEqual(rows["used-case"]["availability"], "cooldown")
            self.assertGreater(rows["used-case"]["cooldown_remaining_days"], 0)
            self.assertEqual(rows["fresh-case"]["times_used"], 0)
            self.assertEqual(rows["fresh-case"]["availability"], "available")

    def test_build_dashboard_publishes_json_and_filterable_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "narrative_memory.jsonl"
            memory.write_text(
                json.dumps(memory_item("case-a", "coordination_failure")) + "\n",
                encoding="utf-8",
            )
            output = root / "pages" / "memory"

            index = build_dashboard(
                memory_path=memory,
                scripts_root=root / "scripts",
                output_dir=output,
                as_of=date(2026, 9, 24),
            )

            document = index.read_text(encoding="utf-8")
            payload = json.loads((output / "narrative-memory.json").read_text(encoding="utf-8"))

            self.assertIn('data-memory-page="narrative-memory"', document)
            self.assertIn('id="memorySearch"', document)
            self.assertIn('id="mechanismFilter"', document)
            self.assertIn('id="availabilityFilter"', document)
            self.assertIn("Mecanismos narrativos", document)
            self.assertIn("Paralelos que llegaron a episodios aprobados", document)
            self.assertEqual(payload["metrics"]["approved_items"], 1)
            self.assertEqual(payload["items"][0]["id"], "case-a")


if __name__ == "__main__":
    unittest.main()
