import unittest
from unittest.mock import Mock, patch

from pipeline.tts.engines import _run


class EngineProcessTests(unittest.TestCase):
    def test_engine_processes_read_utf8_on_windows(self):
        with patch(
            "pipeline.tts.engines.subprocess.run",
            return_value=Mock(returncode=0, stderr="", stdout=""),
        ) as run:
            _run(["tts"], timeout=1)

        self.assertEqual(run.call_args.kwargs["env"]["PYTHONUTF8"], "1")
        self.assertEqual(run.call_args.kwargs["env"]["PYTHONIOENCODING"], "utf-8")
