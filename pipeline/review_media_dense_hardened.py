from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from pipeline.legacy_media_compat import prepare_legacy_media_episode
from pipeline.runtime_hardening import install


def _argument_value(name: str) -> tuple[int, str]:
    try:
        index = sys.argv.index(name)
    except ValueError as exc:
        raise SystemExit(f"Missing required argument {name}") from exc
    if index + 1 >= len(sys.argv):
        raise SystemExit(f"Missing value for {name}")
    return index + 1, sys.argv[index + 1]


def main() -> None:
    # review_media imports run_agent from pipeline.run. Install the hardened runtime first
    # so the dense planner inherits fail-fast quota handling and partial-usage telemetry.
    install()
    from pipeline.review_media_dense import main as dense_main

    value_index, episode_value = _argument_value("--episode-dir")
    source = Path(episode_value)
    if (source / "episode_plan.json").exists() and (source / "script_sections.json").exists():
        dense_main()
        return

    original_argv = list(sys.argv)
    with tempfile.TemporaryDirectory(prefix="legacy-media-") as tmp:
        compat = Path(tmp) / source.name
        prepare_legacy_media_episode(source, compat)
        sys.argv[value_index] = str(compat)
        try:
            dense_main()
        finally:
            sys.argv[:] = original_argv


if __name__ == "__main__":
    main()
