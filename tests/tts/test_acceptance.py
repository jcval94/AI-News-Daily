import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.tts.acceptance import build_tts_doctor, run_tts_acceptance


class AcceptanceTests(unittest.TestCase):
    def test_doctor_allows_slow_cold_engine_imports(self):
        root = Path(tempfile.mkdtemp())
        runtime = root / ".venv-tts/Scripts/python.exe"
        runtime.parent.mkdir(parents=True)
        runtime.touch()
        model = root / ".local/models/piper/es_MX-claude-high.onnx"
        model.parent.mkdir(parents=True)
        model.touch()
        config = {
            "tts": {
                "engine": "kokoro",
                "runtime": {"python": str(runtime)},
                "engines": {
                    "kokoro": {"voice": "ef_dora"},
                    "piper": {
                        "voice": "es_MX-claude-high",
                        "model_dir": ".local/models/piper",
                    },
                },
                "fallback": {"enabled": True, "engine": "piper"},
            }
        }

        with (
            patch("pipeline.tts.acceptance.load_tts_config", return_value=config),
            patch("pipeline.tts.acceptance._probe", return_value={"ok": True, "output": "ok"}) as probe,
            patch("pipeline.tts.acceptance.shutil.which", return_value="available"),
        ):
            build_tts_doctor(repo_root=root)

        imports = [call for call in probe.call_args_list if "-c" in call.args[0]]
        self.assertTrue(imports)
        self.assertTrue(all(call.kwargs["timeout"] == 90 for call in imports))

    def test_render_exception_replaces_stale_report_with_failure(self):
        root = Path(tempfile.mkdtemp())
        report_path = root / ".local/tts/acceptance.latest.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text('{"status":"pass"}', encoding="utf-8")

        with (
            patch(
                "pipeline.tts.acceptance.build_tts_doctor",
                return_value={"status": "pass"},
            ),
            patch(
                "pipeline.tts.acceptance.run_tts_smoke",
                return_value={"status": "pass"},
            ),
            patch("pipeline.tts.acceptance.resolve_episode", return_value=root),
            patch(
                "pipeline.tts.acceptance.render_episode",
                side_effect=RuntimeError("physical render failed"),
            ),
        ):
            result = run_tts_acceptance(repo_root=root)

        persisted = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "fail")
        self.assertEqual(persisted["stopped_after"], "render")
        self.assertIn("physical render failed", persisted["error"])
