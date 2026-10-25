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
            "attribution_text": "Example Artist, Test Track, CC BY 4.0",
        },
        "rights_review": {"status": "pending"},
        "tags": ["calm", "intro"], "intensity": "low",
    }


def approved_fixture() -> dict:
    item = fixture()
    item["rights_review"] = {
        "status": "approved",
        "reviewer": "Human editor",
        "reviewed_on": "2026-10-25",
        "rights_basis": "creative_commons",
        "usage_platforms": ["youtube"],
        "commercial_use_confirmed": True,
        "synchronization_confirmed": True,
        "edits_confirmed": True,
        "track_specific_evidence_confirmed": True,
        "evidence_description": "Reviewed original track listing and terms for this exact recording.",
        "attribution_required": True,
        "content_id_review": "no_known_claim",
        "preview_redistribution_allowed": False,
    }
    return item


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

    def test_valid_review_is_explicit_and_scope_limited(self):
        item = approved_fixture()
        self.assertEqual(rights_status(item), "approved")
        self.assertEqual(validate_catalog({"schema_version": 1, "items": [item]})["approved"], 1)

    def test_missing_approval_fields_fail_schema(self):
        keys = ["reviewer", "reviewed_on", "rights_basis", "usage_platforms",
                "track_specific_evidence_confirmed", "evidence_description",
                "attribution_required", "content_id_review", "preview_redistribution_allowed",
                "synchronization_confirmed", "commercial_use_confirmed", "edits_confirmed"]
        for key in keys:
            with self.subTest(field=key):
                item = approved_fixture()
                del item["rights_review"][key]
                with self.assertRaises(ValueError):
                    validate_catalog({"schema_version": 1, "items": [item]})

    def test_rejects_invalid_claimed_approval(self):
        bad_reviews = [
            {"edits_confirmed": False},
            {"track_specific_evidence_confirmed": False},
            {"usage_platforms": ["instagram"]},
            {"content_id_review": "unchecked"},
            {"content_id_review": "active_claim"},
            {"content_id_review": "possible_claim"},
            {"rights_basis": "provider_specific"},
            {"attribution_required": False},
            {"reviewed_on": "2026-10-24"},
            {"evidence_description": "Generic provider terms; not checked."[:24]},
        ]
        for patch in bad_reviews:
            with self.subTest(patch=patch):
                item = approved_fixture()
                item["rights_review"].update(patch)
                self.assertNotEqual(rights_status(item), "approved")
                with self.assertRaises(ValueError):
                    validate_catalog({"schema_version": 1, "items": [item]})

    def test_possible_content_id_claim_requires_explicit_acceptance(self):
        item = approved_fixture()
        item["rights_review"]["content_id_review"] = "possible_claim"
        item["rights_review"]["content_id_risk_accepted"] = True
        self.assertEqual(validate_catalog({"schema_version": 1, "items": [item]})["approved"], 1)

    def test_cc_by_attribution_is_mandatory(self):
        item = approved_fixture()
        del item["license"]["attribution_text"]
        self.assertEqual(rights_status(item), "review_required")
        with self.assertRaises(ValueError):
            validate_catalog({"schema_version": 1, "items": [item]})

    def test_share_alike_obligation_must_be_acknowledged(self):
        item = approved_fixture()
        item["license"]["identifier"] = "CC BY-SA 4.0"
        self.assertEqual(rights_status(item), "review_required")
        item["rights_review"]["share_alike_obligations_acknowledged"] = True
        self.assertEqual(validate_catalog({"schema_version": 1, "items": [item]})["approved"], 1)

    def test_proprietary_provider_permission_needs_direct_review(self):
        item = approved_fixture()
        item["license"]["identifier"] = "Publisher's bespoke license"
        item["rights_review"]["rights_basis"] = "provider_specific"
        self.assertEqual(validate_catalog({"schema_version": 1, "items": [item]})["approved"], 1)
        item["rights_review"]["rights_basis"] = "direct_permission"
        with self.assertRaises(ValueError):
            validate_catalog({"schema_version": 1, "items": [item]})
        item["rights_review"]["permission_record_url"] = "https://example.org/permission/1"
        self.assertEqual(validate_catalog({"schema_version": 1, "items": [item]})["approved"], 1)

    def test_forbidden_and_ambiguous_license_variants_fail(self):
        licenses = [
            "CC BY-NC 4.0", "CC-BY-NC-ND 4.0", "CC BY ND 3.0",
            "Creative Commons Attribution-NonCommercial 4.0",
            "Creative Commons Attribution-NoDerivatives 4.0",
            "CC_BY_NC", "CC–BY–ND", "Fair Use", "All rights reserved",
            "No restrictions", "Unknown", "UnsPecified",
            "CC mystery 3.0", "CC BY NC SA",
        ]
        for license_name in licenses:
            with self.subTest(identifier=license_name):
                item = approved_fixture()
                item["license"]["identifier"] = license_name
                self.assertEqual(rights_status(item), "blocked")
                with self.assertRaises(ValueError):
                    validate_catalog({"schema_version": 1, "items": [item]})

    def test_blocked_and_pending_do_not_count_as_approved(self):
        item = fixture()
        item["license"]["identifier"] = "All rights reserved"
        self.assertEqual(validate_catalog({"schema_version": 1, "items": [item]})["blocked"], 1)
        item["rights_review"]["status"] = "rejected"
        self.assertEqual(rights_status(item), "blocked")

    def test_duplicate_ids_fail(self):
        item = fixture()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_catalog({"schema_version": 1, "items": [item, copy.deepcopy(item)]})

    def test_unsafe_urls_and_paths_fail(self):
        item = fixture()
        for bad_url in ["http://example.org", "https://localhost/x", "https://evil .example/x"]:
            with self.subTest(url=bad_url):
                item["source_url"] = bad_url
                with self.assertRaisesRegex(ValueError, "source_url"):
                    validate_catalog({"schema_version": 1, "items": [item]})
        item["source_url"] = "https://example.org"
        item["local_relpath"] = "assets/../../secrets"
        with self.assertRaisesRegex(ValueError, "local_relpath"):
            validate_catalog({"schema_version": 1, "items": [item]})

    def test_bad_permission_url_or_hash_fail(self):
        item = approved_fixture()
        item["rights_review"]["rights_basis"] = "direct_permission"
        item["license"]["identifier"] = "Publisher direct grant"
        item["rights_review"]["permission_record_url"] = "file:///private/permission.pdf"
        with self.assertRaises(ValueError):
            validate_catalog({"schema_version": 1, "items": [item]})
        item["rights_review"]["permission_record_url"] = "https://example.org/grant"
        item["license"]["evidence_sha256"] = "not-a-digest"
        with self.assertRaises(ValueError):
            validate_catalog({"schema_version": 1, "items": [item]})

    def test_unknown_fields_fail_schema(self):
        item = fixture()
        item["playback_url"] = "https://example.org/audio.mp3"
        with self.assertRaises(ValueError):
            validate_catalog({"schema_version": 1, "items": [item]})


if __name__ == "__main__":
    unittest.main()
