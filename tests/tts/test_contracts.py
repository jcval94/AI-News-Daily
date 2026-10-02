import unittest

from pipeline.tts.contracts import validate_manifest


def manifest():
    sections = [
        {
            "id": "opening",
            "order": 0,
            "section_key": "opening",
            "source_text": "Hola",
            "spoken_text": "Hola",
            "audio_native_file": "audio/native/sections/00_opening.wav",
            "audio_edit_file": "audio/edit/sections/00_opening.wav",
            "start_seconds": 0.0,
            "end_seconds": 1.25,
            "duration_seconds": 1.25,
            "qa": {"status": "pass", "warnings": []},
        },
        {
            "id": "beat:x",
            "order": 1,
            "section_key": "beat:x",
            "source_text": "Mundo",
            "spoken_text": "Mundo",
            "audio_native_file": "audio/native/sections/01_beat-x.wav",
            "audio_edit_file": "audio/edit/sections/01_beat-x.wav",
            "start_seconds": 1.25,
            "end_seconds": 3.0,
            "duration_seconds": 1.75,
            "qa": {"status": "pass", "warnings": []},
        },
    ]
    return {
        "schema_version": "1.0",
        "manifest_id": "tts:2026-09-25:test",
        "run_id": "test",
        "script_id": "a" * 64,
        "episode_date": "2026-09-25",
        "generated_at_utc": "2026-09-29T00:00:00Z",
        "status": "complete",
        "engine": {
            "requested": "kokoro",
            "used": "kokoro",
            "voice": "ef_dora",
            "language": "es",
            "local_first": True,
            "network_required": False,
        },
        "render": {
            "edit_sample_rate_hz": 48000,
            "channels": 1,
            "sample_format": "pcm_s16le",
            "speed": 1.0,
        },
        "source": {
            "script_path": "scripts/2026-09-25/script.txt",
            "sections_path": "scripts/2026-09-25/script_sections.json",
            "sections_schema_version": 4,
        },
        "files": {
            "master_edit": "audio/edit/narration_master.wav",
            "web_preview": "web/narration_preview.mp3",
        },
        "sections": sections,
        "metrics": {
            "section_count": 2,
            "duration_seconds": 3.0,
            "generation_seconds": 0.5,
            "real_time_factor": 0.1667,
            "web_preview_size_bytes": 1234,
        },
        "qa": {
            "status": "pass",
            "warnings": [],
            "master": {},
        },
        "errors": [],
    }


class NarrationContractTests(unittest.TestCase):
    def test_valid_contiguous_manifest(self):
        validate_manifest(manifest())

    def test_pause_aware_manifest_keeps_spoken_and_timeline_time_separate(self):
        payload = manifest()
        payload["schema_version"] = "1.1"
        payload["sections"][0]["pause_after_seconds"] = 0.35
        payload["sections"][0]["timeline_end_seconds"] = 1.60
        payload["sections"][1]["start_seconds"] = 1.60
        payload["sections"][1]["end_seconds"] = 3.35
        payload["sections"][1]["pause_after_seconds"] = 0.0
        payload["sections"][1]["timeline_end_seconds"] = 3.35
        payload["metrics"]["duration_seconds"] = 3.35
        payload["metrics"]["spoken_duration_seconds"] = 3.0
        payload["metrics"]["pause_duration_seconds"] = 0.35
        validate_manifest(payload)

    def test_pause_timeline_mismatch_is_rejected(self):
        payload = manifest()
        payload["schema_version"] = "1.1"
        payload["sections"][0]["pause_after_seconds"] = 0.35
        payload["sections"][0]["timeline_end_seconds"] = 1.50
        with self.assertRaisesRegex(
            ValueError,
            "pause mismatch",
        ):
            validate_manifest(payload)

    def test_timestamp_gap_is_rejected(self):
        payload = manifest()
        payload["sections"][1]["start_seconds"] = 1.5
        with self.assertRaisesRegex(
            ValueError,
            "not contiguous",
        ):
            validate_manifest(payload)

    def test_duration_arithmetic_is_rejected(self):
        payload = manifest()
        payload["sections"][1]["duration_seconds"] = 1.0
        with self.assertRaisesRegex(
            ValueError,
            "duration mismatch",
        ):
            validate_manifest(payload)

    def test_section_count_must_match(self):
        payload = manifest()
        payload["metrics"]["section_count"] = 3
        with self.assertRaisesRegex(
            ValueError,
            "section_count",
        ):
            validate_manifest(payload)


if __name__ == "__main__":
    unittest.main()
