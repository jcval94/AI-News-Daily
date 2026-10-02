import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.tts.engines import EngineError
from pipeline.tts.render import render_episode


class FallbackTests(unittest.TestCase):
    def _exercise_fallback(self, first_error):
        root = Path(tempfile.mkdtemp())
        episode = root / "scripts" / "2026-09-25"
        episode.mkdir(parents=True)
        (episode / "script.txt").write_text("Hola\n", encoding="utf-8")
        (episode / "script_sections.json").write_text(
            '{"schema_version":4,"sections":[]}',
            encoding="utf-8",
        )
        config = {
            "schema_version": 1,
            "tts": {
                "engine": "kokoro",
                "language": "es",
                "edit_sample_rate_hz": 48000,
                "speech": {
                    "speed": 1.0,
                    "pauses": {
                        "default_ms": 0,
                        "after_kind_ms": {},
                    },
                },
                "engines": {
                    "kokoro": {"voice": "ef_dora"},
                    "piper": {"voice": "es_MX-claude-high"},
                    "edge": {"voice": "es-MX-JorgeNeural"},
                },
                "fallback": {"enabled": True, "engine": "piper"},
                "pronunciation": {"entries": {}},
                "web": {"bitrate": "64k"},
            },
        }
        sections = [{
            "id": "opening",
            "order": 0,
            "section_key": "opening",
            "kind": "opening",
            "beat_id": None,
            "beat_kind": None,
            "evidence_ids": [],
            "source_text": "Hola",
            "source_text_sha256": "a" * 64,
            "spoken_text": "Hola",
            "spoken_text_sha256": "b" * 64,
            "filename_stem": "00_opening",
        }]
        record = {
            **{
                key: sections[0][key]
                for key in (
                    "id",
                    "order",
                    "section_key",
                    "kind",
                    "beat_id",
                    "beat_kind",
                    "evidence_ids",
                    "source_text",
                    "source_text_sha256",
                    "spoken_text",
                    "spoken_text_sha256",
                )
            },
            "engine": "piper",
            "voice": "es_MX-claude-high",
            "audio_native_file": "audio/native/sections/00_opening.wav",
            "audio_edit_file": "audio/edit/sections/00_opening.wav",
            "audio_web_file": "web/sections/00_opening.mp3",
            "start_seconds": 0.0,
            "end_seconds": 1.0,
            "duration_seconds": 1.0,
            "pause_after_seconds": 0.0,
            "timeline_end_seconds": 1.0,
            "generation_seconds": 0.5,
            "real_time_factor": 0.5,
            "native_audio": {},
            "edit_audio": {},
            "ffmpeg_audio": {},
            "qa": {"status": "pass", "warnings": []},
        }
        edit_path = root / "fake-edit.wav"

        def fake_concat(_paths, output, _pauses=None):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"wav")

        def fake_preview(_master, output, _bitrate):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"mp3")

        metrics = {
            "file_size_bytes": 100,
            "duration_seconds": 1.0,
            "sample_rate_hz": 48000,
            "channels": 1,
            "sample_width_bytes": 2,
            "peak_linear": 0.1,
            "peak_dbfs": -20.0,
            "rms_dbfs": -30.0,
            "clipping_suspected": False,
            "silent_suspected": False,
        }

        with (
            patch("pipeline.tts.render.load_tts_config", return_value=config),
            patch(
                "pipeline.tts.render.load_spoken_sections",
                return_value=(sections, {"schema_version": 4}),
            ),
            patch(
                "pipeline.tts.render._render_sections_with_engine",
                side_effect=[
                    first_error,
                    ([record], [edit_path], 1.0, 0.5, []),
                ],
            ) as render_sections,
            patch(
                "pipeline.tts.render._concat_wav",
                side_effect=fake_concat,
            ),
            patch(
                "pipeline.tts.render._web_preview",
                side_effect=fake_preview,
            ),
            patch(
                "pipeline.tts.render.inspect_wav",
                return_value=metrics,
            ),
            patch(
                "pipeline.tts.render.validate_edit_wav",
                return_value=[],
            ),
            patch(
                "pipeline.tts.render.write_manifest",
                side_effect=lambda path, payload: path,
            ),
        ):
            _path, manifest = render_episode(
                episode_dir=episode,
                config_path=root / "config.yaml",
                repo_root=root,
            )

        self.assertEqual(
            [
                call.kwargs["engine"]
                for call in render_sections.call_args_list
            ],
            ["kokoro", "piper"],
        )
        self.assertEqual(manifest["engine"]["used"], "piper")
        self.assertEqual(
            manifest["engine"]["voice"],
            "es_MX-claude-high",
        )
        self.assertIn(
            "fallback_used:kokoro->piper",
            manifest["qa"]["warnings"],
        )
        self.assertTrue(
            manifest["errors"][0].startswith("kokoro:")
        )
        self.assertTrue(
            all(
                item["engine"] == "piper"
                for item in manifest["sections"]
            )
        )
        return manifest

    def test_fallback_restarts_the_whole_run_with_one_engine(self):
        self._exercise_fallback(
            EngineError("kokoro unavailable")
        )

    def test_invalid_audio_validation_error_also_triggers_full_run_fallback(self):
        manifest = self._exercise_fallback(
            ValueError("WAV missing or empty")
        )
        self.assertIn(
            "WAV missing or empty",
            manifest["errors"][0],
        )


if __name__ == "__main__":
    unittest.main()
