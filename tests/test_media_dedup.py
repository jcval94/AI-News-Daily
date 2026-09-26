from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from PIL import Image

from pipeline.media_dedup import (
    asset_identity_keys,
    deduplicate_materialized_media,
    resolution_rank,
)


class MediaDedupTests(unittest.TestCase):
    def test_same_provider_asset_keeps_highest_source_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            low = root / "low.jpg"
            high = root / "high.jpg"
            Image.new("RGB", (1280, 720)).save(low)
            Image.new("RGB", (3840, 2160)).save(high)

            manifest = [
                {
                    "shot_number": 1,
                    "file": "low.jpg",
                    "provider": "pexels",
                    "provider_asset_id": "123",
                    "source_url": "https://www.pexels.com/photo/example-123/?auto=1",
                    "source_width": 1280,
                    "source_height": 720,
                    "start_seconds": 10,
                },
                {
                    "shot_number": 2,
                    "file": "high.jpg",
                    "provider": "pexels",
                    "provider_asset_id": "123",
                    "source_url": "https://www.pexels.com/photo/example-123/",
                    "source_width": 3840,
                    "source_height": 2160,
                    "start_seconds": 40,
                },
            ]
            segments = [
                {"slot_number": 1, "file": "low.jpg"},
                {"slot_number": 2, "file": "high.jpg"},
            ]

            kept, kept_segments, removed = deduplicate_materialized_media(
                manifest,
                segments,
                media_root=root,
            )

            self.assertEqual([item["shot_number"] for item in kept], [2])
            self.assertEqual([item["slot_number"] for item in kept_segments], [1, 2])
            self.assertEqual(kept_segments[0]["retrieval_status"], "unresolved")
            self.assertEqual(len(removed), 1)
            self.assertEqual(removed[0]["kept_shot_number"], 2)
            self.assertFalse(low.exists())
            self.assertTrue(high.exists())

    def test_exact_local_duplicate_is_removed_without_provider_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "a.jpg"
            second = root / "b.jpg"
            first.write_bytes(b"same-file-content")
            second.write_bytes(b"same-file-content")

            manifest = [
                {
                    "shot_number": 7,
                    "file": "a.jpg",
                    "provider": "generated_fallback",
                    "source_width": 1280,
                    "source_height": 720,
                    "start_seconds": 5,
                },
                {
                    "shot_number": 8,
                    "file": "b.jpg",
                    "provider": "generated_fallback",
                    "source_width": 1280,
                    "source_height": 720,
                    "start_seconds": 25,
                },
            ]
            segments = [{"slot_number": 7}, {"slot_number": 8}]

            kept, kept_segments, removed = deduplicate_materialized_media(
                manifest,
                segments,
                media_root=root,
            )

            self.assertEqual(len(kept), 1)
            self.assertEqual(len(kept_segments), 2)
            self.assertEqual(len(removed), 1)
            self.assertEqual(kept[0]["shot_number"], 7)

    def test_source_url_identity_ignores_query_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "asset.jpg"
            path.write_bytes(b"asset")
            item = {
                "file": "asset.jpg",
                "provider": "legacy",
                "source_url": "HTTPS://Example.COM/media/42/?w=640&token=abc",
            }
            keys = asset_identity_keys(item, media_root=root)
            self.assertIn("source:https://example.com/media/42", keys)

    def test_resolution_rank_prioritizes_pixels_before_file_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            huge_file = root / "huge-low.jpg"
            small_file = root / "small-high.jpg"
            Image.new("RGB", (1280, 720)).save(huge_file)
            Image.new("RGB", (1920, 1080)).save(small_file)
            low = {
                "file": "huge-low.jpg",
                "source_width": 1280,
                "source_height": 720,
            }
            high = {
                "file": "small-high.jpg",
                "source_width": 1920,
                "source_height": 1080,
            }
            self.assertGreater(
                resolution_rank(high, media_root=root),
                resolution_rank(low, media_root=root),
            )


if __name__ == "__main__":
    unittest.main()
