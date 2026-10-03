"""Dispatch deterministic checks after token-authenticated digest publication.

GITHUB_TOKEN pushes do not trigger downstream push workflows. Run only after a
verified publication/idempotent result, before acknowledging the Drive handoff.
No research, historical backfill, episode generation, or promotion happens here.
"""
from __future__ import annotations

import argparse
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from pipeline.news_ingestion_health import evaluate_daily_ingestion
from pipeline.production_preflight import TZ, next_scheduled_date


def dispatch_checks(day: date, repo: str, news_dir: Path, *, as_of: date | None = None) -> None:
    health = evaluate_daily_ingestion(day=day, news_dir=news_dir)
    if not health["healthy"]:
        raise ValueError(f"Cannot acknowledge unhealthy digest {day}: {health['reason']}")
    # A digest belongs to the first Tue/Fri window strictly after its date.
    target = next_scheduled_date(day + timedelta(days=1))
    checks = [("news-ingestion-watchdog.yml", f"date={day.isoformat()}")]
    local_today = as_of if as_of is not None else datetime.now(TZ).date()
    # Do not open false coverage incidents while future source days are pending.
    if target - timedelta(days=1) <= local_today:
        checks.append(("production-preflight.yml", f"target_date={target.isoformat()}"))
    for workflow, field in checks:
        subprocess.run(
            ["gh", "workflow", "run", workflow, "--repo", repo, "--ref", "main", "--field", field],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--news-dir", type=Path, default=Path("news"))
    args = parser.parse_args()
    dispatch_checks(date.fromisoformat(args.date), args.repo, args.news_dir)


if __name__ == "__main__":
    main()
