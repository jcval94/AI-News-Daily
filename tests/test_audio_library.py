from __future__ import annotations

import copy
import unittest
from pathlib import Path

from pipeline.audio_library import load_catalog, rights_status, validate_catalog


def fixture() -> dict:
    return {
        "id": "ambient-test-01", "title": "Fictitious Test Audio",
        "creator": "Example only", "kind": "music", "provider": "Example",
        "source_url": "https://example.org/sound/1",
        "license": {
            "identifier": "CC BY 4.0",
            "terms_url": "https://creativecommons.org/licenses/by/4.0/",
            "evidence_url": "https://example.org/sound/1",
            "checked_on": "2026-10-25",
        },
        "rights_review": {"status": "pending"},
        "tags": ["calm", "intro"], "intensity": "low",
    }


class AudioLibraryTests(unittest.TestCase):
    def test_real_index_valid_and_empty_fixture_supported(self):
        path = Path(__file__).resolve().parents[1] / "catalog/audio/index.json"
        payload = load_catalog(path)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(validate_catalog(payload)["total"], len(payload["items"]))
        self.assertEqual(validate_catalog({"schema_version": 1, "items": []})["total"], 0)

    def test_pending_never_auto_approved(self):
        item = fixture()
        self.assertEqual(rights_status(item), "review_required")
        self.assertEqual(validate_catalog({"schema_version": 1, "items": [item]})["approved"], 0)

    def test_approval_requires_positive_rights_evidence(self):
        item = fixture()
        item["rights_review"] = {"status": "approved", "reviewer": "editor", "reviewed_on": "2026-10-25",
                                 "commercial_use_confirmed": True, "synchronization_confirmed": True,
                                 "edits_confirmed": True}
        self.assertEqual(rights_status(item), "approved")
        self.assertEqual(validate_catalog({"schema_version": 1, "items": [item]})["approved"], 1)
        invalid = copy.deepcopy(item)
        invalid["rights_review"]["edits_confirmed"] = False
        with self.assertRaises(ValueError):
            validate_catalog({"schema_version": 1, "items": [invalid]})

    def test_nc_license_blocked_even_if_manually_approved(self):
        item = fixture()
        item["license"]["identifier"] = "CC BY-NC 4.0"
        item["rights_review"] = {"status": "approved", "reviewer": "editor", "reviewed_on": "2026-10-25",
                                 "commercial_use_confirmed": True, "synchronization_confirmed": True,
                                 "edits_confirmed": True}
        self.assertEqual(rights_status(item), "blocked")

    def test_duplicate_ids_fail(self):
        item = fixture()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_catalog({"schema_version": 1, "items": [item, copy.deepcopy(item)]})

    def test_unsafe_urls_and_paths_fail(self):
        item = fixture()
        item["source_url"] = "http://example.org"
        with self.assertRaisesRegex(ValueError, "source_url"):
            validate_catalog({"schema_version": 1, "items": [item]})
        item["source_url"] = "https://example.org"
        item["local_relpath"] = "assets/../../secrets"
        with self.assertRaisesRegex(ValueError, "local_relpath"):
            validate_catalog({"schema_version": 1, "items": [item]})

    def test_unknown_fields_fail_schema(self):
        item = fixture()
        item["playback_url"] = "https://example.org/audio.mp3"
        with self.assertRaises(ValueError):
            validate_catalog({"schema_version": 1, "items": [item]})


if __name__ == "__main__":
    unittest.main()
