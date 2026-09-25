import json
import tempfile
import unittest
from pathlib import Path

from pipeline.local.toolchain import build_toolchain
from pipeline.schema_validation import validate_payload


class LocalToolchainTests(unittest.TestCase):
    def test_snapshot_has_no_absolute_python_path(self):
        repo = Path(__file__).resolve().parents[2]
        cfg = json.loads((repo / "config/local/local_config.example.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            cfg["paths"]["recordings_root"] = str(root / "recordings")
            cfg["paths"]["work_root"] = str(root / "work")
            cfg["paths"]["cache_root"] = str(root / "cache")
            cfg["paths"]["preview_root"] = str(root / "previews")
            payload = build_toolchain(cfg, repo_root=repo, probe_resolve=False)
            validate_payload(payload, "local/local_toolchain.schema.json")
            self.assertFalse(payload["privacy"]["absolute_paths_persisted"])
            self.assertNotIn(str(Path.home()), payload["python"]["executable_redacted"])


if __name__ == "__main__":
    unittest.main()
