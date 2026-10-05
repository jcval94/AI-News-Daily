import json
import unittest
from pathlib import Path

from pipeline.local.paths import looks_absolute
from pipeline.schema_validation import validate_payload


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "local_handoff" / "examples"
REQUIRED_P1 = {
    "recording.ingest",
    "recording.transcribe",
    "recording.align",
    "resolve.sync_audio",
    "timeline.validate",
    "resolve.import_timeline",
}


class LocalP1ExampleTests(unittest.TestCase):
    def test_examples_cover_complete_p1_sequence(self):
        operations = set()
        for path in sorted(EXAMPLES.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            validate_payload(payload, "local/local_job.schema.json")
            operations.add(str(payload["operation"]))
        self.assertTrue(REQUIRED_P1.issubset(operations))

    def test_p1_examples_use_root_refs_not_absolute_paths(self):
        for path in sorted(EXAMPLES.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["operation"] not in REQUIRED_P1:
                continue
            for value in payload.get("params", {}).values():
                if not isinstance(value, dict) or "relative_path" not in value:
                    continue
                self.assertFalse(
                    looks_absolute(str(value["relative_path"])),
                    msg=f"{path.name} contains an absolute path ref",
                )

    def test_p1_examples_require_explicit_execute_mode(self):
        by_operation = {}
        for path in sorted(EXAMPLES.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["operation"] in REQUIRED_P1:
                by_operation[payload["operation"]] = payload
        for operation in REQUIRED_P1:
            self.assertEqual(by_operation[operation]["mode"], "execute")


if __name__ == "__main__":
    unittest.main()
