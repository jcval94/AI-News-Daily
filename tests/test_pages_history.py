from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.pages_history import (
    ArtifactMeta,
    discover_catalog_roots,
    discover_episode_sites,
    merge_catalog_snapshot,
    rank_artifacts,
    recover_history,
)


EPISODE_HTML = '''<!doctype html><html><body>
<div id="globalSearch"></div><button data-tab="overview"></button>
<p>{date}</p></body></html>'''
CATALOG_HTML = '''<!doctype html><html><body>
<nav class="episode-sidebar"></nav><iframe id="episodeFrame"></iframe>
</body></html>'''


class PagesHistoryTests(unittest.TestCase):
    def _episode_site(self, root: Path, date_value: str) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "index.html").write_text(
            EPISODE_HTML.format(date=date_value), encoding="utf-8"
        )
        return root

    def _snapshot(self, root: Path, dates: list[str]) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "index.html").write_text(CATALOG_HTML, encoding="utf-8")
        (root / "episodes.json").write_text(json.dumps(dates), encoding="utf-8")
        for value in dates:
            self._episode_site(root / "episodes" / value, value)
        return root

    def test_catalog_discovery_uses_structure_not_folder_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self._snapshot(root / "arbitrary/deep/name", ["2026-09-01"])
            self.assertEqual(discover_catalog_roots(root), [expected])

    def test_episode_discovery_uses_html_contract_not_artifact_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self._episode_site(root / "whatever/site", "2026-09-04")
            found = discover_episode_sites(root, "totally-random-artifact")
            self.assertEqual(found, [("2026-09-04", expected)])

    def test_snapshot_merges_multiple_distinct_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._snapshot(
                root / "snapshot", ["2026-09-04", "2026-09-01", "2026-08-29"]
            )
            output = root / "pages"
            (output / "episodes").mkdir(parents=True)
            seen = {"2026-09-05"}
            added = merge_catalog_snapshot(snapshot, output, seen, limit=3)
            self.assertEqual(added, 2)
            self.assertEqual(len(seen), 3)

    def test_artifact_rank_prefers_lightweight_review_hint_but_names_are_not_required(self) -> None:
        artifacts = [
            ArtifactMeta(1, "random-heavy", 1, 200_000_000, "2026-09-06T10:00:00Z"),
            ArtifactMeta(2, "anything", 2, 2_000_000, "2026-09-06T09:00:00Z"),
            ArtifactMeta(3, "pages-snapshot", 3, 5_000_000, "2026-09-06T08:00:00Z"),
        ]
        ranked = rank_artifacts(artifacts)
        self.assertEqual(ranked[0].name, "pages-snapshot")
        self.assertIn("anything", [item.name for item in ranked])

    def test_recover_history_accepts_renamed_snapshot_by_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = self._episode_site(root / "current", "2026-09-05")
            extracted = root / "downloaded"
            self._snapshot(extracted / "mystery-folder", ["2026-09-04", "2026-09-01"])
            payload = {
                "artifacts": [
                    {
                        "id": 10,
                        "name": "completely-renamed",
                        "size_in_bytes": 1024,
                        "created_at": "2026-09-06T10:00:00Z",
                        "expired": False,
                        "workflow_run": {"id": 99},
                    }
                ]
            }

            def fake_download(meta, destination):
                import shutil
                shutil.copytree(extracted, destination, dirs_exist_ok=True)
                return True

            with patch("pipeline.pages_history._download_artifact", side_effect=fake_download):
                report = recover_history(
                    repository="owner/repo",
                    current_site=current,
                    current_date="2026-09-05",
                    output_root=root / "pages",
                    history_limit=3,
                    artifact_payload=payload,
                )
            self.assertEqual(report["episode_count"], 3)
            self.assertEqual(
                set(report["episode_dates"]),
                {"2026-09-05", "2026-09-04", "2026-09-01"},
            )


if __name__ == "__main__":
    unittest.main()
