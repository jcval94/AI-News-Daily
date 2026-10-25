from __future__ import annotations

import json
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from pipeline.audio_library import load_catalog, validate_catalog
from pipeline.audio_library_pages import build_audio_library_page


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "catalog/audio/index.json"


class AudioFirstCurationTests(unittest.TestCase):
    def test_initial_candidate_links_are_specific_and_unique(self):
        records = load_catalog(INDEX)["items"]
        self.assertGreaterEqual(len(records), 1)
        urls = [entry["source_url"] for entry in records]
        self.assertEqual(len(urls), len(set(urls)))
        for entry in records:
            with self.subTest(entry=entry["id"]):
                self.assertEqual(entry["source_url"], entry["license"]["evidence_url"])
                self.assertGreaterEqual(len(entry["tags"]), 3)
                source = entry["source_url"]
                if entry["provider"] == "Freesound":
                    self.assertRegex(source, r"^https://freesound\.org/people/[^/]+/sounds/\d+/$")
                    self.assertEqual(entry["license"]["identifier"], "CC0 1.0")
                elif entry["provider"] == "Pixabay":
                    self.assertRegex(source, r"^https://pixabay\.com/music/[a-z0-9-]+-\d+/$")
                    self.assertEqual(entry["license"]["identifier"], "Pixabay Content License")
                else:
                    self.assertRegex(source, r"^https://[^/]+/.+")
                    self.assertTrue(entry["license"]["terms_url"].startswith("https://"))
        self.assertEqual(validate_catalog({"schema_version": 1, "items": records})["total"], len(records))

    def test_expected_pilot_mix_and_content_id_warnings(self):
        items = load_catalog(INDEX)["items"]
        counts = Counter(x["kind"] for x in items)
        for kind in ("music", "sfx", "transition", "ambience"):
            self.assertGreater(counts[kind], 0, f"Missing curated sound category: {kind}")
        for name in ("pixabay-115669", "pixabay-578410"):
            candidates = [x for x in items if x["id"] == name]
            if candidates and candidates[0]["rights_review"]["status"] == "pending":
                self.assertIn("Content ID Registered", candidates[0]["rights_review"]["notes"])

    def test_browser_renders_pilot_without_playback_or_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = build_audio_library_page(catalog=INDEX, output_dir=root)
            html = page.read_text(encoding="utf-8")
            self.assertEqual(html.count("<article data-audio-card"), len(load_catalog(INDEX)["items"]))
            self.assertIn("Pixabay", html)
            self.assertIn("Freesound", html)
            self.assertIn("City Ambience - Mexico City", html)
            self.assertIn("Investigation Puzzle", html)
            self.assertNotIn("<audio", html.lower())
            self.assertNotIn("download=", html.lower())


if __name__ == "__main__":
    unittest.main()
