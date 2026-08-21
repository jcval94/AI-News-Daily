from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from pipeline.run import load_selection_history


def write_episode(root: Path, episode_date: date, titles: list[str], covered_indices: list[int]) -> None:
    episode = root / episode_date.isoformat()
    episode.mkdir(parents=True)
    (episode / "reviews.json").write_text(json.dumps({"approved_for_multimedia": True}), encoding="utf-8")
    (episode / "selected_news.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": title,
                        "date": episode_date.isoformat(),
                        "source": "source",
                        "url": f"https://example.com/{title}",
                        "summary": title,
                    }
                    for title in titles
                ]
            }
        ),
        encoding="utf-8",
    )
    (episode / "episode_plan.json").write_text(
        json.dumps({"stories": [{"selected_news_index": index} for index in covered_indices]}),
        encoding="utf-8",
    )


class SelectionHistoryTests(unittest.TestCase):
    def test_only_covered_stories_are_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_episode(root, date(2026, 8, 20), ["used", "selected-only", "also-used"], [1, 3])
            history = json.loads(load_selection_history(root, date(2026, 8, 21), 30))
            self.assertEqual([item["title"] for item in history], ["used", "also-used"])

    def test_legacy_episode_without_plan_does_not_burn_selected_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "2026-08-20"
            episode.mkdir(parents=True)
            (episode / "reviews.json").write_text(json.dumps({"approved_for_multimedia": True}), encoding="utf-8")
            (episode / "selected_news.json").write_text(json.dumps({"items": [{"title": "unknown-use"}]}), encoding="utf-8")
            history = json.loads(load_selection_history(root, date(2026, 8, 21), 30))
            self.assertEqual(history, [])

    def test_history_keeps_newest_forty_covered_stories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = date(2026, 8, 21)
            for days_ago in range(1, 16):
                episode_date = target - timedelta(days=days_ago)
                titles = [f"d{days_ago}-item{i}" for i in range(1, 5)]
                write_episode(root, episode_date, titles, [1, 2, 3, 4])

            history = json.loads(load_selection_history(root, target, 30))
            titles = [item["title"] for item in history]
            self.assertEqual(len(titles), 40)
            self.assertIn("d1-item1", titles)
            self.assertIn("d10-item4", titles)
            self.assertNotIn("d11-item1", titles)
            self.assertNotIn("d15-item4", titles)


if __name__ == "__main__":
    unittest.main()
