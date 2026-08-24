from __future__ import annotations

# Compatibility entrypoint. The review hub UI lives in review_hub_v10 so it can evolve
# independently from the workflow/module path already used in GitHub Actions and tests.
from pipeline.review_hub_v10 import build_site, main

__all__ = ["build_site", "main"]


if __name__ == "__main__":
    main()
