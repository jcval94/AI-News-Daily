import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.recording_ingest import (
    build_recording_ingest_contract,
    parse_capture_filename,
    scan_recordings,
    write_ingest_contract,
    write_ingest_manifest,
)


def recording_pack():
    return {
        "episode_date": "2026-09-24",
        "capture_recommendation": {
            "resolution": "3840x2160",
            "frame_rate_fps": 30,
            "audio_sample_rate_hz": 48000,
        },
        "recording_protocol": {
            "pre_roll_seconds": 2.0,
            "post_roll_seconds": 2.0,
        },
        "takes": [
            {
                "take_id": "opening_t01",
                "section_label": "Apertura",
                "spoken_slate": "TAKE opening_t01",
                "estimated_duration_seconds": 4.0,
            },
            {
                "take_id": "opening_t02",
                "section_label": "Apertura",
                "spoken_slate": "TAKE opening_t02",
                "estimated_duration_seconds": 4.0,
            },
        ],
    }


def _run(command):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)


def _video(path: Path, *, size: str, duration: float, audio: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={size}:r=30:d={duration}",
    ]
    if audio:
        command += [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration}",
            "-shortest",
        ]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        command += ["-c:a", "aac"]
    command.append(str(path))
    _run(command)


def _audio(path: Path, *, duration: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        shutil.which("ffmpeg"),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=880:sample_rate=48000:duration={duration}",
        "-c:a",
        "pcm_s16le",
        str(path),
    ])


class RecordingIngestContractTests(unittest.TestCase):
    def test_contract_is_stable_and_never_claims_alignment_ready(self):
        contract = build_recording_ingest_contract(recording_pack())
        self.assertEqual(contract["summary"]["expected_take_count"], 2)
        self.assertTrue(contract["storage"]["never_commit_raw_recordings"])
        self.assertTrue(contract["selection_policy"]["retain_all_retakes"])
        self.assertEqual(
            contract["selection_policy"]["authority"],
            "technical_only_not_performance_or_script_accuracy",
        )
        self.assertFalse(contract["readiness"]["ready_for_alignment"])
        self.assertIn("recorded_media_required", contract["readiness"]["blockers"])
        self.assertEqual(
            contract["expected_takes"][0]["examples"]["video_retake"],
            "opening_t01__r02__camA.mov",
        )

    def test_filename_parser_preserves_take_and_retake_identity(self):
        video = parse_capture_filename(Path("opening_t01__r03__camA.mov"))
        audio = parse_capture_filename(Path("opening_t01__r03__lav.wav"))
        unmatched = parse_capture_filename(Path("random camera file.mp4"))
        self.assertEqual(video["take_id"], "opening_t01")
        self.assertEqual(video["retake_number"], 3)
        self.assertEqual(video["media_type"], "video")
        self.assertEqual(audio["media_type"], "audio")
        self.assertFalse(unmatched["matched"])

    def test_write_contract_emits_json_and_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            episode = Path(tmp) / "scripts" / "2026-09-24"
            episode.mkdir(parents=True)
            (episode / "recording_pack.json").write_text(
                json.dumps(recording_pack()), encoding="utf-8"
            )
            json_path, md_path, payload = write_ingest_contract(episode_dir=episode)
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertEqual(payload["summary"]["expected_take_count"], 2)
            instructions = md_path.read_text(encoding="utf-8")
            self.assertIn("opening_t01__r01__camA.mov", instructions)
            self.assertIn("scanner sólo lee", instructions)



class RecordingIngestScannerDeterministicTests(unittest.TestCase):
    def _contract(self):
        contract = build_recording_ingest_contract(recording_pack())
        for item in contract["expected_takes"]:
            item["expected_capture_seconds"] = 10.0
        return contract

    def _files(self, root: Path):
        inbox = root / "inbox"
        inbox.mkdir(parents=True)
        names = [
            "opening_t01__r01__camA.mp4",
            "opening_t01__r02__camA.mp4",
            "opening_t01__r02__audio.wav",
            "opening_t02__r01__camA.mp4",
        ]
        for name in names:
            (inbox / name).write_bytes(("fixture-" + name).encode("utf-8"))
        return inbox

    def _video_inspection(self, path: Path):
        if "__r01__camA" in path.name and path.name.startswith("opening_t01"):
            return {
                "ok": True,
                "kind": "video",
                "width": 640,
                "height": 360,
                "duration_seconds": 10.0,
                "codec": "h264",
                "r_frame_rate": "30/1",
                "has_audio_stream": True,
                "audio_codec": "aac",
                "audio_sample_rate_hz": 48000,
                "audio_channels": 2,
            }
        return {
            "ok": True,
            "kind": "video",
            "width": 1920,
            "height": 1080,
            "duration_seconds": 10.0,
            "codec": "h264",
            "r_frame_rate": "30/1",
            "has_audio_stream": path.name.startswith("opening_t02"),
            "audio_codec": "aac" if path.name.startswith("opening_t02") else "",
            "audio_sample_rate_hz": 48000 if path.name.startswith("opening_t02") else 0,
            "audio_channels": 2 if path.name.startswith("opening_t02") else 0,
        }

    @patch("pipeline.recording_ingest.inspect_audio")
    @patch("pipeline.recording_ingest.inspect_media")
    def test_selection_logic_is_ci_enforced_without_ffmpeg(
        self, inspect_video_mock, inspect_audio_mock
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = self._files(root)
            inspect_video_mock.side_effect = self._video_inspection
            inspect_audio_mock.return_value = {
                "ok": True,
                "kind": "audio",
                "duration_seconds": 10.0,
                "codec": "pcm_s16le",
                "sample_rate_hz": 48000,
                "channels": 2,
            }
            manifest = scan_recordings(
                contract=self._contract(),
                input_dir=inbox,
            )
            self.assertTrue(manifest["readiness"]["ready_for_alignment"])
            first = next(
                item for item in manifest["takes"] if item["take_id"] == "opening_t01"
            )
            self.assertEqual(first["technical_preferred_retake"], 2)
            self.assertEqual(first["retake_count"], 2)
            self.assertEqual(
                first["technical_preferred"]["selected_video"]["relative_path"],
                "opening_t01__r02__camA.mp4",
            )
            self.assertEqual(
                first["technical_preferred"]["audio_source"],
                "external",
            )
            self.assertEqual(len(first["candidates"]), 2)

    @patch("pipeline.recording_ingest.inspect_audio")
    @patch("pipeline.recording_ingest.inspect_media")
    def test_persisted_manifest_passes_schema_without_absolute_paths(
        self, inspect_video_mock, inspect_audio_mock
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = self._files(root)
            inspect_video_mock.side_effect = self._video_inspection
            inspect_audio_mock.return_value = {
                "ok": True,
                "kind": "audio",
                "duration_seconds": 10.0,
                "codec": "pcm_s16le",
                "sample_rate_hz": 48000,
                "channels": 2,
            }
            episode = root / "scripts" / "2026-09-24"
            episode.mkdir(parents=True)
            (episode / "recording_ingest_contract.json").write_text(
                json.dumps(self._contract()),
                encoding="utf-8",
            )
            manifest_path, manifest = write_ingest_manifest(
                episode_dir=episode,
                input_dir=inbox,
                enforce=True,
            )
            self.assertTrue(manifest["readiness"]["ready_for_alignment"])
            serialized = manifest_path.read_text(encoding="utf-8")
            self.assertNotIn(str(root), serialized)
            self.assertIn('"absolute_input_path_persisted": false', serialized)

    @patch("pipeline.recording_ingest.inspect_audio")
    @patch("pipeline.recording_ingest.inspect_media")
    def test_short_external_audio_falls_back_to_embedded_audio(
        self, inspect_video_mock, inspect_audio_mock
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "inbox"
            inbox.mkdir()
            for take_id in ("opening_t01", "opening_t02"):
                (inbox / f"{take_id}__r01__camA.mp4").write_bytes(b"video")
            (inbox / "opening_t01__r01__audio.wav").write_bytes(b"audio")
            inspect_video_mock.return_value = {
                "ok": True,
                "kind": "video",
                "width": 1920,
                "height": 1080,
                "duration_seconds": 10.0,
                "codec": "h264",
                "r_frame_rate": "30/1",
                "has_audio_stream": True,
                "audio_codec": "aac",
                "audio_sample_rate_hz": 48000,
                "audio_channels": 2,
            }
            inspect_audio_mock.return_value = {
                "ok": True,
                "kind": "audio",
                "duration_seconds": 1.0,
                "codec": "pcm_s16le",
                "sample_rate_hz": 48000,
                "channels": 2,
            }
            manifest = scan_recordings(
                contract=self._contract(),
                input_dir=inbox,
            )
            self.assertTrue(manifest["readiness"]["ready_for_alignment"])
            first = next(
                item for item in manifest["takes"] if item["take_id"] == "opening_t01"
            )
            self.assertEqual(first["technical_preferred"]["audio_source"], "embedded")
            self.assertIsNone(
                first["technical_preferred"]["selected_external_audio"]
            )
            self.assertIn(
                "external_audio_too_short",
                first["technical_preferred"]["issues"],
            )

    @patch("pipeline.recording_ingest.inspect_audio")
    @patch("pipeline.recording_ingest.inspect_media")
    def test_short_external_audio_blocks_when_no_embedded_audio_exists(
        self, inspect_video_mock, inspect_audio_mock
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "inbox"
            inbox.mkdir()
            for take_id in ("opening_t01", "opening_t02"):
                (inbox / f"{take_id}__r01__camA.mp4").write_bytes(b"video")
                (inbox / f"{take_id}__r01__audio.wav").write_bytes(b"audio")
            inspect_video_mock.return_value = {
                "ok": True,
                "kind": "video",
                "width": 1920,
                "height": 1080,
                "duration_seconds": 10.0,
                "codec": "h264",
                "r_frame_rate": "30/1",
                "has_audio_stream": False,
                "audio_codec": "",
                "audio_sample_rate_hz": 0,
                "audio_channels": 0,
            }
            inspect_audio_mock.return_value = {
                "ok": True,
                "kind": "audio",
                "duration_seconds": 1.0,
                "codec": "pcm_s16le",
                "sample_rate_hz": 48000,
                "channels": 2,
            }
            manifest = scan_recordings(
                contract=self._contract(),
                input_dir=inbox,
            )
            self.assertFalse(manifest["readiness"]["ready_for_alignment"])
            self.assertIn(
                "no_usable_candidate:opening_t01",
                manifest["readiness"]["blockers"],
            )
            self.assertIn("external_audio_too_short", manifest["readiness"]["warnings"])

    @patch("pipeline.recording_ingest.inspect_media")
    def test_missing_audio_source_makes_candidate_unusable(self, inspect_video_mock):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "inbox"
            inbox.mkdir()
            (inbox / "opening_t01__r01__camA.mp4").write_bytes(b"video")
            (inbox / "opening_t02__r01__camA.mp4").write_bytes(b"video")
            inspect_video_mock.return_value = {
                "ok": True,
                "kind": "video",
                "width": 1920,
                "height": 1080,
                "duration_seconds": 10.0,
                "codec": "h264",
                "r_frame_rate": "30/1",
                "has_audio_stream": False,
                "audio_codec": "",
                "audio_sample_rate_hz": 0,
                "audio_channels": 0,
            }
            manifest = scan_recordings(
                contract=self._contract(),
                input_dir=inbox,
            )
            self.assertFalse(manifest["readiness"]["ready_for_alignment"])
            self.assertIn(
                "no_usable_candidate:opening_t01",
                manifest["readiness"]["blockers"],
            )
            self.assertIn(
                "no_usable_candidate:opening_t02",
                manifest["readiness"]["blockers"],
            )
            first = manifest["takes"][0]["candidates"][0]
            self.assertIn("missing_audio_source", first["issues"])

    @patch("pipeline.recording_ingest.inspect_media")
    def test_implausibly_short_capture_is_not_alignment_ready(self, inspect_video_mock):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "inbox"
            inbox.mkdir()
            for take_id in ("opening_t01", "opening_t02"):
                (inbox / f"{take_id}__r01__camA.mp4").write_bytes(b"video")
            inspect_video_mock.return_value = {
                "ok": True,
                "kind": "video",
                "width": 1920,
                "height": 1080,
                "duration_seconds": 2.0,
                "codec": "h264",
                "r_frame_rate": "30/1",
                "has_audio_stream": True,
                "audio_codec": "aac",
                "audio_sample_rate_hz": 48000,
                "audio_channels": 2,
            }
            manifest = scan_recordings(
                contract=self._contract(),
                input_dir=inbox,
            )
            self.assertFalse(manifest["readiness"]["ready_for_alignment"])
            self.assertIn("capture_too_short", manifest["readiness"]["warnings"])
            self.assertTrue(
                all(
                    take["technical_preferred"] is None
                    for take in manifest["takes"]
                )
            )


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg unavailable")
class RecordingIngestScannerTests(unittest.TestCase):
    def _fixture(self, root: Path, *, include_second_take: bool = True):
        inbox = root / "inbox"
        contract = build_recording_ingest_contract(recording_pack())
        for take in contract["expected_takes"]:
            take["expected_capture_seconds"] = 1.5

        _video(
            inbox / "opening_t01__r01__camA.mp4",
            size="640x360",
            duration=1.5,
            audio=True,
        )
        _video(
            inbox / "opening_t01__r02__camA.mp4",
            size="1280x720",
            duration=1.5,
            audio=False,
        )
        _audio(
            inbox / "opening_t01__r02__audio.wav",
            duration=1.5,
        )
        if include_second_take:
            _video(
                inbox / "opening_t02__r01__camA.mp4",
                size="1280x720",
                duration=1.5,
                audio=True,
            )
        return inbox, contract

    def test_scanner_selects_technical_candidate_and_preserves_all_retakes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox, contract = self._fixture(root)
            manifest = scan_recordings(contract=contract, input_dir=inbox)

            self.assertTrue(manifest["readiness"]["ready_for_alignment"])
            first = next(x for x in manifest["takes"] if x["take_id"] == "opening_t01")
            self.assertEqual(first["retake_count"], 2)
            self.assertEqual(first["technical_preferred_retake"], 2)
            self.assertEqual(first["technical_preferred"]["audio_source"], "external")
            self.assertEqual(len(first["candidates"]), 2)
            self.assertEqual(
                first["technical_preferred"]["selected_video"]["relative_path"],
                "opening_t01__r02__camA.mp4",
            )
            self.assertEqual(
                first["technical_preferred"]["selected_external_audio"]["relative_path"],
                "opening_t01__r02__audio.wav",
            )

    def test_missing_take_blocks_alignment_without_losing_other_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox, contract = self._fixture(root, include_second_take=False)
            manifest = scan_recordings(contract=contract, input_dir=inbox)
            self.assertFalse(manifest["readiness"]["ready_for_alignment"])
            self.assertIn("missing_take:opening_t02", manifest["readiness"]["blockers"])
            first = next(x for x in manifest["takes"] if x["take_id"] == "opening_t01")
            self.assertIsNotNone(first["technical_preferred"])

    def test_manifest_never_persists_absolute_machine_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox, contract = self._fixture(root)
            manifest = scan_recordings(contract=contract, input_dir=inbox)
            serialized = json.dumps(manifest)
            self.assertNotIn(str(root), serialized)
            self.assertFalse(manifest["source"]["absolute_input_path_persisted"])

    def test_write_manifest_validates_schema_and_persists_only_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox, contract = self._fixture(root)
            episode = root / "scripts" / "2026-09-24"
            episode.mkdir(parents=True)
            (episode / "recording_ingest_contract.json").write_text(
                json.dumps(contract),
                encoding="utf-8",
            )
            manifest_path, manifest = write_ingest_manifest(
                episode_dir=episode,
                input_dir=inbox,
                enforce=True,
            )
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(manifest["readiness"]["ready_for_alignment"])
            saved = manifest_path.read_text(encoding="utf-8")
            self.assertNotIn(str(root), saved)
            self.assertIn("opening_t01__r02__camA.mp4", saved)

    def test_unknown_take_id_is_a_blocker_and_unmatched_file_is_only_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox, contract = self._fixture(root)
            _video(
                inbox / "unknown_t99__r01__camA.mp4",
                size="640x360",
                duration=1.0,
                audio=True,
            )
            _video(
                inbox / "camera dump.mp4",
                size="640x360",
                duration=1.0,
                audio=True,
            )
            manifest = scan_recordings(contract=contract, input_dir=inbox)
            self.assertFalse(manifest["readiness"]["ready_for_alignment"])
            self.assertIn("unknown_take_id:unknown_t99", manifest["readiness"]["blockers"])
            self.assertEqual(manifest["summary"]["unmatched_media_file_count"], 1)
            self.assertIn("unmatched_files:1", manifest["readiness"]["warnings"])


if __name__ == "__main__":
    unittest.main()
