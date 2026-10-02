from __future__ import annotations

import json
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


PREFIX = "__bridge_inbox_AI-News-Daily__"
SHEET = "application/vnd.google-apps.spreadsheet"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/gdrive-raw-bridge-probe.yml"


def candidate(name: str, created: str, mime: str = SHEET) -> dict[str, str]:
    return {"id": name, "name": name, "createdTime": created, "mimeType": mime}


class DailyRoutingTests(unittest.TestCase):
    def select(self, files: list[dict[str, str]]) -> dict[str, str]:
        # Execute the deployed selector itself, including its ordering/output logic.
        workflow = WORKFLOW.read_text(encoding="utf-8")
        step = workflow.split("      - name: Select oldest pending AI News handoff\n", 1)[1]
        script = textwrap.dedent(step.split("python - <<'PY'\n", 1)[1].split("          PY\n", 1)[0])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            with patch.dict(os.environ, {"SHEET_PREFIX": PREFIX, "RAW_PREFIX": "ai-news-daily.news.", "GITHUB_OUTPUT": str(output)}):
                with patch.object(Path, "read_text", return_value=json.dumps({"files": files})):
                    exec(compile(script, str(WORKFLOW), "exec"), {})
            return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def test_other_lanes_cannot_take_precedence_over_daily(self) -> None:
        daily = PREFIX + "2026-10-02_122007"
        files = [
            candidate(PREFIX + "research-weekly__2026-10-02_084253", "2026-10-02T14:42:53Z"),
            candidate(PREFIX + "narrative-memory__2026-10-02_090000", "2026-10-02T15:00:00Z"),
            candidate(daily, "2026-10-02T18:20:07Z"),
        ]
        self.assertEqual(self.select(files)["file_id"], daily)

    def test_other_lanes_and_malformed_names_leave_daily_idle(self) -> None:
        names = ["research-weekly__2026-10-02_084253", "narrative-memory__2026-10-02_090000", "2026-10-02_122007_backup", "2026-10-02_12200", "2026-10-02_122007\n"]
        files = [candidate(PREFIX + name, "2026-10-02T14:00:00Z") for name in names]
        files.append(candidate(PREFIX + "2026-10-02_122007", "2026-10-02T14:00:00Z", "text/plain"))
        self.assertEqual(self.select(files), {"file_id": "", "file_name": "", "file_kind": ""})

    def test_oldest_daily_is_selected_regardless_of_input_order(self) -> None:
        older = PREFIX + "2026-10-01_184500"
        files = [candidate(PREFIX + "2026-10-02_122007", "2026-10-02T18:20:07Z"), candidate(older, "2026-10-01T23:45:00Z")]
        self.assertEqual(self.select(files)["file_id"], older)

    def test_legacy_raw_news_lane_is_preserved(self) -> None:
        raw = "ai-news-daily.news.2026-10-02.120000"
        self.assertEqual(self.select([candidate(raw, "2026-10-02T18:00:00Z", "text/plain")])["file_kind"], "raw")


if __name__ == "__main__":
    unittest.main()
