from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

_DATE_RE = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
_EPISODE_MARKERS = ('id="globalSearch"', 'data-tab="overview"')
_CATALOG_MARKERS = ('class="episode-sidebar"', 'id="episodeFrame"')


@dataclass(frozen=True)
class ArtifactMeta:
    artifact_id: int
    name: str
    run_id: int
    size_bytes: int
    created_at: str
    expired: bool = False

    @property
    def hint_score(self) -> int:
        lowered = self.name.casefold()
        score = 0
        if any(token in lowered for token in ("pages", "catalog", "site")):
            score += 3
        if any(token in lowered for token in ("review", "hub", "editorial")):
            score += 2
        if self.size_bytes <= 25 * 1024 * 1024:
            score += 2
        elif self.size_bytes <= 75 * 1024 * 1024:
            score += 1
        return score


def _created_ts(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def rank_artifacts(artifacts: Iterable[ArtifactMeta]) -> list[ArtifactMeta]:
    """Prioritize likely lightweight review sites but never require a naming convention."""
    return sorted(
        (item for item in artifacts if not item.expired),
        key=lambda item: (item.hint_score, _created_ts(item.created_at), -item.size_bytes),
        reverse=True,
    )


def parse_artifacts(payload: dict[str, Any]) -> list[ArtifactMeta]:
    parsed: list[ArtifactMeta] = []
    for raw in payload.get("artifacts", []) if isinstance(payload, dict) else []:
        if not isinstance(raw, dict):
            continue
        run = raw.get("workflow_run") if isinstance(raw.get("workflow_run"), dict) else {}
        try:
            parsed.append(
                ArtifactMeta(
                    artifact_id=int(raw.get("id")),
                    name=str(raw.get("name", "") or ""),
                    run_id=int(run.get("id")),
                    size_bytes=int(raw.get("size_in_bytes", 0) or 0),
                    created_at=str(raw.get("created_at", "") or ""),
                    expired=bool(raw.get("expired", False)),
                )
            )
        except (TypeError, ValueError):
            continue
    return parsed


def _read_text(path: Path, limit: int = 300_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _is_episode_site(index: Path) -> bool:
    text = _read_text(index)
    return bool(text) and all(marker in text for marker in _EPISODE_MARKERS)


def _is_catalog_site(index: Path) -> bool:
    text = _read_text(index)
    return bool(text) and all(marker in text for marker in _CATALOG_MARKERS)


def _date_from_path_or_text(path: Path, text: str, artifact_name: str = "") -> str:
    for value in (str(path), artifact_name, text):
        match = _DATE_RE.search(value)
        if match:
            return match.group(1)
    return ""


def discover_catalog_roots(root: Path) -> list[Path]:
    """Find extracted Pages snapshots by structure and HTML markers, not artifact name."""
    roots: list[Path] = []
    for episodes_json in root.rglob("episodes.json"):
        candidate = episodes_json.parent
        if not (candidate / "episodes").is_dir() or not (candidate / "index.html").is_file():
            continue
        if _is_catalog_site(candidate / "index.html"):
            roots.append(candidate)
    return roots


def discover_episode_sites(root: Path, artifact_name: str = "") -> list[tuple[str, Path]]:
    """Find standalone episode sites by their page contract, regardless of folder names."""
    found: list[tuple[str, Path]] = []
    for index in root.rglob("index.html"):
        if not _is_episode_site(index):
            continue
        text = _read_text(index)
        episode_date = _date_from_path_or_text(index, text, artifact_name)
        if episode_date:
            found.append((episode_date, index.parent))
    return found


def merge_catalog_snapshot(
    snapshot_root: Path,
    output_root: Path,
    seen_dates: set[str],
    limit: int,
) -> int:
    added = 0
    episodes_root = snapshot_root / "episodes"
    if not episodes_root.is_dir():
        return 0
    for episode_dir in sorted(episodes_root.iterdir(), reverse=True):
        if len(seen_dates) >= limit:
            break
        if not episode_dir.is_dir() or not _DATE_RE.fullmatch(episode_dir.name):
            continue
        if episode_dir.name in seen_dates or not (episode_dir / "index.html").is_file():
            continue
        if not _is_episode_site(episode_dir / "index.html"):
            continue
        destination = output_root / "episodes" / episode_dir.name
        shutil.copytree(episode_dir, destination, dirs_exist_ok=True)
        seen_dates.add(episode_dir.name)
        added += 1
    return added


def merge_episode_site(
    episode_date: str,
    site_root: Path,
    output_root: Path,
    seen_dates: set[str],
    limit: int,
) -> bool:
    if len(seen_dates) >= limit or episode_date in seen_dates:
        return False
    destination = output_root / "episodes" / episode_date
    shutil.copytree(site_root, destination, dirs_exist_ok=True)
    seen_dates.add(episode_date)
    return True


def _gh_json(repository: str) -> dict[str, Any]:
    command = [
        "gh",
        "api",
        f"repos/{repository}/actions/artifacts?per_page=100",
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)
    return payload if isinstance(payload, dict) else {}


def _download_artifact(meta: ArtifactMeta, destination: Path) -> bool:
    destination.mkdir(parents=True, exist_ok=True)
    command = [
        "gh",
        "run",
        "download",
        str(meta.run_id),
        "--name",
        meta.name,
        "--dir",
        str(destination),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    return completed.returncode == 0


def recover_history(
    *,
    repository: str,
    current_site: Path,
    current_date: str,
    output_root: Path,
    history_limit: int = 8,
    max_candidates: int = 32,
    max_legacy_bytes: int = 120 * 1024 * 1024,
    artifact_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Pages episode tree from current site + validated historical artifacts.

    New catalog snapshots are preferred because they recover many episodes with one
    download. Legacy review artifacts remain a bounded compatibility fallback. Names
    are ranking hints only; every artifact must pass structural/content validation.
    """
    history_limit = max(1, int(history_limit))
    max_candidates = max(1, int(max_candidates))
    output_root.mkdir(parents=True, exist_ok=True)
    episodes_root = output_root / "episodes"
    episodes_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(current_site, episodes_root / current_date, dirs_exist_ok=True)
    seen_dates = {current_date}

    payload = artifact_payload if artifact_payload is not None else _gh_json(repository)
    ranked = rank_artifacts(parse_artifacts(payload))[:max_candidates]
    diagnostics: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="pages-history-") as tmp:
        temp_root = Path(tmp)
        for position, meta in enumerate(ranked, start=1):
            if len(seen_dates) >= history_limit:
                break
            # Large legacy bundles are allowed only in a small bounded tail. This
            # prevents Pages rebuilds from being held hostage by multimedia archives.
            if meta.size_bytes > max_legacy_bytes and position > 8:
                diagnostics.append({"artifact": meta.name, "status": "skipped_too_large"})
                continue
            extracted = temp_root / f"{meta.run_id}-{meta.artifact_id}"
            if not _download_artifact(meta, extracted):
                diagnostics.append({"artifact": meta.name, "status": "download_failed"})
                continue

            added = 0
            for catalog_root in discover_catalog_roots(extracted):
                added += merge_catalog_snapshot(
                    catalog_root, output_root, seen_dates, history_limit
                )
                if len(seen_dates) >= history_limit:
                    break

            if len(seen_dates) < history_limit:
                for episode_date, site_root in discover_episode_sites(extracted, meta.name):
                    if merge_episode_site(
                        episode_date, site_root, output_root, seen_dates, history_limit
                    ):
                        added += 1
                    if len(seen_dates) >= history_limit:
                        break

            diagnostics.append(
                {
                    "artifact": meta.name,
                    "run_id": meta.run_id,
                    "size_bytes": meta.size_bytes,
                    "status": "accepted" if added else "not_a_review_site",
                    "episodes_added": added,
                }
            )

    return {
        "current_date": current_date,
        "episode_count": len(seen_dates),
        "episode_dates": sorted(seen_dates, reverse=True),
        "history_limit": history_limit,
        "candidates_considered": len(diagnostics),
        "diagnostics": diagnostics,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recover a bounded multi-episode Pages history")
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--current-site", required=True)
    parser.add_argument("--current-date", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--history-limit", type=int, default=8)
    parser.add_argument("--max-candidates", type=int, default=32)
    parser.add_argument("--report", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.repository:
        raise SystemExit("--repository or GITHUB_REPOSITORY is required")
    report = recover_history(
        repository=args.repository,
        current_site=Path(args.current_site),
        current_date=args.current_date,
        output_root=Path(args.output_root),
        history_limit=args.history_limit,
        max_candidates=args.max_candidates,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
