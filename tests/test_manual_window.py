from __future__ import annotations

import os
import unittest
from datetime import date
from unittest.mock import patch

from pipeline.core import PipelineConfig, expected_news_dates


class ManualWindowTests(unittest.TestCase):
    def test_recent_window_allows_manual_run_on_any_day(self) -> None:
        with patch.dict(
            os.environ,
            {"NEWS_SOURCE_MODE": "recent_window", "NEWS_LOOKBACK_DAYS": "4"},
            clear=False,
        ):
            self.assertEqual(
                [item.isoformat() for item in expected_news_dates(date(2026, 8, 21))],
                ["2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"],
            )
            config = PipelineConfig.from_env()
            self.assertEqual(config.news_source_mode, "recent_window")
            self.assertEqual(config.news_lookback_days, 4)

    def test_scheduled_window_remains_the_default(self) -> None:
        with patch.dict(
            os.environ,
            {"NEWS_SOURCE_MODE": "scheduled_window"},
            clear=False,
        ):
            self.assertEqual(
                [item.isoformat() for item in expected_news_dates(date(2026, 8, 21))],
                ["2026-08-18", "2026-08-19", "2026-08-20"],
            )


if __name__ == "__main__":
    unittest.main()
