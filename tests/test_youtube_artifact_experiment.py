from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.youtube_artifacts import EXPECTED_CATALOG_SIZE
from experiments.youtube_artifacts.download import (
    build_manifest,
    build_yt_dlp_command,
    load_catalog,
    sanitized_metadata,
    sha256_file,
    verify_metadata,
    write_supporting_files,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "experiments" / "youtube_artifacts" / "catalog.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "youtube-artifact-experiment.yml"


class YouTubeArtifactExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog(CATALOG_PATH)

    def test_catalog_has_ten_unique_rights_curated_entries(self) -> None:
        items = self.catalog["items"]
        self.assertEqual(EXPECTED_CATALOG_SIZE, len(items))
        self.assertEqual(list(range(1, 11)), [item["ordinal"] for item in items])
        self.assertEqual(10, len({item["video_id"] for item in items}))
        self.assertEqual(5, sum(item["cohort"] == "famous_open_movie" for item in items))
        self.assertEqual(5, sum(item["cohort"] == "random_cc" for item in items))
        self.assertTrue(
            all(item["license_evidence"]["basis"] in {"youtube_metadata", "publisher_license"} for item in items)
        )

    def test_catalog_rejects_duplicate_video_ids(self) -> None:
        payload = copy.deepcopy(self.catalog)
        payload["items"][1]["video_id"] = payload["items"][0]["video_id"]
        payload["items"][1]["source_url"] = payload["items"][0]["source_url"]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate YouTube video_id"):
                load_catalog(path)

    def test_workflow_is_ephemeral_and_has_no_production_promotion(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("retention-days: 7", workflow)
        self.assertIn("compression-level: 0", workflow)
        self.assertIn("--required-successes 10", workflow)
        self.assertIn("inputs.runner || 'ubuntu-latest'", workflow)
        self.assertIn("- self-hosted", workflow)
        self.assertNotIn("pipeline.footage", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("scripts/$TARGET_DATE", workflow)

    def test_download_command_is_bounded_and_never_accepts_playlists(self) -> None:
        item = self.catalog["items"][0]
        command = build_yt_dlp_command(
            item,
            item_dir=Path("/tmp/video"),
            clip_seconds=15,
            yt_dlp_executable="yt-dlp",
        )
        self.assertIn("--no-playlist", command)
        self.assertIn("--download-sections", command)
        self.assertIn("*0-15", command)
        self.assertIn("!is_live & !was_live", command)
        self.assertIn("youtube:player_client=web_embedded;skip=hls,dash", command)
        self.assertEqual(item["source_url"], command[-1])

    def test_sanitized_metadata_drops_signed_urls_and_format_inventory(self) -> None:
        clean = sanitized_metadata(
            {
                "id": "aqz-KE-bpKQ",
                "title": "Big Buck Bunny",
                "formats": [{"url": "https://signed.example/video?token=secret"}],
                "url": "https://signed.example/direct?token=secret",
                "http_headers": {"Cookie": "secret"},
            }
        )
        self.assertEqual({"id": "aqz-KE-bpKQ", "title": "Big Buck Bunny"}, clean)

    def test_youtube_metadata_license_fails_closed(self) -> None:
        item = next(
            entry for entry in self.catalog["items"] if entry["license_evidence"]["basis"] == "youtube_metadata"
        )
        metadata = {
            "id": item["video_id"],
            "channel": item["expected_channel"],
            "availability": "public",
            "live_status": "not_live",
            "license": "Standard YouTube License",
        }
        errors = verify_metadata(item, metadata)
        self.assertTrue(any("no longer declares" in error for error in errors))

    def test_publisher_license_still_requires_exact_channel(self) -> None:
        item = next(
            entry for entry in self.catalog["items"] if entry["license_evidence"]["basis"] == "publisher_license"
        )
        metadata = {
            "id": item["video_id"],
            "channel": "Imposter channel",
            "availability": "public",
            "live_status": "not_live",
        }
        errors = verify_metadata(item, metadata)
        self.assertTrue(any("channel drift" in error for error in errors))

    def test_sha256_file_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.bin"
            path.write_bytes(b"youtube-artifact-test")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha256_file(path))

    def test_manifest_and_supporting_files_capture_success_and_failure(self) -> None:
        evidence = self.catalog["items"][0]["license_evidence"]
        results = [
            {
                "ordinal": 1,
                "cohort": "famous_open_movie",
                "video_id": "aqz-KE-bpKQ",
                "source_url": "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
                "expected_title": "Big Buck Bunny",
                "expected_channel": "Blender",
                "selection_reason": "test",
                "license_evidence": evidence,
                "status": "success",
                "actual_title": "Big Buck Bunny",
                "actual_channel": "Blender",
                "youtube_declared_license": "Creative Commons Attribution license (reuse allowed)",
                "source_duration_seconds": 635,
                "started_at_utc": "2026-09-06T00:00:00+00:00",
                "finished_at_utc": "2026-09-06T00:00:01+00:00",
                "clip": {
                    "path": "videos/01_aqz-KE-bpKQ/aqz-KE-bpKQ.mp4",
                    "sha256": "a" * 64,
                    "duration_seconds": 15.0,
                    "size_bytes": 1234,
                    "container": "mov,mp4",
                    "width": 640,
                    "height": 360,
                    "video_codec": "h264",
                    "audio_codec": "aac",
                },
                "metadata": {
                    "path": "videos/01_aqz-KE-bpKQ/metadata.json",
                    "sha256": "b" * 64,
                },
            },
            {
                "ordinal": 2,
                "cohort": "random_cc",
                "video_id": "w6uX9jamcwQ",
                "source_url": "https://www.youtube.com/watch?v=w6uX9jamcwQ",
                "expected_title": "Waterfall",
                "expected_channel": "Youstock",
                "selection_reason": "test",
                "license_evidence": evidence,
                "status": "failed",
                "error": "network timeout",
                "started_at_utc": "2026-09-06T00:00:00+00:00",
                "finished_at_utc": "2026-09-06T00:00:01+00:00",
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with mock.patch(
                "experiments.youtube_artifacts.download._tool_version", return_value="test-version"
            ):
                manifest = build_manifest(
                    catalog_path=CATALOG_PATH,
                    clip_seconds=15,
                    workers=2,
                    max_bytes_per_clip=20 * 1024 * 1024,
                    required_successes=2,
                    results=results,
                    yt_dlp_executable="yt-dlp",
                )
            write_supporting_files(output_dir, manifest)
            self.assertEqual(1, manifest["summary"]["succeeded"])
            self.assertFalse(manifest["summary"]["gate_passed"])
            self.assertIn("network timeout", (output_dir / "SUMMARY.md").read_text(encoding="utf-8"))
            self.assertIn("Big Buck Bunny", (output_dir / "ATTRIBUTION.md").read_text(encoding="utf-8"))
            self.assertIn("a" * 64, (output_dir / "SHA256SUMS").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
