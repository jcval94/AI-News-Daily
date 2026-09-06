from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.review_source import discover_episode_source


class ReviewSourceTests(unittest.TestCase):
    def _episode(
        self,
        root: Path,
        folder: str,
        *,
        episode_date: str,
        publishable: bool | None = True,
        status: str = "approved",
        rich: bool = True,
    ) -> Path:
        episode = root / folder
        episode.mkdir(parents=True, exist_ok=True)
        (episode / "script.txt").write_text("Guion válido\n", encoding="utf-8")
        state = {"episode_date": episode_date, "status": status}
        if publishable is not None:
            state["publishable"] = publishable
        (episode / "run_state.json").write_text(json.dumps(state), encoding="utf-8")
        if rich:
            (episode / "selected_news.json").write_text('{"items": []}', encoding="utf-8")
            (episode / "reviews.json").write_text('{}', encoding="utf-8")
            (episode / "episode_plan.json").write_text('{}', encoding="utf-8")
        return episode

    def test_artifact_and_directory_names_do_not_define_validity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "totally-renamed-artifact"
            expected = self._episode(
                root,
                "nested/custom/episode-alpha",
                episode_date="2026-09-04",
            )
            found = discover_episode_source(root)
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.episode_dir, expected)
            self.assertEqual(found.episode_date, "2026-09-04")

    def test_target_date_selects_matching_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._episode(root, "scripts/2026-09-01", episode_date="2026-09-01")
            expected = self._episode(root, "other/location", episode_date="2026-09-04")
            found = discover_episode_source(root, "2026-09-04")
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.episode_dir, expected)

    def test_approved_candidate_beats_newer_but_blocked_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved = self._episode(
                root,
                "a",
                episode_date="2026-09-04",
                publishable=True,
                status="approved",
            )
            self._episode(
                root,
                "z",
                episode_date="2026-09-05",
                publishable=False,
                status="script_not_approved",
            )
            found = discover_episode_source(root)
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.episode_dir, approved)

    def test_empty_script_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "scripts/2026-09-04"
            episode.mkdir(parents=True)
            (episode / "script.txt").write_text("\n", encoding="utf-8")
            self.assertIsNone(discover_episode_source(root))

    def test_date_named_legacy_episode_without_state_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "weird-root/2026-08-29"
            episode.mkdir(parents=True)
            (episode / "script.txt").write_text("Guion heredado", encoding="utf-8")
            found = discover_episode_source(root)
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.episode_date, "2026-08-29")


if __name__ == "__main__":
    unittest.main()
