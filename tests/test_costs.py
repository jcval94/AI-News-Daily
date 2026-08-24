from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.costs import build_cost_snapshot


class CostSnapshotTests(unittest.TestCase):
    def test_cost_snapshot_prices_observed_usage_and_marks_unknown_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "episode"
            media = root / "media"
            output = root / "site"
            episode.mkdir()
            media.mkdir()
            output.mkdir()

            (episode / "run_report.json").write_text(
                json.dumps({"configuration": {"openai_model": "gpt-5.4-nano"}}),
                encoding="utf-8",
            )
            (episode / "execution_trace.json").write_text(
                json.dumps(
                    {
                        "agent_calls": [
                            {
                                "step": "write_script",
                                "agent": "writer",
                                "attempt": 1,
                                "status": "success",
                                "elapsed_seconds": 12.5,
                                "usage": {
                                    "prompt_tokens": 1_000_000,
                                    "output_tokens": 1_000_000,
                                    "reasoning_tokens": 0,
                                    "total_tokens": 2_000_000,
                                },
                            },
                            {
                                "step": "write_script",
                                "agent": "writer",
                                "attempt": 2,
                                "status": "error",
                                "elapsed_seconds": 2.0,
                                "error_type": "TimeoutError",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (media / "plan.json").write_text(
                json.dumps(
                    {
                        "agent_trace": [
                            {
                                "step": "review_plan_multimedia",
                                "agent": "multimedia_editor",
                                "attempt": 1,
                                "status": "success",
                                "elapsed_seconds": 3.0,
                                "usage": {
                                    "prompt_tokens": 500_000,
                                    "output_tokens": 100_000,
                                    "reasoning_tokens": 0,
                                    "total_tokens": 600_000,
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (media / "manifest.json").write_text(
                json.dumps(
                    [
                        {"provider": "pexels", "file": "one.mp4"},
                        {"provider": "pexels", "file": "two.jpg"},
                        {"provider": "generated_fallback", "file": "three.jpg"},
                    ]
                ),
                encoding="utf-8",
            )
            (media / "one.bin").write_bytes(b"x" * 1024)
            zip_path = root / "media.zip"
            zip_path.write_bytes(b"z" * 2048)
            pricing = root / "pricing.json"
            pricing.write_text(
                json.dumps(
                    {
                        "currency": "USD",
                        "as_of": "2026-08-24",
                        "models": {
                            "gpt-5.4-nano": {
                                "input_per_million": 0.20,
                                "cached_input_per_million": 0.02,
                                "output_per_million": 1.25,
                                "source": "https://example.com/openai",
                            }
                        },
                        "services": {
                            "pexels": {"usd_per_request": 0, "source": "https://example.com/pexels"},
                            "github_actions_standard_public_runner": {"usd_per_minute": 0, "source": "https://example.com/actions"},
                            "github_actions_artifact_storage": {
                                "usd_per_gb_month_over_included_allowance": 0.25,
                                "source": "https://example.com/storage",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            snapshot = build_cost_snapshot(
                episode_dir=episode,
                media_dir=media,
                media_zip=zip_path,
                output_dir=output,
                pricing_path=pricing,
                episode_budget_usd=2.0,
            )

            # Production: 1M * .20 + 1M * 1.25 = 1.45
            # Review planner: .5M * .20 + .1M * 1.25 = .225
            self.assertAlmostEqual(snapshot["totals"]["known_openai_cost_usd"], 1.675, places=6)
            self.assertAlmostEqual(snapshot["budget"]["known_direct_cost_usd"], 1.675, places=6)
            self.assertAlmostEqual(snapshot["budget"]["remaining_usd"], 0.325, places=6)
            self.assertAlmostEqual(snapshot["budget"]["utilization_pct"], 83.75, places=2)
            self.assertEqual(snapshot["usage"]["prompt_tokens"], 1_500_000)
            self.assertEqual(snapshot["usage"]["output_tokens"], 1_100_000)
            self.assertEqual(snapshot["usage"]["unmeasured_failed_attempts"], 1)
            self.assertFalse(snapshot["coverage"]["known_direct_total_is_complete"])
            self.assertFalse(snapshot["coverage"]["cached_input_discount_measured"])
            self.assertEqual(snapshot["multimedia"]["pexels_assets"], 2)
            self.assertEqual(snapshot["totals"]["pexels_known_cost_usd"], 0.0)
            self.assertEqual(snapshot["totals"]["github_actions_compute_known_cost_usd"], 0.0)
            self.assertGreater(len(snapshot["breakdown_by_step"]), 1)
            self.assertTrue(any("failed without persisted token usage" in item for item in snapshot["coverage"]["warnings"]))

    def test_reasoning_tokens_are_not_double_billed_when_total_already_contains_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "episode"
            media = root / "media"
            output = root / "site"
            episode.mkdir(); media.mkdir(); output.mkdir()
            (episode / "execution_trace.json").write_text(
                json.dumps(
                    {
                        "agent_calls": [
                            {
                                "step": "judge",
                                "agent": "judge",
                                "status": "success",
                                "attempt": 1,
                                "usage": {
                                    "prompt_tokens": 100,
                                    "output_tokens": 50,
                                    "reasoning_tokens": 25,
                                    "total_tokens": 175,
                                },
                            }
                        ]
                    }
                ), encoding="utf-8"
            )
            (media / "plan.json").write_text("{}", encoding="utf-8")
            (media / "manifest.json").write_text("[]", encoding="utf-8")
            zip_path = root / "media.zip"; zip_path.write_bytes(b"")
            pricing = root / "pricing.json"
            pricing.write_text(json.dumps({
                "currency": "USD",
                "models": {"gpt-5.4-nano": {"input_per_million": 1.0, "output_per_million": 1.0}},
                "services": {}
            }), encoding="utf-8")
            snapshot = build_cost_snapshot(
                episode_dir=episode, media_dir=media, media_zip=zip_path,
                output_dir=output, pricing_path=pricing
            )
            attempt = snapshot["attempts"][0]
            self.assertEqual(attempt["billable_output_tokens"], 75)


if __name__ == "__main__":
    unittest.main()
