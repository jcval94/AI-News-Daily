from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.media import download_shot_asset


class MediaManifestTests(unittest.TestCase):
    def test_manifest_uses_logical_episode_relative_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("pipeline.media.search_pexels", return_value=None), patch("pipeline.media.search_wikimedia", return_value=None):
            destination = Path(tmp) / ".pipeline-runs" / "x" / "assets" / "slot_001.jpg"
            record = download_shot_asset(
                {"shot_number": 1, "visual_query": "abstract verification", "on_screen_text": "Verificar"},
                destination,
                logical_file="assets/slot_001.jpg",
            )
            self.assertEqual(record["file"], "assets/slot_001.jpg")
            self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
