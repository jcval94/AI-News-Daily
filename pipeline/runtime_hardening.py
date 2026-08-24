from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any


_PERMANENT_QUOTA_MARKERS = (
    "insufficient_quota",
    "credit_balance_exhausted",
    "no credits remaining",
    "billing hard limit",
)


@dataclass
class _AgentCallFailure(Exception):
    original: Exception
    usage: dict[str, int]


def is_permanent_quota_error(exc: Exception) -> bool:
    """Return True only for quota/billing failures that will not heal with a retry."""
    parts = [str(exc)]
    for attr in ("code", "type", "message"):
        value = getattr(exc, attr, None)
        if value:
            parts.append(str(value))
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            parts.append(str(response.json()))
        except Exception:
            parts.append(str(response))
    haystack = " ".join(parts).lower()
    return any(marker in haystack for marker in _PERMANENT_QUOTA_MARKERS)


async def _run_agent_once(base: Any, agent: Any, initial_state: dict[str, Any], prompt: str) -> tuple[dict[str, Any], dict[str, int]]:
    service = base.InMemorySessionService()
    session_id = base.uuid.uuid4().hex
    await service.create_session(
        app_name=base.APP_NAME,
        user_id=base.USER_ID,
        session_id=session_id,
        state=initial_state,
    )
    runner = base.Runner(agent=agent, app_name=base.APP_NAME, session_service=service)
    message = base.types.Content(role="user", parts=[base.types.Part.from_text(text=prompt)])
    usage: dict[str, int] = {}
    seen_usage_event_ids: set[str] = set()
    try:
        async for event in runner.run_async(
            user_id=base.USER_ID,
            session_id=session_id,
            new_message=message,
        ):
            event_id = str(getattr(event, "id", ""))
            event_usage = base._usage_from_event(event)
            if event_usage and event_id not in seen_usage_event_ids:
                base._merge_usage(usage, event_usage)
                if event_id:
                    seen_usage_event_ids.add(event_id)
    except Exception as exc:
        # Preserve any usage already emitted by ADK before the stream failed.
        raise _AgentCallFailure(exc, dict(usage)) from exc

    session = await service.get_session(
        app_name=base.APP_NAME,
        user_id=base.USER_ID,
        session_id=session_id,
    )
    if session is None:
        raise _AgentCallFailure(RuntimeError("ADK session disappeared unexpectedly"), dict(usage))
    return dict(session.state), usage


async def _run_agent(
    base: Any,
    agent: Any,
    initial_state: dict[str, Any],
    prompt: str,
    *,
    step: str,
    trace: list[dict[str, Any]],
    iteration: int | None = None,
) -> dict[str, Any]:
    # Production generates dense multimedia in a dedicated post-script stage. Avoid paying
    # for the legacy sparse planner when the caller explicitly asks for zero media here.
    if step == "plan_multimedia":
        try:
            requested = int(initial_state.get("max_media_downloads", 0) or 0)
        except (TypeError, ValueError):
            requested = 0
        if requested <= 0:
            trace.append(
                {
                    "step": step,
                    "agent": getattr(agent, "name", type(agent).__name__),
                    "iteration": iteration,
                    "attempt": 0,
                    "status": "skipped",
                    "elapsed_seconds": 0.0,
                    "usage": {},
                    "reason": "dedicated_dense_media_stage",
                }
            )
            return {"multimedia_plan": {"segments": []}}

    last_error: Exception | None = None
    for attempt in range(1, base.CONFIG.agent_max_attempts + 1):
        started = time.monotonic()
        usage: dict[str, int] = {}
        try:
            state, usage = await _run_agent_once(base, agent, initial_state, prompt)
            trace.append(
                {
                    "step": step,
                    "agent": getattr(agent, "name", type(agent).__name__),
                    "iteration": iteration,
                    "attempt": attempt,
                    "status": "success",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "usage": usage,
                }
            )
            return state
        except _AgentCallFailure as wrapped:
            exc = wrapped.original
            usage = wrapped.usage
            last_error = exc
            permanent_quota = is_permanent_quota_error(exc)
            retryable = base.is_retryable_exception(exc) and not permanent_quota
            trace.append(
                {
                    "step": step,
                    "agent": getattr(agent, "name", type(agent).__name__),
                    "iteration": iteration,
                    "attempt": attempt,
                    "status": "error",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "retryable": retryable,
                    "permanent_quota_error": permanent_quota,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                    "usage": usage,
                }
            )
            if not retryable or attempt >= base.CONFIG.agent_max_attempts:
                raise exc
            delay = base.CONFIG.agent_retry_base_seconds * (2 ** (attempt - 1))
            print(
                f"Transient failure in {step}; retrying in {delay:.1f}s: "
                f"{type(exc).__name__}: {exc}"
            )
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error


def install() -> Any:
    """Patch pipeline.run once so every downstream importer receives hardened model calls."""
    from pipeline import run as base

    if getattr(base, "_RUNTIME_HARDENING_INSTALLED", False):
        return base

    async def hardened_once(agent: Any, initial_state: dict[str, Any], prompt: str) -> tuple[dict[str, Any], dict[str, int]]:
        return await _run_agent_once(base, agent, initial_state, prompt)

    async def hardened_run(
        agent: Any,
        initial_state: dict[str, Any],
        prompt: str,
        *,
        step: str,
        trace: list[dict[str, Any]],
        iteration: int | None = None,
    ) -> dict[str, Any]:
        return await _run_agent(
            base,
            agent,
            initial_state,
            prompt,
            step=step,
            trace=trace,
            iteration=iteration,
        )

    base._run_agent_once = hardened_once
    base.run_agent = hardened_run
    base._RUNTIME_HARDENING_INSTALLED = True
    return base
