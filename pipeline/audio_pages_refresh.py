"""Fail-closed, metadata-only patch of a trusted complete Pages snapshot.

Never generate episodes, acquire media, or replace unrelated Pages sections.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

from pipeline.audio_library import DEFAULT_CATALOG, load_catalog
from pipeline.audio_library_pages import build_audio_library_page


REQUIRED = (
    "index.html",
    "episodes.json",
    "health/index.html",
    "memory/index.html",
    "memory/memory.js",
    "metrics/index.html",
    "experiments/index.html",
    "experiments/experiments.json",
)
_EPISODE_ID = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(?:-[A-Za-z0-9_-]+)?$")


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_snapshot(root: Path) -> list[Path]:
    """Accept only a complete, already-published multi-section Review Hub snapshot."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Pages snapshot root is missing or symlinked")
    files: list[Path] = []
    for relative in REQUIRED:
        file = root / relative
        if file.is_symlink() or not file.is_file() or file.stat().st_size == 0:
            raise ValueError(f"Missing or unsafe Pages snapshot file: {relative}")
        files.append(file)

    root_html = (root / "index.html").read_text(encoding="utf-8")
    if ('href="audio/index.html"' not in root_html
            or 'id="audioLibraryLink"' not in root_html
            or 'class="audio-mobile-link"' not in root_html
            or 'id="episodeFrame"' not in root_html):
        raise ValueError("Pages snapshot predates audio navigation; full rebuild required")

    meta = json.loads((root / "episodes.json").read_text(encoding="utf-8"))
    episodes = meta.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("Pages snapshot has no episode history")
    for episode in episodes:
        eid = str(episode.get("id", ""))
        if not _EPISODE_ID.fullmatch(eid):
            raise ValueError("Pages snapshot contains unsafe episode ID")
        path = root / "episodes" / eid / "index.html"
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Pages snapshot missing episode: {eid}")
        files.append(path)

    audio = root / "audio"
    if audio.is_symlink() or (audio.exists() and not audio.is_dir()):
        raise ValueError("Existing audio directory is unsafe")
    return files


def refresh_audio_pages(*, pages_root: Path, catalog: Path = DEFAULT_CATALOG) -> Path:
    """Replace only /audio/ after validating both catalog and complete baseline."""
    load_catalog(catalog)
    unchanged = validate_snapshot(pages_root)
    before = {p: _digest(p) for p in unchanged}
    audio = pages_root / "audio"

    with tempfile.TemporaryDirectory(dir=pages_root, prefix=".audio-refresh-") as tmp:
        staging = Path(tmp) / "new"
        build_audio_library_page(catalog=catalog, output_dir=staging)
        if not (staging / "index.html").is_file() or not (staging / "audio.js").is_file():
            raise ValueError("Audio build incomplete")
        previous = Path(tmp) / "old"
        if audio.exists():
            audio.rename(previous)
        try:
            staging.rename(audio)
        except Exception:
            if previous.exists():
                previous.rename(audio)
            raise

    for path, expected in before.items():
        if not path.is_file() or _digest(path) != expected:
            raise ValueError(f"Unexpected mutation outside /audio/: {path}")
    if not (audio / "index.html").is_file() or not (audio / "audio.js").is_file():
        raise ValueError("Audio publication is incomplete")
    return audio / "index.html"


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh /audio/ in an existing complete Pages snapshot")
    parser.add_argument("--pages-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()
    print(refresh_audio_pages(pages_root=args.pages_root, catalog=args.catalog))


if __name__ == "__main__":
    main()
