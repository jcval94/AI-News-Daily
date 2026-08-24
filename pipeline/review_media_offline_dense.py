from __future__ import annotations

import json
from pathlib import Path

from pipeline.review_media_density import effective_budget, install_density_policy

# Install before importing review_media_offline because that module binds candidate/budget helpers
# from pipeline.review_media at import time.
install_density_policy()
from pipeline import review_media_offline as base  # noqa: E402


def main() -> None:
    args = base.parse_args()
    budget = effective_budget(args.max_media_downloads)
    result = base.build_offline_review_media(
        episode_dir=Path(args.episode_dir),
        output_dir=Path(args.output_dir),
        max_media_downloads=budget,
        zip_path=Path(args.zip_out),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
