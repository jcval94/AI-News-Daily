import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.whisperx_adapter import (
    build_transcript_bundle,
    normalize_whisperx_result,
    whisperx_command,
)


class WhisperXAdapterTests(unittest.TestCase):
    def test_normalizes_segment_words(self):
        payload = {
            "language": "es",
            "segments": [
                {
                    "text": "Hola mundo.",
                    "words": [
                        {"word": "Hola", "start": 0.2, "end": 0.5, "score": 0.91},
                        {"word": "mundo.", "start": 0.55, "end": 0.9, "score": 0.88},
                    ],
                }
            ],
        }
        item = normalize_whisperx_result(
            payload,
            take_id="opening_t01",
            retake_number=2,
            source_relative_path="opening_t01__r02__camA.mp4",
            timebase="video_source",
        )
        self.assertEqual(item["take_id"], "opening_t01")
        self.assertEqual(item["retake_number"], 2)
        self.assertEqual(item["timebase"], "video_source")
        self.assertEqual(len(item["words"]), 2)
        self.assertEqual(item["text"], "Hola mundo.")

    def test_prefers_top_level_word_segments_when_available(self):
        payload = {
            "language": "es",
            "segments": [{"text": "Hola mundo.", "words": []}],
            "word_segments": [
                {"word": "Hola", "start": 0.1, "end": 0.4, "score": 0.9},
                {"word": "mundo", "start": 0.5, "end": 0.8, "score": 0.8},
            ],
        }
        item = normalize_whisperx_result(
            payload,
            take_id="opening_t01",
            retake_number=1,
            source_relative_path="opening.mp4",
            timebase="video_source",
        )
        self.assertEqual(
            item["provider_metadata"]["word_timestamp_source"],
            "word_segments",
        )

    def test_command_keeps_alignment_enabled_and_uses_json(self):
        command = whisperx_command(
            executable="whisperx",
            media_path=Path("clip.mp4"),
            output_dir=Path("out"),
            model="large-v3",
            language="es",
            device="cuda",
            compute_type="float16",
            batch_size=8,
            vad_method="silero",
        )
        self.assertEqual(command[0], "whisperx")
        self.assertIn("--output_format", command)
        self.assertIn("json", command)
        self.assertNotIn("--no_align", command)
        self.assertIn("--vad_method", command)
        self.assertIn("silero", command)

    @patch("pipeline.whisperx_adapter._transcribe_one")
    def test_bundle_prefers_video_scratch_audio_over_external_audio(
        self, transcribe_mock
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "opening_t01__r01__camA.mp4",
                "opening_t01__r01__audio.wav",
            ):
                (root / name).write_bytes(b"x")
            transcribe_mock.side_effect = lambda **kwargs: {
                "take_id": kwargs["take_id"],
                "retake_number": kwargs["retake_number"],
                "source_relative_path": kwargs["source_relative_path"],
                "timebase": kwargs["timebase"],
                "language": "es",
                "text": "hola",
                "words": [{"word": "hola", "start": 0.1, "end": 0.3, "score": 0.9}],
            }
            manifest = {
                "episode_date": "2026-09-25",
                "takes": [
                    {
                        "take_id": "opening_t01",
                        "candidates": [
                            {
                                "retake_number": 1,
                                "status": "usable_technical",
                                "selected_video": {
                                    "relative_path": "opening_t01__r01__camA.mp4",
                                    "inspection": {"has_audio_stream": True},
                                },
                                "selected_external_audio": {
                                    "relative_path": "opening_t01__r01__audio.wav",
                                    "inspection": {"ok": True},
                                },
                            }
                        ],
                    }
                ],
            }
            bundle = build_transcript_bundle(
                ingest_manifest=manifest,
                recordings_root=root,
                executable="whisperx",
            )
            self.assertEqual(bundle["items"][0]["timebase"], "video_source")
            self.assertEqual(
                bundle["items"][0]["source_relative_path"],
                "opening_t01__r01__camA.mp4",
            )
            kwargs = transcribe_mock.call_args.kwargs
            self.assertEqual(kwargs["timebase"], "video_source")

    @patch("pipeline.whisperx_adapter._transcribe_one")
    def test_bundle_uses_external_timebase_only_without_camera_scratch_audio(
        self, transcribe_mock
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "opening_t01__r01__camA.mp4",
                "opening_t01__r01__audio.wav",
            ):
                (root / name).write_bytes(b"x")
            transcribe_mock.side_effect = lambda **kwargs: {
                "take_id": kwargs["take_id"],
                "retake_number": kwargs["retake_number"],
                "source_relative_path": kwargs["source_relative_path"],
                "timebase": kwargs["timebase"],
                "language": "es",
                "text": "hola",
                "words": [{"word": "hola", "start": 0.1, "end": 0.3, "score": 0.9}],
            }
            manifest = {
                "episode_date": "2026-09-25",
                "takes": [
                    {
                        "take_id": "opening_t01",
                        "candidates": [
                            {
                                "retake_number": 1,
                                "status": "usable_technical",
                                "selected_video": {
                                    "relative_path": "opening_t01__r01__camA.mp4",
                                    "inspection": {"has_audio_stream": False},
                                },
                                "selected_external_audio": {
                                    "relative_path": "opening_t01__r01__audio.wav",
                                    "inspection": {"ok": True},
                                },
                            }
                        ],
                    }
                ],
            }
            bundle = build_transcript_bundle(
                ingest_manifest=manifest,
                recordings_root=root,
                executable="whisperx",
            )
            self.assertEqual(
                bundle["items"][0]["timebase"],
                "external_audio_source",
            )
            self.assertEqual(
                bundle["items"][0]["source_relative_path"],
                "opening_t01__r01__audio.wav",
            )

    def test_rejects_non_monotonic_word_timestamps(self):
        with self.assertRaisesRegex(ValueError, "not monotonic"):
            normalize_whisperx_result(
                {
                    "language": "es",
                    "word_segments": [
                        {"word": "uno", "start": 1.0, "end": 2.0},
                        {"word": "dos", "start": 1.2, "end": 1.5},
                    ],
                },
                take_id="opening_t01",
                retake_number=1,
                source_relative_path="clip.mp4",
            )


if __name__ == "__main__":
    unittest.main()
