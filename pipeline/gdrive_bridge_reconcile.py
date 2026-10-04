"""Bounded wakeups for pending Drive handoffs; dispatch is never publication.

Uses the existing consumer workflows and no research/content side effects.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Any

import requests

from pipeline.gdrive_bridge_io import Drive, LANES, select

ACTIVE_GRACE = timedelta(minutes=20)
DISPATCH_COOLDOWN = timedelta(minutes=10)
MAX_ATTEMPTS = 3


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Run timestamp must include timezone")
    return result


def decide(runs: list[dict[str, Any]], file_id: str, now: datetime) -> str:
    # A successful idle poll is not evidence that this pending file was consumed.
    if any(r.get("status") != "completed" and now - timestamp(r["created_at"]) < ACTIVE_GRACE for r in runs):
        return "active"
    attempts = [r for r in runs if r.get("event") == "workflow_dispatch" and str(r.get("display_title") or "").endswith(f"[{file_id}]")]
    # Budget is per handoff over the retained workflow history, not reset on each wake.
    if len(attempts) >= MAX_ATTEMPTS:
        return "blocked_attempt_budget"
    if any(now - timestamp(r["created_at"]) < DISPATCH_COOLDOWN for r in attempts):
        return "cooldown"
    return "dispatch"


class GitHub:
    def __init__(self, repo: str, token: str, session: Any = None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
            raise ValueError("Invalid repository or missing GitHub token")
        self.base = "https://api.github.com/repos/" + repo
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
        self.session = session if session is not None else requests.Session()

    def runs(self, workflow: str, since: datetime) -> list[dict[str, Any]]:
        result = []
        # A bounded complete window: if exceeded, fail inspection rather than dispatch blind.
        for page in range(1, 11):
            response = self.session.get(f"{self.base}/actions/workflows/{workflow}/runs", headers=self.headers, params={"branch": "main", "created": ">=" + since.isoformat(), "per_page": 100, "page": page}, timeout=30)
            response.raise_for_status()
            body = response.json()
            items = body.get("workflow_runs")
            if not isinstance(items, list):
                raise ValueError("Malformed workflow run listing")
            result.extend(items)
            if len(result) >= body.get("total_count", len(result)) or len(items) < 100:
                return result
        raise ValueError("Run inspection exceeded budget; refusing blind dispatch")

    def dispatch(self, workflow: str, file_id: str) -> int | None:
        # One request only. Timeout is ambiguous; do not retry a side effect blindly.
        response = self.session.post(f"{self.base}/actions/workflows/{workflow}/dispatches", headers=self.headers, json={"ref": "main", "inputs": {"handoff_id": file_id}}, timeout=30)
        response.raise_for_status()
        if response.status_code not in {200, 204}:
            raise ValueError("Unexpected workflow dispatch response")
        return response.json().get("workflow_run_id") if response.status_code == 200 else None


def reconcile(drive: Drive, github: GitHub, inbox: str, *, now: datetime | None = None) -> dict[str, Any]:
    now = now if now is not None else datetime.now(timezone.utc)
    report: dict[str, Any] = {"as_of": now.isoformat(), "publication_verified": False, "lanes": {}}
    files = drive.list_inbox(inbox)
    for lane, contract in LANES.items():
        item = select(files, lane)
        if not item:
            report["lanes"][lane] = {"status": "idle"}
            continue
        entry = {"file_id": item["id"], "workflow": contract.workflow}
        report["lanes"][lane] = entry
        try:
            since = min(timestamp(item["createdTime"]), now - ACTIVE_GRACE)
            runs = github.runs(contract.workflow, since)
            decision = decide(runs, item["id"], now)
            entry["status"] = decision
            if decision == "dispatch":
                entry["run_id"] = github.dispatch(contract.workflow, item["id"])
                entry["status"] = "dispatched"
        except (requests.RequestException, ValueError) as exc:
            # Fail closed. A timed-out POST may already have created a run.
            entry["status"] = "inspection_or_dispatch_failed"
            entry["error_type"] = type(exc).__name__
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = reconcile(Drive(os.environ["ACCESS_TOKEN"]), GitHub(args.repo, os.environ["GH_TOKEN"]), os.environ["INBOX_FOLDER_ID"])
    except (requests.RequestException, ValueError) as exc:
        report = {"publication_verified": False, "error_type": type(exc).__name__, "status": "inspection_failed", "lanes": {}}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## Drive handoff reconciliation\n\nDispatch is a wakeup, not publication.\n\n```json\n" + json.dumps(report, indent=2) + "\n```\n")
    if report.get("status") == "inspection_failed" or any(e["status"] in {"inspection_or_dispatch_failed", "blocked_attempt_budget"} for e in report["lanes"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
