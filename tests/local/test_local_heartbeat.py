import json
import tempfile
import unittest
from pathlib import Path

from pipeline.local.heartbeat import Heartbeat, build_heartbeat, write_heartbeat
from pipeline.schema_validation import validate_payload


class LocalHeartbeatTests(unittest.TestCase):
    def test_contract_contains_no_machine_paths(self):
        payload = build_heartbeat(
            job_id="job-heartbeat-001",
            operation="recording.transcribe",
            status="running",
            started_at="2026-10-05T20:00:00Z",
            now="2026-10-05T20:00:05Z",
            runner_pid=1234,
        )
        validate_payload(payload, "local/local_heartbeat.schema.json")
        serialized = json.dumps(payload)
        self.assertNotIn("C:\\", serialized)
        self.assertFalse(payload["privacy"]["absolute_paths_persisted"])

    def test_atomic_write_and_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "heartbeat.json"
            ticks = iter(
                [
                    "2026-10-05T20:00:00Z",
                    "2026-10-05T20:00:01Z",
                    "2026-10-05T20:00:02Z",
                ]
            )
            heartbeat = Heartbeat(
                path,
                job_id="job-heartbeat-002",
                operation="timeline.validate",
                started_at="2026-10-05T20:00:00Z",
                now_fn=lambda: next(ticks),
                interval_seconds=60,
            )
            heartbeat.start()
            self.assertTrue(path.is_file())
            self.assertTrue(heartbeat.finish("success"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "success")
            self.assertIsNotNone(payload["finished_at"])


if __name__ == "__main__":
    unittest.main()
