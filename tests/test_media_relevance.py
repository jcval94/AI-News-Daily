from __future__ import annotations

import unittest

from pipeline.media import media_relevance_score, select_best_candidate


class MediaRelevanceTests(unittest.TestCase):
    def test_security_dashboard_beats_decorative_scrabble(self) -> None:
        query = "cybersecurity monitoring dashboard"
        candidates = [
            {"candidate_text": "Scrabble tiles spelling SECURITY", "provider": "pexels"},
            {"candidate_text": "Cyber security monitoring dashboard with incident alerts", "provider": "wikimedia_commons"},
        ]
        best = select_best_candidate(query, candidates)
        self.assertIsNotNone(best)
        self.assertIn("dashboard", best["candidate_text"].lower())

    def test_unrelated_stock_photo_falls_below_relevant_diagram(self) -> None:
        query = "software patching workflow diagram"
        relevant = media_relevance_score(query, "software update patch workflow diagram showing deployment stages")
        generic = media_relevance_score(query, "businessman standing at whiteboard in office")
        self.assertGreater(relevant, generic)


if __name__ == "__main__":
    unittest.main()
