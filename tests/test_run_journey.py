from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.review_hub_v11 import run_journey_section
from pipeline.run_journey import derive_run_journey


class RunJourneyTests(unittest.TestCase):
    def _write(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_derives_executed_and_not_required_refinement_phases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp) / "scripts" / "2026-08-21"
            production_media = Path(tmp) / "multimedia" / "2026-08-21"
            episode.mkdir(parents=True)
            production_media.mkdir(parents=True)
            self._write(episode / "run_state.json", {"status": "approved", "publishable": True, "reason": "all gates passed"})
            self._write(episode / "selected_news.json", {"items": [{"title": "A"}, {"title": "B"}]})
            self._write(episode / "episode_plan.json", {"claim_ledger": [{"evidence_id": "E1"}]})
            self._write(episode / "novelty_check.json", {"attempts": [{"similarity": 0.19, "duplicate": False}]})
            self._write(episode / "reviews.json", {"approved_for_multimedia": True, "gate": {"approved": True}})
            self._write(
                episode / "execution_trace.json",
                {
                    "agent_calls": [
                        {"step": "select_news", "status": "success", "elapsed_seconds": 1.0, "usage": {"total_tokens": 100}},
                        {"step": "plan_episode", "status": "success", "elapsed_seconds": 2.0, "usage": {"total_tokens": 200}},
                        {"step": "write_script", "status": "success", "elapsed_seconds": 3.0, "usage": {"total_tokens": 300}},
                        {"step": "editorial_judge", "status": "success", "elapsed_seconds": 1.0, "usage": {"total_tokens": 50}},
                        {"step": "seo_judge", "status": "success", "elapsed_seconds": 1.0, "usage": {"total_tokens": 50}},
                        {"step": "attention_judge", "status": "success", "elapsed_seconds": 1.0, "usage": {"total_tokens": 50}},
                        {"step": "voice_judge", "status": "success", "elapsed_seconds": 1.0, "usage": {"total_tokens": 50}},
                        {"step": "refine_factual", "status": "success", "elapsed_seconds": 4.0, "usage": {"total_tokens": 400}},
                        {"step": "plan_multimedia", "status": "success", "elapsed_seconds": 2.0, "usage": {"total_tokens": 100}},
                    ],
                    "refinement_iterations": [
                        {"iteration": 1, "approved": False, "next_refinement_phase": "factual"},
                        {"iteration": 2, "approved": True, "next_refinement_phase": None},
                    ],
                },
            )
            self._write(production_media / "manifest.json", [{"file": "asset.jpg"}])
            snapshot = {
                "breakdown_by_step": [
                    {"step": "select_news", "estimated_cost_usd": 0.001},
                    {"step": "refine_factual", "estimated_cost_usd": 0.004},
                ]
            }

            journey = derive_run_journey(
                episode_dir=episode,
                production_media_dir=production_media,
                cost_snapshot=snapshot,
            )
            by_id = {stage["id"]: stage for stage in journey["stages"]}
            self.assertEqual(journey["status"], "approved")
            self.assertEqual(journey["selected_news_count"], 2)
            self.assertEqual(journey["refinement_iterations"], 2)
            self.assertEqual(by_id["factual_refine"]["status"], "executed")
            self.assertEqual(by_id["factual_refine"]["tokens"], 400)
            self.assertAlmostEqual(by_id["factual_refine"]["estimated_cost_usd"], 0.004)
            self.assertEqual(by_id["voice_refine"]["status"], "not_required")
            self.assertEqual(by_id["secondary_refine"]["status"], "not_required")
            self.assertEqual(by_id["media_materialize"]["status"], "executed")

            html = run_journey_section(journey)
            self.assertIn("Qué camino tomó este episodio", html)
            self.assertIn("refiners fueron realmente necesarios", html)
            self.assertIn("Factual repair", html)
            self.assertIn("NO REQUERIDO", html)
            self.assertIn("$0.0040", html)

    def test_discovers_production_media_beside_persisted_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp) / ".review-source" / "scripts" / "2026-08-21"
            production_media = Path(tmp) / ".review-source" / "multimedia" / "2026-08-21"
            episode.mkdir(parents=True)
            self._write(episode / "run_state.json", {"status": "approved", "publishable": True})
            self._write(production_media / "manifest.json", [{"file": "production.jpg"}])

            journey = derive_run_journey(episode_dir=episode, cost_snapshot={})
            by_id = {stage["id"]: stage for stage in journey["stages"]}
            self.assertEqual(by_id["media_materialize"]["status"], "executed")

    def test_review_media_is_not_misreported_as_production_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp) / "episode"
            review_media = Path(tmp) / "review-media"
            episode.mkdir()
            review_media.mkdir()
            self._write(episode / "run_state.json", {"status": "approved", "publishable": True})
            self._write(review_media / "manifest.json", [{"file": "review-only.jpg"}])
            journey = derive_run_journey(episode_dir=episode, media_dir=review_media, cost_snapshot={})
            by_id = {stage["id"]: stage for stage in journey["stages"]}
            self.assertEqual(by_id["media_materialize"]["status"], "not_observed")

    def test_non_publishable_state_remains_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp)
            self._write(episode / "run_state.json", {"status": "no_novel_essay_angle", "publishable": False, "reason": "duplicate angle"})
            self._write(episode / "novelty_check.json", {"attempts": [{"similarity": 0.55, "duplicate": True}]})
            journey = derive_run_journey(episode_dir=episode, cost_snapshot={})
            self.assertFalse(journey["publishable"])
            self.assertEqual(journey["status"], "no_novel_essay_angle")
            self.assertEqual(journey["nearest_similarity"], 0.55)
            html = run_journey_section(journey)
            self.assertIn("no_novel_essay_angle", html)
            self.assertIn("duplicate angle", html)


if __name__ == "__main__":
    unittest.main()
