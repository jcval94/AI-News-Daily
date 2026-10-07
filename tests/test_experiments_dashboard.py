from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.experiments_dashboard import build_dashboard, discover_experiments


class ExperimentsDashboardTests(unittest.TestCase):
    def _write_json(self, path: Path, value: object) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_builds_index_editable_run_and_story_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "experiments"
            run = root / "notebook_story_flow" / "results" / "2026-09-25" / "gh-123-1"
            run.mkdir(parents=True)
            self._write_json(
                run / "run_report.json",
                {
                    "experiment": "notebook_story_flow",
                    "episode_date": "2026-09-25",
                    "status": "rejected_factual",
                    "publishable": False,
                    "word_count": 1200,
                    "estimated_duration_seconds": 480,
                    "words_per_minute": 150,
                    "source_episode_dir": "C:/private/source",
                },
            )
            self._write_json(run / "deterministic_gate.json", {"passed": True, "issues": []})
            self._write_json(run / "factual_review.json", {"risk": "medium", "invented_details": ["Falta <fuente>"]})
            self._write_json(
                run / "story_plan.json",
                {
                    "selected_memory_id": "apollo-story",
                    "ledger": [{"evidence_id": "current-case", "news_id": "n_1"}],
                },
            )
            self._write_json(
                run / "script_sections.json",
                {
                    "sections": [
                        {"id": "opening", "text": "Historia <abierta>", "memory_claim_indices": [1], "evidence_ids": [], "start_seconds": 0, "end_seconds": 90},
                        {"id": "dato_1", "text": "Caso actual", "memory_claim_indices": [], "evidence_ids": ["current-case"], "start_seconds": 90, "end_seconds": 120},
                    ]
                },
            )
            (run / "script.txt").write_text("Historia abierta\n\nCaso actual", encoding="utf-8")

            failed = root / "notebook_story_flow" / "results" / "2026-10-06" / "gh-456-1"
            failed.mkdir(parents=True)
            self._write_json(
                failed / "run_report.json",
                {"experiment": "notebook_story_flow", "episode_date": "2026-10-06", "status": "failure", "reason": "Validation failed"},
            )

            discovered = discover_experiments([root])
            index = build_dashboard(roots=[root], output_dir=base / "site")
            document = index.read_text(encoding="utf-8")
            manifest = json.loads((base / "site" / "experiments.json").read_text(encoding="utf-8"))
            editable = next(item for item in discovered if item["script"])
            run_page = (base / "site" / "runs" / editable["slug"] / "index.html").read_text(encoding="utf-8")
            failed_item = next(item for item in discovered if not item["script"])
            failed_page = (base / "site" / "runs" / failed_item["slug"] / "index.html").read_text(encoding="utf-8")

            self.assertEqual(len(discovered), 2)
            self.assertIn('data-experiments-page="experiments"', document)
            self.assertIn("Abrir mesa de guion", document)
            self.assertIn('data-script-editor="v1"', run_page)
            self.assertIn('data-script-productivity-runtime="v1"', run_page)
            self.assertIn('id="scriptDiffButton"', run_page)
            self.assertIn("Apollo Story", run_page)
            self.assertIn("Current Case", run_page)
            self.assertIn("Historia &lt;abierta&gt;", run_page)
            self.assertIn("terminó antes de producir un guion", failed_page)
            self.assertNotIn('data-script-editor="v1"', failed_page)
            self.assertNotIn("C:/private/source", json.dumps(manifest))
            self.assertNotIn("script", manifest["experiments"][0])


if __name__ == "__main__":
    unittest.main()
