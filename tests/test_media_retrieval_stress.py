from __future__ import annotations

import unittest
from pathlib import Path

from experiments.media_retrieval_stress.run import (
    DEFAULT_CASES,
    case_result,
    load_cases,
    make_need,
    normalize,
    summarize_match,
)
from pipeline.media import select_best_candidate
from pipeline.media_acquisition import need_description


class MultimediaRetrievalStressTests(unittest.TestCase):
    def test_core_profile_is_nontrivial_and_contains_canonical_franchise_case(self) -> None:
        cases = load_cases(DEFAULT_CASES, "core")
        self.assertGreaterEqual(len(cases), 10)
        time_wizard = next(case for case in cases if case["id"] == "franchise_yugioh_time_wizard")
        self.assertEqual(time_wizard["expected_mode"], "exact")
        self.assertIn("Time Wizard", time_wizard["visual_query"])
        self.assertTrue(time_wizard["may_be_rights_blocked"])

    def test_full_profile_covers_video_specific_failure_modes(self) -> None:
        cases = load_cases(DEFAULT_CASES, "full")
        categories = {case["category"] for case in cases}
        self.assertIn("video_clip_offset", categories)
        self.assertIn("video_metadata_visual_mismatch", categories)
        self.assertIn("quality_vs_identity", categories)
        self.assertIn("untrusted_metadata", categories)

    def test_localized_subject_stays_grounded_while_query_can_disambiguate(self) -> None:
        case = next(
            case for case in load_cases(DEFAULT_CASES, "core")
            if case["id"] == "franchise_yugioh_time_wizard"
        )
        need = make_need(case)
        description = need_description(need)
        self.assertIn("El Mago del Tiempo", description)
        self.assertIn("Yu-Gi-Oh Time Wizard", description)

    def test_normalization_handles_accents(self) -> None:
        self.assertEqual(normalize("mecanismo de Anticitera"), normalize("MECANISMO DE ANTICITERA"))
        self.assertEqual(normalize("Platón"), "platon")

    def test_matching_accepts_exact_alias_and_rejects_wrong_collision(self) -> None:
        case = next(
            case for case in load_cases(DEFAULT_CASES, "core")
            if case["id"] == "product_gemini_google_not_zodiac"
        )
        good = [{"title": "Google Gemini AI assistant", "description": "Google Gemini product demo"}]
        matched = summarize_match(case, "Google Gemini AI model interface", good)
        self.assertTrue(matched["pass"])
        self.assertEqual(matched["status"], "PASS_SELECTED")

        bad = [{"title": "Gemini zodiac constellation", "description": "horoscope signs"}]
        matched = summarize_match(case, "Google Gemini AI model interface", bad)
        self.assertFalse(matched["pass"])
        self.assertEqual(matched["status"], "FAIL_WRONG_ENTITY")

    def test_stock_ranker_prefers_specific_product_over_generic_collision(self) -> None:
        query = "Apple Vision Pro headset"
        candidates = [
            {"candidate_text": "red apple fruit in an orchard", "provider": "pexels"},
            {"candidate_text": "Apple Vision Pro headset mixed reality demonstration", "provider": "wikimedia_commons"},
        ]
        best = select_best_candidate(query, candidates)
        self.assertIsNotNone(best)
        self.assertIn("headset", best["candidate_text"].lower())

    def test_offline_corpus_mode_never_calls_live_retrieval(self) -> None:
        case = load_cases(DEFAULT_CASES, "core")[0]
        result = case_result(case, live=False)
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "CORPUS_VALID")


if __name__ == "__main__":
    unittest.main()
