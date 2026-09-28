import json
import unittest
from pathlib import Path

from pipeline.schema_validation import validate_payload


class LocalHandoffRequestTests(unittest.TestCase):
    def test_all_committed_requests_match_local_job_contract(self):
        repo = Path(__file__).resolve().parents[2]
        root = repo / "local_handoff" / "requests"
        if not root.is_dir():
            return
        for path in sorted(root.glob("*.json")):
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                validate_payload(payload, "local/local_job.schema.json")


if __name__ == "__main__":
    unittest.main()
