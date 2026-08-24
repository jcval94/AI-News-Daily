from __future__ import annotations

import unittest

from pipeline.review_hub_v8 import apply_e2e_workspace, process_panel


class ReviewHubV8Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = {
            "totals": {
                "known_direct_cost_usd": 0.12,
                "known_openai_cost_usd": 0.12,
                "pexels_known_cost_usd": 0.0,
                "wikimedia_known_cost_usd": 0.0,
                "generated_fallback_known_cost_usd": 0.0,
                "github_actions_compute_known_cost_usd": 0.0,
                "artifact_storage_gross_exposure_usd": 0.04,
            },
            "usage": {
                "prompt_tokens": 408_908,
                "output_tokens": 30_302,
                "reasoning_tokens": 2_000,
                "total_tokens": 441_210,
                "attempts_with_observed_usage": 25,
            },
            "pricing_snapshot": {
                "production_model": "gpt-5.4-nano",
                "production_rate": {
                    "input_per_million": 0.2,
                    "output_per_million": 1.25,
                },
            },
            "breakdown_by_step": [
                {"step": "select_news"},
                {"step": "plan_episode"},
                {"step": "write_script"},
            ],
            "attempts": [{"step": "select_news"}],
        }

    def test_process_panel_is_long_form_and_teaches_full_architecture(self) -> None:
        panel = process_panel(self.snapshot)
        self.assertIn("Cómo se fabrica un episodio", panel)
        self.assertIn("Dos capas que nunca deben confundirse", panel)
        self.assertIn("El recorrido completo", panel)
        self.assertIn("news_relevance_selector", panel)
        self.assertIn("editorial_director", panel)
        self.assertIn("script_refiner", panel)
        self.assertIn("multimedia_editor_master", panel)
        self.assertIn("Gate determinista de calidad", panel)
        self.assertIn("no_novel_essay_angle", panel)
        self.assertIn("execution_trace.json", panel)
        self.assertIn("run_report.json", panel)
        self.assertIn("Build AI News Video Kit", panel)
        self.assertIn("Editorial Regression", panel)
        self.assertIn("Editorial Review Hub / Pages", panel)
        self.assertIn("Costo directo conocido", panel)
        self.assertIn("$0.1200", panel)
        self.assertIn("441,210", panel)

    def test_workspace_adds_process_before_budget(self) -> None:
        document = """<!doctype html><html><head><style></style></head><body>
<nav class="hub-tabs" role="tablist">
<button id="tab-overview" data-tab="overview">Overview</button>
<button id="tab-script" data-tab="script">Script</button>
<button id="tab-evidence" data-tab="evidence">Evidence</button>
<button id="tab-media" data-tab="media">Media</button>
<button id="tab-budget" data-tab="budget">Budget</button>
<button id="tab-technical" data-tab="technical">Technical</button>
</nav>
<div id="panel-overview" class="hub-panel" data-panel="overview"></div>
<div id="panel-script" class="hub-panel" data-panel="script"></div>
<div id="panel-evidence" class="hub-panel" data-panel="evidence"></div>
<div id="panel-media" class="hub-panel" data-panel="media"></div>
<div id="panel-budget" class="hub-panel" data-panel="budget"></div>
<div id="panel-technical" class="hub-panel" data-panel="technical"></div>
</body></html>"""
        result = apply_e2e_workspace(document, self.snapshot)
        self.assertIn('data-tab="process"', result)
        self.assertIn('id="panel-process"', result)
        self.assertLess(result.index('data-tab="process"'), result.index('id="tab-budget"'))
        self.assertLess(result.index('id="panel-process"'), result.index('id="panel-budget"'))
        self.assertIn("v8: long-form E2E", result)
        self.assertIn("Proceso E2E", result)


if __name__ == "__main__":
    unittest.main()
