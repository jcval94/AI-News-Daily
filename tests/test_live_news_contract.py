from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.news import parse_news_file, resolve_news_file, source_date_from_path


class LiveNewsContractTests(unittest.TestCase):
    def test_september_timestamped_sources_are_discoverable_and_structured(self) -> None:
        root = Path("news")
        expected = {
            "2026-09-01": "2026-09-01-08-23-09.txt",
            "2026-09-02": "2026-09-02-08-35-24.txt",
            "2026-09-03": "2026-09-03-08-45-35.txt",
        }
        for editorial_date, filename in expected.items():
            with self.subTest(editorial_date=editorial_date):
                path = resolve_news_file(root, editorial_date)
                self.assertIsNotNone(path)
                assert path is not None
                self.assertEqual(path.name, filename)
                self.assertEqual(source_date_from_path(path), editorial_date)
                items = parse_news_file(path)
                self.assertGreater(len(items), 0)
                self.assertTrue(all(item.source_file == filename for item in items))
                self.assertTrue(all(item.date for item in items))
                self.assertTrue(all(item.source for item in items))


if __name__ == "__main__":
    unittest.main()
