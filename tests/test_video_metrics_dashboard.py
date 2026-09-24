from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.video_metrics_dashboard import build_dashboard, discover_metrics


class VideoMetricsDashboardTests(unittest.TestCase):
    def _episode(
        self,
        root: Path,
        date: str,
        *,
        editorial: float,
        attention: float,
        voice: float,
        seo: float,
        publishable: bool,
    ) -> Path:
        episode = root / date
        (episode / "artifacts").mkdir(parents=True)
        (episode / "downloads").mkdir(parents=True)
        (episode / "scripts").mkdir(parents=True)
        (episode / "media" / "opening").mkdir(parents=True)
        (episode / "index.html").write_text("<html></html>", encoding="utf-8")
        (episode / "artifacts" / "episode_plan.json").write_text(
            json.dumps({"episode_title": f"Episodio {date}"}), encoding="utf-8"
        )
        (episode / "artifacts" / "reviews.json").write_text(
            json.dumps({
                "editorial": {"score": editorial, "approved": editorial >= 8},
                "youtube_attention_master": {"score": attention, "approved": attention >= 8},
                "voice_humanity": {"score": voice, "approved": voice >= 8},
                "seo_master": {"score": seo, "approved": seo >= 8},
                "gate": {"duration_seconds": 600},
                "best_candidate": {"iteration": 2, "judged_unique_script_count": 3},
            }),
            encoding="utf-8",
        )
        (episode / "artifacts" / "run_state.json").write_text(
            json.dumps({
                "status": "script_approved" if publishable else "script_not_approved",
                "publishable": publishable,
                "started_at_utc": f"{date}T10:00:00",
                "finished_at_utc": f"{date}T10:02:00",
            }),
            encoding="utf-8",
        )
        (episode / "artifacts" / "editorial-regression.json").write_text(
            json.dumps({"structural_pass": True}), encoding="utf-8"
        )
        (episode / "artifacts" / "novelty_check.json").write_text(
            json.dumps({"attempts": [{}, {}]}), encoding="utf-8"
        )
        (episode / "artifacts" / "execution_trace.json").write_text(
            json.dumps({"agent_calls": [
                {"status": "success", "usage": {"total_tokens": 100}},
                {"status": "error", "usage": {"total_tokens": 50}},
            ]}),
            encoding="utf-8",
        )
        manifest = [
            {"file": "opening/a.mp4", "asset_type": "video", "mime_type": "video/mp4", "start_seconds": 2},
            {"file": "opening/b.jpg", "asset_type": "image", "mime_type": "image/jpeg", "start_seconds": 8},
        ]
        (episode / "artifacts" / "media-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (episode / "artifacts" / "media-plan.json").write_text(
            json.dumps({"opening_media_count": 2, "opening_video_count": 1}), encoding="utf-8"
        )
        (episode / "media" / "opening" / "a.mp4").write_bytes(b"mp4")
        (episode / "media" / "opening" / "b.jpg").write_bytes(b"jpg")
        (episode / "downloads" / "cost_snapshot.json").write_text(
            json.dumps({"totals": {"known_direct_cost_usd": 0.125}}), encoding="utf-8"
        )
        (episode / "scripts" / f"latest-{date}-run-1.txt").write_text(
            "uno dos tres cuatro cinco", encoding="utf-8"
        )
        return episode

    def test_extracts_primary_scores_and_relevant_production_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "episodes"
            self._episode(root, "2026-09-01", editorial=7.5, attention=8.0, voice=8.5, seo=9.0, publishable=False)
            self._episode(root, "2026-09-04", editorial=8.0, attention=8.5, voice=9.0, seo=9.5, publishable=True)

            rows = discover_metrics(root)

            self.assertEqual([row["date"] for row in rows], ["2026-09-01", "2026-09-04"])
            latest = rows[-1]
            self.assertEqual(latest["scores"]["editorial"], 8.0)
            self.assertEqual(latest["scores"]["attention"], 8.5)
            self.assertEqual(latest["scores"]["voice"], 9.0)
            self.assertEqual(latest["scores"]["seo"], 9.5)
            self.assertEqual(latest["asset_count"], 2)
            self.assertEqual(latest["video_count"], 1)
            self.assertEqual(latest["opening_video_count"], 1)
            self.assertEqual(latest["judged_unique_script_count"], 3)
            self.assertEqual(latest["novelty_attempt_count"], 2)
            self.assertEqual(latest["recorded_total_tokens"], 150)
            self.assertEqual(latest["agent_error_count"], 1)
            self.assertEqual(latest["known_direct_cost_usd"], 0.125)

    def test_build_dashboard_writes_static_chart_table_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "episodes"
            self._episode(root, "2026-09-04", editorial=8.0, attention=8.5, voice=9.0, seo=9.5, publishable=True)

            index = build_dashboard(episodes_root=root, output_dir=base / "metrics")
            document = index.read_text(encoding="utf-8")
            payload = json.loads((base / "metrics" / "video-metrics-history.json").read_text(encoding="utf-8"))

            self.assertIn('data-metrics-page="video-metrics-history"', document)
            self.assertIn("Editorial", document)
            self.assertIn("Attention", document)
            self.assertIn("Voice", document)
            self.assertIn("SEO", document)
            self.assertIn('class="trend-chart"', document)
            self.assertIn("Videos 0–20s", document)
            self.assertIn("Costo", document)
            self.assertEqual(payload["metric_scope"], "editorial_pipeline_not_youtube_analytics")
            self.assertEqual(len(payload["episodes"]), 1)


if __name__ == "__main__":
    unittest.main()
