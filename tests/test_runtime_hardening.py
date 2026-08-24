from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from pipeline.runtime_hardening import _run_agent, is_permanent_quota_error


class RuntimeHardeningTests(unittest.TestCase):
    def test_permanent_quota_errors_fail_fast_classification(self) -> None:
        self.assertTrue(is_permanent_quota_error(RuntimeError("insufficient_quota")))
        self.assertTrue(is_permanent_quota_error(RuntimeError("credit_balance_exhausted")))
        self.assertTrue(is_permanent_quota_error(RuntimeError("You have no credits remaining")))
        self.assertFalse(is_permanent_quota_error(RuntimeError("rate limit exceeded; retry later")))

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
