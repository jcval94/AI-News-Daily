from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pipeline import review_media as base
from pipeline.review_media_density import effective_budget, install_density_policy


def main() -> None:
    install_density_policy()
    args = base.parse_args()
    budget = effective_budget(args.max_media_downloads)
    result = asyncio.run(
        base.build_review_media(
            episode_dir=Path(args.episode_dir),
            output_dir=Path(args.output_dir),
            max_media_downloads=budget,
            zip_path=Path(args.zip_out),
        )
    )
    print(json.dumps({k: v for k, v in result.items() if k != "manifest"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
