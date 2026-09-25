import json
import tempfile
import unittest
from pathlib import Path

from pipeline.local.preflight import build_preflight
from pipeline.schema_validation import validate_payload


class LocalPreflightTests(unittest.TestCase):
    def test_preflight_contracts_validate_without_resolve(self):
        repo_root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            cfg = json.loads((repo_root / "config/local/local_config.example.json").read_text(encoding="utf-8"))
            cfg["paths"]["recordings_root"] = str(root / "recordings")
            cfg["paths"]["work_root"] = str(root / "work")
            cfg["paths"]["cache_root"] = str(root / "cache")
            cfg["paths"]["preview_root"] = str(root / "previews")
            cfg["executables"]["python_core"] = __import__("sys").executable
            cfg["preflight"]["require_windows"] = False
            cfg["preflight"]["hard_min_free_gb"] = 0
            result = build_preflight(cfg, repo_root=repo_root)
            validate_payload(result["environment"], "local/local_environment.schema.json")
            validate_payload(result["capabilities"], "local/local_capabilities.schema.json")
            self.assertFalse(result["environment"]["privacy"]["absolute_paths_persisted"])


if __name__ == "__main__":
    unittest.main()
