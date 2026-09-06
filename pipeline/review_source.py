from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_APPROVED_STATUSES = {"approved", "script_approved"}


@dataclass(frozen=True)
class EpisodeSource:
    episode_dir: Path
    episode_date: str
    script_path: Path
    publishable: bool | None
    status: str
    score: tuple[int, int, int, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "episode_dir": str(self.episode_dir),
            "episode_date": self.episode_date,
            "script_path": str(self.script_path),
            "publishable": self.publishable,
            "status": self.status,
        }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _date_from_state(episode_dir: Path) -> str:
    state = _read_json(episode_dir / "run_state.json")
    for key in ("episode_date", "target_date", "date"):
        value = str(state.get(key, "") or "").strip()
        if _DATE_RE.fullmatch(value):
            return value
    return ""


def _date_from_dir(episode_dir: Path) -> str:
    return episode_dir.name if _DATE_RE.fullmatch(episode_dir.name) else ""


def _date_from_artifacts(episode_dir: Path) -> str:
    for name in ("episode_plan.json", "selected_news.json", "reviews.json"):
        payload = _read_json(episode_dir / name)
        for key in ("episode_date", "target_date", "date"):
            value = str(payload.get(key, "") or "").strip()
            if _DATE_RE.fullmatch(value):
                return value
    return ""


def _state(episode_dir: Path) -> tuple[bool | None, str]:
    payload = _read_json(episode_dir / "run_state.json")
    status = str(payload.get("status", "") or "").strip().lower()
    publishable_raw = payload.get("publishable")
    publishable = publishable_raw if isinstance(publishable_raw, bool) else None
    return publishable, status


def _candidate_from_script(script_path: Path) -> EpisodeSource | None:
    try:
        if not script_path.read_text(encoding="utf-8").strip():
            return None
    except (OSError, UnicodeError):
        return None

    episode_dir = script_path.parent
    # A real episode normally has these contracts. Legacy artifacts may miss one,
    # so use them as ranking signals rather than brittle hard requirements.
    support_files = sum(
        int((episode_dir / name).exists())
        for name in ("run_state.json", "selected_news.json", "reviews.json", "episode_plan.json")
    )
    episode_date = (
        _date_from_state(episode_dir)
        or _date_from_dir(episode_dir)
        or _date_from_artifacts(episode_dir)
    )
    if not episode_date:
        return None

    publishable, status = _state(episode_dir)
    approved = publishable is True or status in _APPROVED_STATUSES
    explicitly_blocked = publishable is False and status and status not in _APPROVED_STATUSES
    # Prefer approved sources, then richer artifact contracts, then deterministic path order.
    score = (
        2 if approved else (0 if explicitly_blocked else 1),
        support_files,
        1 if "scripts" in episode_dir.parts else 0,
        str(script_path),
    )
    return EpisodeSource(
        episode_dir=episode_dir,
        episode_date=episode_date,
        script_path=script_path,
        publishable=publishable,
        status=status,
        score=score,
    )


def discover_episode_source(root: Path, target_date: str = "") -> EpisodeSource | None:
    """Find the strongest usable episode in an extracted artifact tree.

    The artifact name, workflow name, directory depth and exact scripts root are not
    part of the contract. The content is the contract: a non-empty script plus an
    inferable episode date, with approved/richer state preferred when available.
    """
    target = str(target_date or "").strip()
    candidates: list[EpisodeSource] = []
    if not root.exists():
        return None
    for script_path in root.rglob("script.txt"):
        candidate = _candidate_from_script(script_path)
        if candidate is None:
            continue
        if target and candidate.episode_date != target:
            continue
        candidates.append(candidate)
    return max(candidates, key=lambda item: item.score) if candidates else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve a valid episode from an extracted Actions artifact")
    parser.add_argument("--root", required=True)
    parser.add_argument("--target-date", default="")
    parser.add_argument("--output", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidate = discover_episode_source(Path(args.root), args.target_date)
    if candidate is None:
        raise SystemExit(2)
    payload = candidate.as_dict()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
