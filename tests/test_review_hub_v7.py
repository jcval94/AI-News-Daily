from __future__ import annotations

import unittest

from pipeline.review_hub_v7 import apply_budget_workspace, budget_panel


class ReviewHubV7Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = {
            "budget": {
                "configured_usd": 1.0,
                "known_direct_cost_usd": 0.12,
                "remaining_usd": 0.88,
                "utilization_pct": 12.0,
                "status": "within_budget",
            },
            "totals": {
                "known_openai_cost_usd": 0.12,
                "pexels_known_cost_usd": 0.0,
                "github_actions_compute_known_cost_usd": 0.0,
                "known_direct_cost_usd": 0.12,
                "artifact_storage_gross_exposure_usd": 0.10,
            },
            "usage": {
                "prompt_tokens": 408_908,
                "output_tokens": 30_302,
                "reasoning_tokens": 0,
                "total_tokens": 439_210,
                "attempts_with_observed_usage": 25,
            },
            "pricing_snapshot": {
                "as_of": "2026-08-24",
                "production_model": "gpt-5.4-nano",
                "production_rate": {
                    "input_per_million": 0.2,
                    "output_per_million": 1.25,
                },
            },
            "multimedia": {
                "asset_count": 54,
                "pexels_assets": 54,
                "provider_counts": {"pexels": 54},
            },
            "github": {
                "raw_artifact_upload_bytes_estimate": 411_000_000,
            },
            "breakdown_by_step": [
                {
                    "scope": "production_pipeline",
                    "step": "select_news",
                    "agent": "selector",
                    "attempts": 1,
                    "errors": 0,
                    "prompt_tokens": 20_000,
                    "billable_output_tokens": 1_000,
                    "elapsed_seconds": 4.5,
                    "estimated_cost_usd": 0.00525,
                }
            ],
            "attempts": [
                {
                    "scope": "production_pipeline",
                    "sequence": 1,
                    "step": "select_news",
                    "agent": "selector",
                    "iteration": None,
                    "attempt": 1,
                    "status": "success",
                    "prompt_tokens": 20_000,
                    "output_tokens": 1_000,
                    "reasoning_tokens": 0,
                    "total_tokens": 21_000,
                    "elapsed_seconds": 4.5,
                    "estimated_cost_usd": 0.00525,
                }
            ],
            "coverage": {
                "known_direct_total_is_complete": True,
                "warnings": [],
            },
            "sources": {
                "openai": "https://example.com/openai",
                "pexels": "https://example.com/pexels",
                "github_actions": "https://example.com/actions",
                "github_storage": "https://example.com/storage",
            },
        }

    def test_budget_panel_contains_full_breakdown_and_download(self) -> None:
        panel = budget_panel(self.snapshot)
        self.assertIn("Budget &amp; Costs", panel)
        self.assertIn("Costo directo conocido", panel)
        self.assertIn("Pexels API", panel)
        self.assertIn("GitHub Actions compute", panel)
        self.assertIn("Artifact storage", panel)
        self.assertIn("Costo por paso", panel)
        self.assertIn("select_news", panel)
        self.assertIn("Ver cada intento del modelo", panel)
        self.assertIn("Cobertura de medición", panel)
        self.assertIn("downloads/cost_snapshot.json", panel)

    def test_workspace_adds_budget_as_sixth_top_level_tab(self) -> None:
        document = """<!doctype html><html><head><style></style></head><body>
<nav class="hub-tabs" role="tablist">
<button id="tab-overview" data-tab="overview">Overview</button>
<button id="tab-script" data-tab="script">Script</button>
<button id="tab-evidence" data-tab="evidence">Evidence</button>
<button id="tab-media" data-tab="media">Media</button>
<button id="tab-technical" data-tab="technical">Technical</button>
</nav>
<div id="panel-overview" class="hub-panel" data-panel="overview"></div>
<div id="panel-script" class="hub-panel" data-panel="script"></div>
<div id="panel-evidence" class="hub-panel" data-panel="evidence"></div>
<div id="panel-media" class="hub-panel" data-panel="media"></div>
<div id="panel-technical" class="hub-panel" data-panel="technical"></div>
</body></html>"""
        result = apply_budget_workspace(document, self.snapshot)
        self.assertIn('data-tab="budget"', result)
        self.assertIn('id="panel-budget"', result)
        self.assertLess(result.index('data-tab="budget"'), result.index('id="tab-technical"'))
        self.assertLess(result.index('id="panel-budget"'), result.index('id="panel-technical"'))
        self.assertIn("v7: dedicated FinOps", result)


if __name__ == "__main__":
    unittest.main()
