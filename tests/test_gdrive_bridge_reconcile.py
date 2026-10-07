from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock

import requests
import yaml

from pipeline.gdrive_bridge_reconcile import GitHub, decide, reconcile
from pipeline.gdrive_bridge_io import LANES, SHEET_MIME

NOW = datetime(2026, 10, 4, 16, 0, tzinfo=timezone.utc)


def run(*, age=0, event="workflow_dispatch", status="completed", file_id="pending", conclusion="success"):
    return {"created_at": (NOW-timedelta(minutes=age)).isoformat(), "event": event, "status": status, "conclusion": conclusion, "display_title": f"Drive daily bridge [{file_id}]"}


class ReconcileTests(unittest.TestCase):
    def test_success_idle_poll_does_not_suppress_pending(self):
        self.assertEqual(decide([run(age=1, event="schedule")], "pending", NOW), "dispatch")

    def test_active_run_blocks_only_within_grace(self):
        self.assertEqual(decide([run(status="queued", age=19)], "pending", NOW), "active")
        self.assertEqual(decide([run(status="in_progress", age=21, event="schedule")], "pending", NOW), "dispatch")

    def test_dispatch_cooldown_is_per_file(self):
        self.assertEqual(decide([run(age=1)], "pending", NOW), "cooldown")
        self.assertEqual(decide([run(age=1, file_id="other")], "pending", NOW), "dispatch")

    def test_budget_survives_cooldown_and_is_per_file(self):
        attempts = [run(age=11), run(age=30), run(age=70)]
        self.assertEqual(decide(attempts, "pending", NOW), "blocked_attempt_budget")
        self.assertEqual(decide(attempts, "different", NOW), "dispatch")

    def test_same_file_dispatch_is_not_publication(self):
        drive, github = Mock(), Mock()
        drive.list_inbox.return_value = [{"id": "pending", "name": "__bridge_inbox_AI-News-Daily__2026-10-04_083640", "mimeType": SHEET_MIME, "createdTime": "2026-10-04T14:37:20Z"}]
        github.runs.return_value = [run(age=1, event="schedule")]
        github.dispatch.return_value = 123
        got = reconcile(drive, github, "inbox", now=NOW)
        self.assertFalse(got["publication_verified"])
        self.assertEqual(got["lanes"]["daily"]["status"], "dispatched")
        self.assertEqual(got["lanes"]["daily"]["run_id"], 123)
        github.dispatch.assert_called_once_with(LANES["daily"].workflow, "pending")

    def test_empty_inbox_has_no_remote_write(self):
        drive, github = Mock(), Mock()
        drive.list_inbox.return_value = []
        got = reconcile(drive, github, "inbox", now=NOW)
        self.assertTrue(all(e["status"] == "idle" for e in got["lanes"].values()))
        github.runs.assert_not_called()
        github.dispatch.assert_not_called()

    def test_inspection_failure_does_not_dispatch(self):
        drive, github = Mock(), Mock()
        drive.list_inbox.return_value = [{"id": "pending", "name": "__bridge_inbox_AI-News-Daily__2026-10-04_083640", "mimeType": SHEET_MIME, "createdTime": "2026-10-04T14:37:20Z"}]
        github.runs.side_effect = requests.HTTPError("forbidden")
        got = reconcile(drive, github, "inbox", now=NOW)
        self.assertEqual(got["lanes"]["daily"]["status"], "inspection_or_dispatch_failed")
        github.dispatch.assert_not_called()

    def test_timeout_is_not_retried_or_marked_published(self):
        session = Mock()
        session.post.side_effect = requests.Timeout()
        with self.assertRaises(requests.Timeout):
            GitHub("jcval94/AI-News-Daily", "token", session).dispatch(LANES["daily"].workflow, "pending")
        self.assertEqual(session.post.call_count, 1)

    def test_dispatch_response_retains_run_id_and_exact_input(self):
        session = Mock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {"workflow_run_id": 456}
        result = GitHub("jcval94/AI-News-Daily", "token", session).dispatch(LANES["daily"].workflow, "pending")
        self.assertEqual(result, 456)
        self.assertEqual(session.post.call_args.kwargs["json"], {"ref": "main", "inputs": {"handoff_id": "pending"}})

    def test_three_workflows_wire_verified_io_and_exact_dispatch(self):
        root = Path(__file__).resolve().parents[1]
        expected_crons = {
            "daily": "2 * * * *",
            "weekly": "3 * * * *",
            "narrative": "4 * * * *",
        }
        for lane, contract in LANES.items():
            data = yaml.load((root/".github/workflows"/contract.workflow).read_text(), Loader=yaml.BaseLoader)
            self.assertEqual(data["on"]["schedule"], [{"cron": expected_crons[lane]}])
            self.assertIn("handoff_id", data["on"]["workflow_dispatch"]["inputs"])
            self.assertIn("inputs.handoff_id", data["run-name"])
            steps = data["jobs"]["consume"]["steps"]
            selector = next(s for s in steps if s.get("id") == "select")
            self.assertIn("select --lane " + lane, selector["run"])
            for outcome in ("processed", "failed"):
                step = next(s for s in steps if s.get("name", "").startswith("Move ") and s["name"].endswith(outcome))
                self.assertIn("move --outcome " + outcome, step["run"])

    def test_reconcile_only_watchdog_cannot_cancel_or_build_pages(self):
        root = Path(__file__).resolve().parents[1]
        data = yaml.load((root / ".github/workflows/editorial-review-hub.yml").read_text(), Loader=yaml.BaseLoader)
        condition = data["jobs"]["build"]["if"]
        name = data["run-name"].split("${{", 1)[1].split("}}", 1)[0]
        group = data["concurrency"]["group"].split("${{", 1)[1].split("}}", 1)[0]

        def evaluate(expression, context):
            # Evaluate only this boolean/comparison subset from trusted workflow YAML.
            for key in sorted(context, key=len, reverse=True):
                expression = expression.replace(key, repr(context[key]))
            tree = ast.parse(expression.strip().replace("&&", "and").replace("||", "or"), mode="eval")
            allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq, ast.NotEq, ast.Constant)
            self.assertTrue(all(isinstance(node, allowed) for node in ast.walk(tree)))
            return eval(compile(tree, "workflow-condition", "eval"), {"__builtins__": {}}, {})

        cases = [
            ("push", "", "", True),
            ("workflow_dispatch", "", "", True),
            ("workflow_run", "News Ingestion Watchdog", "schedule", True),
            ("workflow_run", "News Ingestion Watchdog", "workflow_dispatch", True),
            ("workflow_run", "Production Preflight", "workflow_run", True),
            ("workflow_run", "News Ingestion Watchdog", "workflow_run", False),
        ]
        for event, upstream_name, upstream_event, builds in cases:
            with self.subTest(event=event, upstream=upstream_name, source=upstream_event):
                context = {"github.event_name": event, "github.event.workflow_run.name": upstream_name,
                           "github.event.workflow_run.event": upstream_event, "github.run_id": 123}
                self.assertEqual(evaluate(condition, context), builds)
                self.assertEqual(evaluate(name, context), "Editorial Review Hub" if builds else "Drive reconciliation acknowledged (no Pages build)")
                self.assertEqual(evaluate(group, context), "main" if builds else 123)
                if not builds:
                    context["github.run_id"] = 124
                    self.assertNotEqual(evaluate(group, context), 123)
        self.assertIn("build", data["jobs"]["deploy"]["needs"])
        self.assertIn("news/**", data["on"]["push"]["paths"])
        self.assertIn("editorial/narrative_memory.jsonl", data["on"]["push"]["paths"])

    def test_watchdog_uses_two_daily_schedules_without_workflow_run_mesh(self):
        root = Path(__file__).resolve().parents[1]
        data = yaml.load((root/".github/workflows/news-ingestion-watchdog.yml").read_text(), Loader=yaml.BaseLoader)
        self.assertNotIn("workflow_run", data["on"])
        self.assertEqual(
            data["on"]["schedule"],
            [{"cron": "30 16 * * *"}, {"cron": "0 20 * * *"}],
        )
        job = data["jobs"]["reconcile-drive"]
        self.assertEqual(job["if"], "github.ref == 'refs/heads/main' && inputs.date == ''")
        self.assertEqual(job["steps"][0]["with"]["ref"], "main")
        self.assertEqual(job["permissions"], {"contents": "read", "actions": "write"})
        self.assertNotIn("if", data["jobs"]["watchdog"])


if __name__ == "__main__":
    unittest.main()
