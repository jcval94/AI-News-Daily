from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from app.agent import TensionCandidate, TensionScoutResult, tension_scout_agent
from pipeline.run import collect_social_signals


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


    def test_collect_social_signals_uses_recent_structured_catalogs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {
                "generated_at": "2026-08-28T09:00:00-06:00",
                "signals": [
                    {
                        "signal_id": "oversight_speed_gap",
                        "date": "2026-08-28",
                        "source": "Example primary source",
                        "url": "https://example.org/source",
                        "observation": "Human review is becoming a bottleneck in an automated workflow.",
                        "domains": ["work", "trust"],
                        "evidence_type": "report",
                    }
                ],
            }
            (root / "2026-08-28.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

            raw, files = collect_social_signals(root, date(2026, 8, 28), 14)

            self.assertIsNotNone(raw)
            decoded = json.loads(raw or "{}")
            self.assertEqual(decoded["signals"][0]["signal_id"], "oversight_speed_gap")
            self.assertEqual(files, [root / "2026-08-28.json"])

    def test_collect_social_signals_returns_none_without_catalogs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw, files = collect_social_signals(
                Path(tmp), date(2026, 8, 28), 14
            )
            self.assertIsNone(raw)
            self.assertEqual(files, [])


if __name__ == "__main__":
    unittest.main()
