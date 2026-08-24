from __future__ import annotations

from pipeline.runtime_hardening import install


def main() -> None:
    # review_media imports run_agent from pipeline.run. Install the hardened runtime first
    # so the dense planner inherits fail-fast quota handling and partial-usage telemetry.
    install()
    from pipeline.review_media_dense import main as dense_main

    dense_main()


if __name__ == "__main__":
    main()
