from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.agent import TensionCandidate, TensionScoutResult, tension_scout_agent


def candidate(tension_id: str, signal_id: str) -> TensionCandidate:
    return TensionCandidate(
        tension_id=tension_id,
        observation="Automated systems can act in more domains with less human intervention.",
        social_problem="Human oversight may not scale at the same rate as automated action.",
        human_tension="Speed and convenience increasingly conflict with meaningful human control.",
        central_mystery="What happens when acting becomes cheaper and faster than checking the result?",
        second_order_question="If intelligence becomes abundant, could trustworthy verification become scarce?",
        why_now="Recent source-backed signals show automated action moving into higher-stakes workflows.",
        affected_people=["workers", "users"],
        forces_in_conflict=["speed", "control"],
        signal_ids=[signal_id],
        evidence_needed=["paper", "dataset", "counterevidence"],
        potential_counterargument="Automation may also make verification faster and more reliable.",
        narrative_potential=9.0,
        social_relevance=9.0,
        researchability=8.5,
        freshness=8.0,
    )


class TensionScoutContractTests(unittest.TestCase):
    def test_contract_accepts_three_distinct_tensions(self) -> None:
        result = TensionScoutResult(
            candidates=[
                candidate("oversight_gap", "signal_1"),
                candidate("learning_gap", "signal_2"),
                candidate("trust_gap", "signal_3"),
            ]
        )
        self.assertEqual(len(result.candidates), 3)

    def test_contract_rejects_duplicate_tension_ids(self) -> None:
        with self.assertRaises(ValidationError):
            TensionScoutResult(
                candidates=[
                    candidate("same", "signal_1"),
                    candidate("same", "signal_2"),
                    candidate("other", "signal_3"),
                ]
            )

    def test_contract_rejects_duplicate_signal_ids_inside_candidate(self) -> None:
        bad = candidate("oversight_gap", "signal_1").model_copy(
            update={"signal_ids": ["signal_1", "signal_1"]}
        )
        with self.assertRaises(ValidationError):
            TensionScoutResult(
                candidates=[
                    bad,
                    candidate("learning_gap", "signal_2"),
                    candidate("trust_gap", "signal_3"),
                ]
            )

    def test_tension_scout_does_not_depend_on_news_text(self) -> None:
        instruction = str(tension_scout_agent.instruction)
        self.assertIn("{social_signals}", instruction)
        self.assertNotIn("{news_text}", instruction)


if __name__ == "__main__":
    unittest.main()
