from __future__ import annotations

from pipeline.news_resolution import install as install_news_resolution
from pipeline.runtime_hardening import install as install_runtime_hardening


def main() -> None:
    base = install_runtime_hardening()
    base = install_news_resolution(base)
    base.main()


if __name__ == "__main__":
    main()
