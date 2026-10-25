from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.audio_library_pages import build_audio_library_page
from pipeline.review_hub_catalog import catalog_document


class AudioLibraryPagesTests(unittest.TestCase):
    def test_empty_catalog_builds_useful_mobile_page_without_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "index.json"
            catalog.write_text('{"schema_version":1,"items":[]}', encoding="utf-8")
            page = build_audio_library_page(catalog=catalog, output_dir=root / "audio")
            body = page.read_text(encoding="utf-8")
            self.assertIn('data-audio-library="v1"', body)
            self.assertIn('id="audioSearch"', body)
            self.assertIn('src="audio.js"', body)
            self.assertNotIn("<audio", body.lower())
            self.assertTrue((root / "audio/audio.js").is_file())

    def test_escape_untrusted_track_metadata_and_show_rights(self):
        item = {
            "id": "test-audio-123", "title": "<script>alert(1)</script>",
            "creator": "A & B", "kind": "sfx", "provider": "Sound Example",
            "source_url": "https://example.org/item/123",
            "license": {"identifier": "CC0 1.0",
                        "terms_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                        "evidence_url": "https://example.org/item/123",
                        "checked_on": "2026-10-25"},
            "rights_review": {"status": "pending"},
            "mood": "tense", "intensity": "high", "tags": ["impact"]
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"schema_version": 1, "items": [item]}), encoding="utf-8")
            html = build_audio_library_page(catalog=catalog, output_dir=root / "site").read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>alert", html)
            self.assertIn('data-rights="review_required"', html)
            self.assertIn('data-mood="tense"', html)
            self.assertIn('rel="noopener noreferrer"', html)
            self.assertIn("Ficha original", html)
            self.assertNotIn("<audio", html.lower())

    def test_root_catalog_links_to_browser_on_desktop_and_mobile(self):
        episodes = [{"id": "2026-10-01", "date": "2026-10-01", "href": "episodes/2026-10-01/index.html",
                     "status": "Aprobado", "title": "Example", "run_id": "x", "cost": None}]
        document = catalog_document(episodes, current_id="2026-10-01")
        self.assertGreaterEqual(document.count('href="audio/index.html"'), 2)


if __name__ == "__main__":
    unittest.main()
