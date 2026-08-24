from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel, ValidationError

from pipeline.runtime_hardening import (
    _AgentCallFailure,
    _run_agent,
    is_model_output_validation_error,
    is_permanent_quota_error,
)


class _Contract(BaseModel):
    required_number: int


class RuntimeHardeningTests(unittest.TestCase):
    def test_permanent_quota_errors_fail_fast_classification(self) -> None:
        self.assertTrue(is_permanent_quota_error(RuntimeError("insufficient_quota")))
        self.assertTrue(is_permanent_quota_error(RuntimeError("credit_balance_exhausted")))
        self.assertTrue(is_permanent_quota_error(RuntimeError("You have no credits remaining")))
        self.assertFalse(is_permanent_quota_error(RuntimeError("rate limit exceeded; retry later")))

    def test_pydantic_output_validation_is_repairable(self) -> None:
        with self.assertRaises(ValidationError) as captured:
            _Contract.model_validate({"required_number": "not-a-number"})
        self.assertTrue(is_model_output_validation_error(captured.exception))
        self.assertFalse(is_model_output_validation_error(ValueError("ordinary local failure")))

    def test_schema_failure_retries_with_validation_feedback(self) -> None:
        with self.assertRaises(ValidationError) as captured:
            _Contract.model_validate({"required_number": "bad"})
        first_failure = _AgentCallFailure(captured.exception, {})
        runner = AsyncMock(
            side_effect=[
                first_failure,
                ({"result": "repaired"}, {"prompt_tokens": 10, "output_tokens": 2}),
            ]
        )
        base = SimpleNamespace(
            CONFIG=SimpleNamespace(agent_max_attempts=3, agent_retry_base_seconds=0.0),
            is_retryable_exception=lambda exc: False,
        )
        agent = SimpleNamespace(name="editorial_director")
        trace: list[dict] = []
        with patch("pipeline.runtime_hardening._run_agent_once", runner):
            result = asyncio.run(
                _run_agent(
                    base,
                    agent,
                    {},
                    "Build the episode plan.",
                    step="plan_episode",
                    trace=trace,
                )
            )
        self.assertEqual(result, {"result": "repaired"})
        self.assertEqual(runner.await_count, 2)
        second_prompt = runner.await_args_list[1].args[3]
        self.assertIn("Validation feedback", second_prompt)
        self.assertTrue(trace[0]["schema_repair"])
        self.assertTrue(trace[0]["retryable"])
        self.assertEqual(trace[1]["status"], "success")

    def test_zero_media_budget_skips_legacy_multimedia_model_call(self) -> None:
        base = SimpleNamespace(
            CONFIG=SimpleNamespace(agent_max_attempts=3, agent_retry_base_seconds=0.0),
            is_retryable_exception=lambda exc: True,
        )
        agent = SimpleNamespace(name="multimedia_editor_master")
        trace: list[dict] = []
        result = asyncio.run(
            _run_agent(
                base,
                agent,
                {"max_media_downloads": 0},
                "unused",
                step="plan_multimedia",
                trace=trace,
            )
        )
        self.assertEqual(result, {"multimedia_plan": {"segments": []}})
        self.assertEqual(trace[0]["status"], "skipped")
        self.assertEqual(trace[0]["reason"], "dedicated_dense_media_stage")


if __name__ == "__main__":
    unittest.main()
