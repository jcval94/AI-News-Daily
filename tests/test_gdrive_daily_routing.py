from __future__ import annotations

import io
import os
import tempfile
from contextlib import redirect_stdout
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.gdrive_bridge_io import main


PREFIX = "__bridge_inbox_AI-News-Daily__"
SHEET = "application/vnd.google-apps.spreadsheet"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/gdrive-raw-bridge-probe.yml"


def candidate(name: str, created: str, mime: str = SHEET) -> dict[str, str]:
    return {"id": name, "name": name, "createdTime": created, "mimeType": mime}


class DailyRoutingTests(unittest.TestCase):
    def select(self, files: list[dict[str, str]]) -> dict[str, str]:
        # Exercise the production CLI; only the Drive read is replaced.
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            with patch.dict(os.environ, {"ACCESS_TOKEN": "test-token", "INBOX_FOLDER_ID": "inbox", "REQUESTED_FILE_ID": "", "GITHUB_OUTPUT": str(output)}):
                with patch("sys.argv", ["gdrive_bridge_io", "select", "--lane", "daily"]), patch("pipeline.gdrive_bridge_io.Drive") as client:
                    client.return_value.list_inbox.return_value = files
                    with redirect_stdout(io.StringIO()):
                        main()
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
