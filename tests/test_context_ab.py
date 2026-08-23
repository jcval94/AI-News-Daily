from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pipeline.context_ab_report import build_report
from pipeline.run_ab_arm import _ab_retryable_exception, _usage_with_cache_from_event


class ContextABRuntimeTests(unittest.TestCase):
    def test_cached_input_usage_is_exposed(self) -> None:
        event = SimpleNamespace(
            usage_metadata=SimpleNamespace(
                prompt_token_count=1000,
                candidates_token_count=100,
                thoughts_token_count=50,
                total_token_count=1150,
                cached_content_token_count=400,
            )
        )
        usage = _usage_with_cache_from_event(event)
        self.assertEqual(usage["prompt_tokens"], 1000)
        self.assertEqual(usage["cached_prompt_tokens"], 400)
        self.assertEqual(usage["uncached_prompt_tokens"], 600)

    def test_permanent_quota_exhaustion_is_not_retryable(self) -> None:
        exc = RuntimeError("429 insufficient_quota credit_balance_exhausted")
        self.assertFalse(_ab_retryable_exception(exc))


class ContextABReportTests(unittest.TestCase):
    def _write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _episode(self, root: Path, *, prompt: int, cached: int, score: float, candidate: bool) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "script.txt").write_text("word " * 1200, encoding="utf-8")
        self._write_json(root / "selected_news.json", {"items": [{"news_id": "a"}, {"news_id": "b"}]})
        self._write_json(root / "run_state.json", {"status": "approved"})
        self._write_json(
            root / "reviews.json",
            {
                "approved_for_multimedia": True,
                "editorial": {"score": score, "approved": True, "factuality_risk": "low"},
                "seo_master": {"score": score, "approved": True},
                "youtube_attention_master": {"score": score, "approved": True},
                "voice_humanity": {"score": score, "approved": True},
            },
        )
        self._write_json(
            root / "execution_trace.json",
            {
                "agent_calls": [
                    {
                        "status": "success",
                        "usage": {
                            "prompt_tokens": prompt,
                            "cached_prompt_tokens": cached,
                            "uncached_prompt_tokens": prompt - cached,
                            "output_tokens": 100,
                            "total_tokens": prompt + 100,
                        },
                    }
                ]
            },
        )
        if candidate:
            self._write_json(
                root / "context_budget.json",
                {
                    "all_discovery_sources_preserved": True,
                    "removed_source_items": 0,
                    "selected_item_count": 2,
                    "selected_exact_source_matches": 2,
                },
            )
        return root

    def test_gate_passes_when_quality_holds_and_prompt_cost_falls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            control = self._episode(base / "control", prompt=10000, cached=1000, score=9.0, candidate=False)
            candidate = self._episode(base / "candidate", prompt=8500, cached=900, score=8.9, candidate=True)
            report = build_report(control_dir=control, candidate_dir=candidate)
            self.assertTrue(report["comparison"]["gate_pass"])
            self.assertEqual(report["comparison"]["prompt_tokens"]["reduction_pct"], 15.0)

    def test_gate_fails_on_quality_regression_or_missing_cache_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            control = self._episode(base / "control", prompt=10000, cached=1000, score=9.0, candidate=False)
            candidate = self._episode(base / "candidate", prompt=8000, cached=500, score=8.4, candidate=True)
            trace_path = candidate / "execution_trace.json"
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            trace["agent_calls"][0]["usage"].pop("cached_prompt_tokens")
            trace["agent_calls"][0]["usage"].pop("uncached_prompt_tokens")
            trace_path.write_text(json.dumps(trace), encoding="utf-8")

            report = build_report(control_dir=control, candidate_dir=candidate)
            failures = report["comparison"]["failures"]
            self.assertFalse(report["comparison"]["gate_pass"])
            self.assertTrue(any(value.startswith("judge_regression:") for value in failures))
            self.assertIn("cached_uncached_input_telemetry_incomplete", failures)


if __name__ == "__main__":
    unittest.main()
