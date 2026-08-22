from __future__ import annotations

import unittest

from pipeline.run import _candidate_rank, _script_sha256


class BestCandidateTests(unittest.TestCase):
    def test_same_script_has_stable_hash_despite_whitespace(self) -> None:
        self.assertEqual(_script_sha256("hola   mundo"), _script_sha256("hola mundo"))

    def test_low_factuality_and_ai_smell_beat_higher_average_with_risk(self) -> None:
        gate = {"approved": False, "checks": {"a": True, "b": True}}
        safer = _candidate_rank(
            gate, {"score": 8.5, "factuality_risk": "low"}, {"score": 8.5}, {"score": 8.5},
            {"score": 8.5, "ai_smell_risk": "low", "intellectual_depth": 8.5, "human_relevance": 8.5},
        )
        riskier = _candidate_rank(
            gate, {"score": 9.5, "factuality_risk": "medium"}, {"score": 9.5}, {"score": 9.5},
            {"score": 9.5, "ai_smell_risk": "medium", "intellectual_depth": 9.5, "human_relevance": 9.5},
        )
        self.assertGreater(safer, riskier)


if __name__ == "__main__":
    unittest.main()
