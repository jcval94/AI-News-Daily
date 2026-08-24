from __future__ import annotations

import unittest

from pipeline.review_hub_v9 import apply_current_architecture, process_panel


class ReviewHubV9Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = {
            "totals": {"known_direct_cost_usd": 0.12},
            "usage": {"total_tokens": 441_210, "attempts_with_observed_usage": 25},
            "breakdown_by_step": [{"step": "select_news"}, {"step": "refine_factual"}],
            "attempts": [{"step": "select_news"}],
        }

    def test_process_panel_matches_current_agentic_architecture(self) -> None:
        panel = process_panel(self.snapshot)
        self.assertIn("Claim Ledger", panel)
        self.assertIn("supported_facts", panel)
        self.assertIn("allowed_interpretations", panel)
        self.assertIn("prohibited_claims", panel)
        self.assertIn("factual_script_refiner", panel)
        self.assertIn("voice_script_refiner", panel)
        self.assertIn("secondary_script_refiner", panel)
        self.assertIn("_select_refinement_phase", panel)
        self.assertIn("Factual → voz → secundario", panel)
        self.assertNotIn("<code>script_refiner</code>", panel)
        self.assertIn("11 responsabilidades", panel)
        self.assertIn("Por qué el sistema está construido así", panel)

    def test_replaces_existing_process_panel_without_touching_other_tabs(self) -> None:
        document = """<html><body>
<div id="panel-process" class="hub-panel" data-panel="process"><section>OLD PROCESS</section></div>
<div id="panel-budget" class="hub-panel" data-panel="budget">BUDGET</div>
<div id="panel-technical" class="hub-panel" data-panel="technical">TECH</div>
</body></html>"""
        result = apply_current_architecture(document, self.snapshot)
        self.assertNotIn("OLD PROCESS", result)
        self.assertIn("Claim Ledger", result)
        self.assertIn("BUDGET", result)
        self.assertIn("TECH", result)
        self.assertEqual(result.count('id="panel-process"'), 1)


if __name__ == "__main__":
    unittest.main()
