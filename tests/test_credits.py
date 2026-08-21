from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline.credits import build_credits, write_credits
from pipeline.licenses import assess_license


class CreditsTests(unittest.TestCase):
    def test_cc_by_asset_generates_attribution_credit(self) -> None:
        manifest = [{"shot_number": 1, "file": "assets/a.jpg", "provider": "wikimedia_commons", "creator": "Ada", "license": "CC BY 4.0", "source_url": "https://commons.wikimedia.org/x"}]
        payload = build_credits(manifest)
        self.assertTrue(payload["all_assets_license_valid"])
        self.assertEqual(payload["attribution_required_count"], 1)
        with tempfile.TemporaryDirectory() as tmp:
            md, js = write_credits(manifest, Path(tmp))
            self.assertIn("Ada", md.read_text())
            self.assertTrue(js.exists())

    def test_noncommercial_and_unknown_licenses_are_rejected(self) -> None:
        self.assertFalse(assess_license("wikimedia_commons", "CC BY-NC 4.0")["allowed"])
        self.assertFalse(assess_license("wikimedia_commons", "All Rights Reserved")["allowed"])
        with self.assertRaises(ValueError):
            build_credits([{"file": "x.jpg", "provider": "wikimedia_commons", "license": "CC BY-NC 4.0"}])


if __name__ == "__main__":
    unittest.main()
