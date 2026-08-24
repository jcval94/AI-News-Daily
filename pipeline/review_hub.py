from __future__ import annotations

# Compatibility entrypoint. The review hub UI lives in review_hub_v11 so the
# living architecture and observed-run overlay can evolve behind a stable module path.
from pipeline.review_hub_v11 import build_site, main

__all__ = ["build_site", "main"]


if __name__ == "__main__":
    main()
