import json
import tempfile
import unittest
from pathlib import Path

from pipeline.placeholder_media import build_placeholder_manifest, write_placeholder_media


def virtual_payload():
    return {
        "episode_date": "2026-09-24",
        "format": {"resolution": "3840x2160"},
        "tracks": [
            {
                "track_id": "V2",
                "clips": [
                    {
                        "clip_id": "broll_001",
                        "status": "placeholder",
                        "cue_id": "slot_001",
                        "name": "specific research paper screenshot",
                        "timeline_start_seconds": 4,
                        "timeline_end_seconds": 8,
                        "duration_seconds": 4,
                        "source": {"blockers": ["missing_manifest_asset"]},
                        "director": {"visual_role": "evidence"},
                    },
                    {
                        "clip_id": "broll_002",
                        "status": "resolved",
                        "cue_id": "slot_002",
                        "name": "real asset",
                        "timeline_start_seconds": 12,
                        "timeline_end_seconds": 16,
                        "duration_seconds": 4,
                        "source": {"logical_media_path": "multimedia/2026-09-24/assets/real.mp4"},
                        "director": {"visual_role": "context"},
                    },
                ],
            },
            {
                "track_id": "V1",
                "clips": [
                    {
                        "clip_id": "aroll_001",
                        "take_id": "opening_t01",
                        "replace_key": "opening_t01",
                        "timeline_start_seconds": 0,
                        "timeline_end_seconds": 10,
                        "duration_seconds": 10,
                        "section": {"section_label": "Apertura"},
                    },
                    {
                        "clip_id": "aroll_002",
                        "take_id": "opening_t02",
                        "replace_key": "opening_t02",
                        "timeline_start_seconds": 10,
                        "timeline_end_seconds": 20,
                        "duration_seconds": 10,
                        "section": {"section_label": "Apertura"},
                    },
                ],
            },
        ],
    }


class PlaceholderMediaTests(unittest.TestCase):
    def test_generates_every_v1_and_only_missing_v2(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "placeholder_media"
            payload = build_placeholder_manifest(
                virtual_timeline=virtual_payload(),
                output_dir=output,
                width=640,
                height=360,
            )
            self.assertEqual(payload["summary"]["presenter_placeholder_count"], 2)
            self.assertEqual(payload["summary"]["media_placeholder_count"], 1)
            self.assertEqual(payload["summary"]["placeholder_count"], 3)
            keys = {item["placeholder_id"] for item in payload["items"]}
            self.assertEqual(keys, {"take:opening_t01", "take:opening_t02", "cue:slot_001"})
            for item in payload["items"]:
                self.assertTrue((output / item["file"]).is_file())
                self.assertTrue(item["sha256"])
            self.assertTrue(payload["policy"]["resolved_media_is_never_replaced_by_placeholder"])

    def test_write_emits_manifest_and_pngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp) / "scripts" / "2026-09-24"
            episode.mkdir(parents=True)
            (episode / "virtual_timeline.json").write_text(
                json.dumps(virtual_payload()), encoding="utf-8"
            )
            directory, manifest = write_placeholder_media(
                episode_dir=episode,
                width=640,
                height=360,
            )
            self.assertTrue(manifest.is_file())
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["placeholder_count"], 3)
            self.assertTrue((directory / "v1" / "opening_t01.png").is_file())
            self.assertTrue((directory / "v2" / "slot_001.png").is_file())

    def test_duplicate_placeholder_identity_fails_closed(self):
        payload = virtual_payload()
        payload["tracks"][1]["clips"].append(dict(payload["tracks"][1]["clips"][0]))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "Duplicate presenter placeholder"):
                build_placeholder_manifest(
                    virtual_timeline=payload,
                    output_dir=Path(tmp),
                    width=640,
                    height=360,
                )


if __name__ == "__main__":
    unittest.main()
