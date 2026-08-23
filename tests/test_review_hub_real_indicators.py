from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.review_hub_v4 import apply_real_indicators, derive_real_indicators


class ReviewHubRealIndicatorTests(unittest.TestCase):
    def test_indicators_use_persisted_measurements_and_existing_media_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "episode"
            media = root / "media"
            episode.mkdir()
            media.mkdir()

            (episode / "script.txt").write_text("uno dos tres cuatro", encoding="utf-8")
            (episode / "reviews.json").write_text(
                json.dumps(
                    {
                        "gate": {"duration_seconds": 120},
                        "best_candidate": {"iteration": 3, "judged_unique_script_count": 3},
                        "editorial": {"score": 7.1},
                        "seo_master": {},
                        "youtube_attention_master": {"score": 7.6},
                        "voice_humanity": {"score": 8.1},
                    }
                ),
                encoding="utf-8",
            )
            (episode / "run_state.json").write_text(
                json.dumps(
                    {
                        "episode_date": "2026-08-21",
                        "status": "script_not_approved",
                        "publishable": False,
                        "started_at_utc": "2026-08-22T00:00:00+00:00",
                        "finished_at_utc": "2026-08-22T00:00:10+00:00",
                    }
                ),
                encoding="utf-8",
            )
            (episode / "novelty_check.json").write_text(
                json.dumps({"attempts": [{"attempt": 1}]}), encoding="utf-8"
            )
            (episode / "execution_trace.json").write_text(
                json.dumps(
                    {
                        "agent_calls": [
                            {"status": "success", "usage": {"total_tokens": 123}},
                            {"status": "error"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            opening = media / "opening.mp4"
            opening.write_bytes(b"video")
            later = media / "later.jpg"
            later.write_bytes(b"image")
            (media / "manifest.json").write_text(
                json.dumps(
                    [
                        {
                            "file": "opening.mp4",
                            "asset_type": "video",
                            "mime_type": "video/mp4",
                            "start_seconds": 0,
                        },
                        {
                            "file": "missing.mp4",
                            "asset_type": "video",
                            "start_seconds": 4,
                        },
                        {"file": "later.jpg", "asset_type": "image", "start_seconds": 30},
                    ]
                ),
                encoding="utf-8",
            )
            regression = root / "editorial-regression.json"
            regression.write_text(json.dumps({"structural_pass": True}), encoding="utf-8")

            indicators = derive_real_indicators(
                episode_dir=episode,
                media_dir=media,
                regression_path=regression,
                run_id="123",
            )

            self.assertEqual(indicators["word_count"], 4)
            self.assertEqual(indicators["duration_seconds"], 120)
            self.assertEqual(indicators["asset_count"], 2)
            self.assertEqual(indicators["opening_asset_count"], 1)
            self.assertEqual(indicators["opening_video_count"], 1)
            self.assertEqual(indicators["scores"]["editorial"], 7.1)
            self.assertIsNone(indicators["scores"]["seo"])
            self.assertEqual(indicators["recorded_total_tokens"], 123)
            self.assertEqual(indicators["agent_error_count"], 1)
            self.assertEqual(indicators["wall_seconds"], 10)

            page = """
<section class="hero">
<div class="hero-row"><span class="badge bad">OLD</span> <span class="muted">old indicators</span></div>
<div class="hero-meta">Human review · old</div>
</section>
<div class="metrics"><div class="metric"><strong>7.1</strong><span>Editorial</span></div><div class="metric"><strong>5</strong><span>media 0–20s</span></div><div class="metric"><strong>4</strong><span>videos 0–20s</span></div></div>
<div class="grid2">reviews</div>
<section id="multimedia" data-search-group><h2>Multimedia de revisión</h2><p>old media summary</p><p>downloads</p></section>
"""
            upgraded = apply_real_indicators(page, indicators)

            self.assertIn("2 assets descargados", upgraded)
            self.assertIn("1 videos descargados en 0–20s", upgraded)
            self.assertIn("5</strong><span>media 0–20s · plan", upgraded)
            self.assertIn("4</strong><span>videos 0–20s · plan", upgraded)
            self.assertIn("—</strong><span>SEO · reviews.json", upgraded)
            self.assertNotIn("0.0</strong><span>SEO", upgraded)
            self.assertIn("123</strong><span>Tokens registrados", upgraded)
            self.assertIn("Revisión humana: <strong>pendiente</strong>", upgraded)
            self.assertIn("costo monetario no se muestra", upgraded)


if __name__ == "__main__":
    unittest.main()
