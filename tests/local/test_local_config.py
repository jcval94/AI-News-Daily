import json
import unittest

from pipeline.local.config import REPO_ROOT
from pipeline.schema_validation import validate_payload


class LocalConfigContractTests(unittest.TestCase):
    def test_committed_examples_validate(self):
        config = json.loads((REPO_ROOT / "config/local/local_config.example.json").read_text(encoding="utf-8"))
        validate_payload(config, "local/local_config.schema.json")
        self.assertFalse(config["security"]["allow_shell"])
        self.assertFalse(config["resolve"]["overwrite_existing"])
        job = json.loads((REPO_ROOT / "config/local/local_job.example.json").read_text(encoding="utf-8"))
        validate_payload(job, "local/local_job.schema.json")


if __name__ == "__main__":
    unittest.main()
