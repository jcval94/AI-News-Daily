import json
import tempfile
import unittest
from pathlib import Path

from pipeline.edit_manifest import build_edit_manifest, write_edit_manifest


def _sections():
    return {
        "schema_version": 2,
        "sections": [
            {
                "section_key": "opening",
                "kind": "opening",
                "beat_id": None,
                "beat_kind": None,
                "evidence_ids": [],
                "spoken_text": "uno dos tres cuatro cinco seis siete ocho nueve diez",
                "word_count": 10,
            },
            {
                "section_key": "beat:evidence",
                "kind": "development",
                "beat_id": "evidence",
                "beat_kind": "evidence",
                "evidence_ids": ["ev1"],
                "spoken_text": "once doce trece catorce quince dieciseis diecisiete dieciocho diecinueve veinte",
                "word_count": 10,
            },
        ],
    }


class EditManifestTests(unittest.TestCase):
    def test_builds_presenter_and_media_timeline(self):
        payload = build_edit_manifest(
            episode_date="2026-09-24",
            script="uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis diecisiete dieciocho diecinueve veinte",
            script_sections=_sections(),
            media_plan={
                "segments": [
                    {
                        "slot_number": 7,
                        "mode": "media",
                        "start_seconds": 2.0,
                        "end_seconds": 4.0,
                        "visual_query": "archival research documents",
                        "on_screen_text": "La evidencia",
                        "reason": "Make the evidence concrete",
                        "visual_role": "evidence",
                        "transition_in": "hard_cut",
                        "transition_out": "hard_cut",
                        "treatment": "slow_push_in",
                        "pacing": "normal",
                        "director_note": "Hold long enough to read the document.",
                    }
                ]
            },
            media_manifest=[
                {
                    "shot_number": 7,
                    "file": "B01_evidence/S007.jpg",
                    "asset_type": "image",
                    "mime_type": "image/jpeg",
                    "provider": "wikimedia_commons",
                    "license": "CC BY-SA 4.0",
                    "license_valid": True,
                }
            ],
            words_per_second=2.0,
        )

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["status"], "pre_recording")
        self.assertTrue(payload["timing"]["requires_recording_retime"])
        self.assertTrue(payload["sources"]["script_sha256"])
        self.assertEqual(
            [item["mode"] for item in payload["timeline"]],
            ["presenter", "media", "presenter", "presenter"],
        )
        media = next(item for item in payload["timeline"] if item["mode"] == "media")
        self.assertEqual(media["cue_id"], "slot_007")
        self.assertEqual(media["media"]["file"], "B01_evidence/S007.jpg")
        self.assertEqual(media["director"]["visual_role"], "evidence")
        self.assertEqual(
            media["director"]["note"], "Hold long enough to read the document."
        )
        self.assertTrue(media["script_anchor"]["excerpt"])

    def test_missing_asset_is_visible_not_silently_green(self):
        payload = build_edit_manifest(
            episode_date="2026-09-24",
            script="uno dos tres cuatro cinco seis siete ocho nueve diez",
            script_sections={
                "sections": [
                    {
                        "section_key": "opening",
                        "kind": "opening",
                        "spoken_text": "uno dos tres cuatro cinco seis siete ocho nueve diez",
                        "word_count": 10,
                        "evidence_ids": [],
                    }
                ]
            },
            media_plan={
                "segments": [
                    {
                        "slot_number": 1,
                        "mode": "media",
                        "start_seconds": 0,
                        "end_seconds": 2,
                        "visual_query": "documentary notes",
                        "reason": "Cold open",
                    }
                ]
            },
            media_manifest=[],
            words_per_second=2.0,
        )

        media = payload["timeline"][0]
        self.assertEqual(media["mode"], "media")
        self.assertFalse(media["media"]["available"])
        self.assertIn(
            "no downloaded asset",
            " ".join(payload["validation_warnings"]).lower(),
        )


    def test_rejects_stale_script_sections(self):
        with self.assertRaisesRegex(ValueError, "does not match script.txt"):
            build_edit_manifest(
                episode_date="2026-09-24",
                script="texto nuevo",
                script_sections={
                    "sections": [
                        {
                            "section_key": "opening",
                            "kind": "opening",
                            "spoken_text": "texto viejo",
                            "word_count": 2,
                            "evidence_ids": [],
                        }
                    ]
                },
                media_plan={"segments": []},
                media_manifest=[],
                words_per_second=2.0,
            )

    def test_rejects_duplicate_media_slots(self):
        with self.assertRaisesRegex(ValueError, "Duplicate media cue"):
            build_edit_manifest(
                episode_date="2026-09-24",
                script="uno dos tres cuatro cinco seis siete ocho nueve diez",
                script_sections={
                    "sections": [
                        {
                            "section_key": "opening",
                            "kind": "opening",
                            "spoken_text": "uno dos tres cuatro cinco seis siete ocho nueve diez",
                            "word_count": 10,
                            "evidence_ids": [],
                        }
                    ]
                },
                media_plan={
                    "segments": [
                        {
                            "slot_number": 1,
                            "mode": "media",
                            "start_seconds": 0,
                            "end_seconds": 1,
                            "visual_query": "notes",
                        },
                        {
                            "slot_number": 1,
                            "mode": "media",
                            "start_seconds": 2,
                            "end_seconds": 3,
                            "visual_query": "documents",
                        },
                    ]
                },
                media_manifest=[],
                words_per_second=2.0,
            )

    def test_missing_preferred_video_keeps_video_treatment(self):
        payload = build_edit_manifest(
            episode_date="2026-09-24",
            script="uno dos tres cuatro cinco seis siete ocho nueve diez",
            script_sections={
                "sections": [
                    {
                        "section_key": "opening",
                        "kind": "opening",
                        "spoken_text": "uno dos tres cuatro cinco seis siete ocho nueve diez",
                        "word_count": 10,
                        "evidence_ids": [],
                    }
                ]
            },
            media_plan={
                "segments": [
                    {
                        "slot_number": 1,
                        "mode": "media",
                        "start_seconds": 0,
                        "end_seconds": 2,
                        "visual_query": "moving documentary footage",
                        "preferred_asset_type": "video",
                        "motion_preference": "high",
                        "slot_priority": "opening_dense_media",
                        "reason": "Cold-open rhythm",
                    }
                ]
            },
            media_manifest=[],
            words_per_second=2.0,
        )
        media = payload["timeline"][0]
        self.assertEqual(media["director"]["treatment"], "natural_motion")
        self.assertFalse(payload["readiness"]["asset_resolution_complete"])
        self.assertIn("recording_retime_required", payload["readiness"]["blockers"])

    def test_write_manifest_verifies_physical_media_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode_dir = root / "scripts" / "2026-09-24"
            media_dir = root / "multimedia" / "2026-09-24"
            episode_dir.mkdir(parents=True)
            media_dir.mkdir(parents=True)
            script = "uno dos tres cuatro"
            (episode_dir / "script.txt").write_text(script, encoding="utf-8")
            (episode_dir / "script_sections.json").write_text(
                json.dumps(
                    {
                        "sections": [
                            {
                                "section_key": "opening",
                                "kind": "opening",
                                "spoken_text": script,
                                "word_count": 4,
                                "evidence_ids": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (episode_dir / "run_state.json").write_text(
                json.dumps({"episode_date": "2026-09-24"}),
                encoding="utf-8",
            )
            (media_dir / "plan.json").write_text(
                json.dumps(
                    {
                        "script_date": "2026-09-24",
                        "segments": [
                            {
                                "slot_number": 1,
                                "mode": "media",
                                "start_seconds": 0,
                                "end_seconds": 1,
                                "visual_query": "document",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (media_dir / "manifest.json").write_text(
                json.dumps(
                    [
                        {
                            "shot_number": 1,
                            "file": "assets/missing.jpg",
                            "asset_type": "image",
                            "license": "CC0",
                            "license_valid": True,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            destination = write_edit_manifest(
                episode_dir=episode_dir,
                media_dir=media_dir,
                words_per_second=2.0,
            )
            payload = json.loads(destination.read_text(encoding="utf-8"))
            media = payload["timeline"][0]["media"]
            self.assertFalse(media["file_exists"])
            self.assertFalse(media["usable_for_edit"])
            self.assertIn("missing_file", media["blockers"])
            self.assertEqual(payload["summary"]["blocked_media_cue_count"], 1)



if __name__ == "__main__":
    unittest.main()
