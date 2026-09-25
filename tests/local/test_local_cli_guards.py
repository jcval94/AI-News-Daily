import unittest
from pathlib import Path
from unittest.mock import patch

import pipeline.local.__main__ as local_main


class LocalCliGuardTests(unittest.TestCase):
    def test_direct_execute_is_blocked_before_job_read(self):
        with patch(
            "sys.argv",
            [
                "pipeline.local",
                "run-job",
                "local_handoff/requests/anything.json",
                "--execute",
            ],
        ), patch.object(local_main, "load_config", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "Direct execution"):
                local_main.main()


if __name__ == "__main__":
    unittest.main()
