from __future__ import annotations

import unittest

from app.refiners import editorial_factual_refiner_agent, factual_refiner_agent
from pipeline import run
from pipeline.refinement_hardening import install


class RefinementHardeningTests(unittest.TestCase):
    def tearDown(self) -> None:
        run.factual_refiner_agent = factual_refiner_agent

    def test_install_replaces_only_first_phase_refiner(self) -> None:
        original_voice = run.voice_refiner_agent
        original_secondary = run.secondary_refiner_agent

        installed = install(run)

        self.assertIs(installed, run)
        self.assertIs(run.factual_refiner_agent, editorial_factual_refiner_agent)
        self.assertIs(run.voice_refiner_agent, original_voice)
        self.assertIs(run.secondary_refiner_agent, original_secondary)

    def test_recovery_refiner_can_act_on_editorial_and_factual_review(self) -> None:
        instruction = editorial_factual_refiner_agent.instruction.lower()

        self.assertIn("repair both classes", instruction)
        self.assertIn("news_text is the source of truth", instruction)
        self.assertIn("conceptual clarification", instruction)
        self.assertIn("do not optimize seo", instruction)
        self.assertIn("separate voice & humanity pass", instruction)

    def test_original_factual_refiner_remains_strictly_isolated(self) -> None:
        instruction = factual_refiner_agent.instruction.lower()
        self.assertIn("your only job is factual repair", instruction)
        self.assertIn("do not optimize voice", instruction)


if __name__ == "__main__":
    unittest.main()
