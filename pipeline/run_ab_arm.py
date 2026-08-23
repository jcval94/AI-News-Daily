from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pipeline.run as base
import pipeline.run_context_budget as candidate

_ORIGINAL_USAGE_FROM_EVENT = base._usage_from_event
_ORIGINAL_IS_RETRYABLE_EXCEPTION = base.is_retryable_exception
_ALLOWED_ARMS = {"control", "candidate"}


def _usage_with_cache_from_event(event: Any) -> dict[str, int]:
    """Keep normal usage accounting and expose cache reads when ADK provides them."""
    result = _ORIGINAL_USAGE_FROM_EVENT(event)
    meta = getattr(event, "usage_metadata", None)
    if not meta:
        return result

    cached: int | None = None
    for name in (
        "cached_content_token_count",
        "cached_prompt_token_count",
        "cache_read_input_tokens",
    ):
        value = getattr(meta, name, None)
        if isinstance(value, int):
            cached = value
            break

    if cached is None:
        details = getattr(meta, "prompt_tokens_details", None)
        if isinstance(details, dict):
            value = details.get("cached_tokens")
            if isinstance(value, int):
                cached = value
        elif details is not None:
            value = getattr(details, "cached_tokens", None)
            if isinstance(value, int):
                cached = value

    if cached is not None:
        cached = max(0, cached)
        result["cached_prompt_tokens"] = cached
        prompt = result.get("prompt_tokens")
        if isinstance(prompt, int):
            result["uncached_prompt_tokens"] = max(0, prompt - cached)
    return result


def _ab_retryable_exception(exc: Exception) -> bool:
    """Do not burn retries on permanent quota/balance exhaustion returned as HTTP 429."""
    text = f"{type(exc).__name__}: {exc}".lower()
    permanent_quota_markers = (
        "insufficient_quota",
        "credit_balance_exhausted",
        "no credits remaining",
        "no credits left",
        "billing quota",
        "run out of credits",
    )
    if any(marker in text for marker in permanent_quota_markers):
        return False
    return _ORIGINAL_IS_RETRYABLE_EXCEPTION(exc)


def configured_arm() -> str:
    arm = os.getenv("AB_ARM", "control").strip().lower()
    if arm not in _ALLOWED_ARMS:
        raise ValueError(f"AB_ARM must be one of {sorted(_ALLOWED_ARMS)}, got {arm!r}")
    return arm


async def build(*, arm: str, **kwargs: Any) -> Path | None:
    if arm not in _ALLOWED_ARMS:
        raise ValueError(f"Unknown A/B arm: {arm}")

    previous_usage = base._usage_from_event
    previous_retryable = base.is_retryable_exception
    base._usage_from_event = _usage_with_cache_from_event
    base.is_retryable_exception = _ab_retryable_exception
    try:
        if arm == "candidate":
            return await candidate.build(**kwargs)
        return await base.build(**kwargs)
    finally:
        base._usage_from_event = previous_usage
        base.is_retryable_exception = previous_retryable


def main() -> None:
    args = base.parse_args()
    asyncio.run(
        build(
            arm=configured_arm(),
            target_date=base.parse_target_date(args.target_date),
            news_dir=Path(args.news_dir),
            scripts_root=Path(args.scripts_dir),
            multimedia_root=Path(args.multimedia_dir),
            history_scripts_root=Path(args.history_scripts_dir),
            max_media_downloads=args.max_media_downloads,
            download_multimedia=base.DOWNLOAD_MULTIMEDIA and not args.no_download_multimedia,
            editorial_dir=Path(args.editorial_dir),
        )
    )


if __name__ == "__main__":
    main()
