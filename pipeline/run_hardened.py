from __future__ import annotations

from pipeline.runtime_hardening import install


def main() -> None:
    base = install()
    base.main()


if __name__ == "__main__":
    main()
