from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.readiness_history import build_dashboard, build_report, readiness_document


def _snapshot(target: str, score: float, generated: str, status: str = "ready") -> dict:
    return {
        "schema_version": 1,
        "generated_at_utc": generated,
        "target_date": target,
        "status": status,
        "readiness_score": score,
        "side_effect_free": True,
        "source_coverage": {
            "coverage_ratio": 1.0 if status == "ready" else 0.5,
            "missing_dates": [] if status == "ready" else ["2026-09-28"],
            "unparseable_dates": [],
        },
        "source_quality": {"score": 82.0, "band": "high", "observational_only": True},
    }


class ReadinessHistoryTests(unittest.TestCase):
    def test_keeps_latest_snapshot_per_target_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "a"
            newer = root / "b"
            other = root / "c"
            older.mkdir()
            newer.mkdir()
            other.mkdir()
            (older / "production-readiness.json").write_text(
                json.dumps(_snapshot("2026-09-29", 70, "2026-09-28T20:00:00Z", "at_risk")),
                encoding="utf-8",
            )
            (newer / "production-readiness.json").write_text(
                json.dumps(_snapshot("2026-09-29", 92, "2026-09-29T00:05:00Z")),
                encoding="utf-8",
            )
            (other / "production-readiness.json").write_text(
                json.dumps(_snapshot("2026-10-02", 88, "2026-10-01T23:59:00Z")),
                encoding="utf-8",
            )

            report = build_report(root)

            self.assertEqual(report["snapshot_count"], 2)
            self.assertEqual(report["snapshots"][0]["target_date"], "2026-10-02")
            rows = {row["target_date"]: row for row in report["snapshots"]}
            self.assertEqual(rows["2026-09-29"]["readiness_score"], 92)

    def test_dashboard_writes_html_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input"
            source.mkdir()
            (source / "production-readiness.json").write_text(
                json.dumps(_snapshot("2026-09-29", 92, "2026-09-28T23:59:00Z")),
                encoding="utf-8",
            )
            out = root / "out"
            json_path, html_path = build_dashboard(input_root=source, output_dir=out)

            self.assertTrue(json_path.is_file())
            self.assertTrue(html_path.is_file())
            document = html_path.read_text(encoding="utf-8")
            self.assertIn('data-readiness-page="production-readiness"', document)
            self.assertIn("Production Readiness", document)
            self.assertIn("Source quality", document)

    def test_empty_dashboard_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_report(Path(tmp))
            self.assertEqual(report["snapshot_count"], 0)
            self.assertIn("primer Production Preflight", readiness_document(report))


if __name__ == "__main__":
    unittest.main()
