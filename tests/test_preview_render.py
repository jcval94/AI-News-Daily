import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline.preview_render import build_preview_plan, render_preview


def _png(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (640, 360), (value, value, value)).save(path)


def resolve_plan() -> dict:
    return {
        "episode_date": "2026-09-24",
        "summary": {"duration_seconds": 4.0},
        "placements": [
            {
                "placement_id": "v1_a",
                "track_id": "V1",
                "take_id": "take_a",
                "cue_id": None,
                "timeline_start_seconds": 0.0,
                "duration_seconds": 2.0,
                "logical_repo_path": "scripts/2026-09-24/placeholder_media/v1/take_a.png",
                "placeholder": True,
            },
            {
                "placement_id": "v1_b",
                "track_id": "V1",
                "take_id": "take_b",
                "cue_id": None,
                "timeline_start_seconds": 2.0,
                "duration_seconds": 2.0,
                "logical_repo_path": "scripts/2026-09-24/placeholder_media/v1/take_b.png",
                "placeholder": True,
            },
            {
                "placement_id": "v2_a",
                "track_id": "V2",
                "take_id": None,
                "cue_id": "slot_001",
                "timeline_start_seconds": 1.0,
                "duration_seconds": 2.0,
                "logical_repo_path": "scripts/2026-09-24/placeholder_media/v2/slot_001.png",
                "placeholder": True,
            },
        ],
    }


class PreviewRenderTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict:
        _png(root / "scripts/2026-09-24/placeholder_media/v1/take_a.png", 50)
        _png(root / "scripts/2026-09-24/placeholder_media/v1/take_b.png", 90)
        _png(root / "scripts/2026-09-24/placeholder_media/v2/slot_001.png", 140)
        return resolve_plan()

    def test_v2_overrides_v1_and_adjacent_same_source_is_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._fixture(root)
            plan = build_preview_plan(
                resolve_plan=payload,
                repo_root=root,
                width=640,
                height=360,
                fps=10,
            )
            self.assertEqual(plan["summary"]["segment_count"], 3)
            self.assertEqual(
                [item["track_id"] for item in plan["segments"]],
                ["V1", "V2", "V1"],
            )
            self.assertEqual(
                [(item["timeline_start_seconds"], item["timeline_end_seconds"]) for item in plan["segments"]],
                [(0.0, 1.0), (1.0, 3.0), (3.0, 4.0)],
            )
            self.assertEqual(plan["summary"]["presenter_seconds"], 2.0)
            self.assertEqual(plan["summary"]["broll_seconds"], 2.0)
            self.assertEqual(plan["summary"]["placeholder_broll_seconds"], 2.0)
            self.assertEqual(plan["summary"]["broll_coverage_ratio"], 0.5)
            self.assertFalse(plan["policy"]["publishable"])
            self.assertFalse(plan["policy"]["frame_accurate"])

    def test_missing_v1_base_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._fixture(root)
            payload["placements"] = [payload["placements"][2]]
            with self.assertRaisesRegex(ValueError, "exactly one V1"):
                build_preview_plan(
                    resolve_plan=payload,
                    repo_root=root,
                    width=640,
                    height=360,
                    fps=10,
                )

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg unavailable")
    def test_short_preview_is_really_encoded_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._fixture(root)
            payload["summary"]["duration_seconds"] = 2.0
            payload["placements"] = [
                {
                    **payload["placements"][0],
                    "duration_seconds": 2.0,
                },
                {
                    **payload["placements"][2],
                    "timeline_start_seconds": 0.5,
                    "duration_seconds": 1.0,
                },
            ]
            plan = build_preview_plan(
                resolve_plan=payload,
                repo_root=root,
                width=320,
                height=180,
                fps=6,
            )
            output = root / "preview.mp4"
            validation_path = root / "validation.json"
            validation = render_preview(
                plan=plan,
                repo_root=root,
                output_path=output,
                validation_path=validation_path,
            )
            self.assertTrue(validation["valid"])
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)
            self.assertEqual(validation["width"], 320)
            self.assertEqual(validation["height"], 180)
            self.assertEqual(validation["audio_codec"], "aac")
            self.assertFalse(validation["publishable"])
            saved = json.loads(validation_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["decode_fallback_count"], 0)


if __name__ == "__main__":
    unittest.main()
