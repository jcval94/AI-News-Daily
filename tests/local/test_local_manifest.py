import unittest

from pipeline.local.manifest import new_run_manifest
from pipeline.schema_validation import validate_payload


class LocalRunManifestTests(unittest.TestCase):
    def test_new_manifest_is_private_and_running(self):
        payload = new_run_manifest("run-20260925-001", "2026-09-25")
        validate_payload(payload, "local/local_run_manifest.schema.json")
        self.assertEqual(payload["status"], "running")
        self.assertFalse(payload["privacy"]["absolute_paths_persisted"])
        self.assertFalse(payload["privacy"]["raw_media_uploaded"])


if __name__ == "__main__":
    unittest.main()
