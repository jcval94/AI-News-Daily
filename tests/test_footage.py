from __future__ import annotations

import unittest

from pipeline.footage import (
    build_search_queries,
    parse_iso8601_duration,
    rights_record,
    score_candidate,
)


class FootageDiscoveryTests(unittest.TestCase):
    def test_build_search_queries_prefers_title_plus_source(self) -> None:
        story = {
            "title": "Anthropic presenta una nueva técnica de interpretabilidad",
            "source": "Anthropic",
            "summary": "La empresa publicó una demostración técnica.",
        }
        queries = build_search_queries(story, limit=2)
        self.assertEqual(2, len(queries))
        self.assertIn("Anthropic", queries[0])
        self.assertIn("interpretabilidad", queries[0])

    def test_parse_iso8601_duration(self) -> None:
        self.assertEqual(3723, parse_iso8601_duration("PT1H2M3S"))
        self.assertEqual(45, parse_iso8601_duration("PT45S"))
        self.assertIsNone(parse_iso8601_duration("bad"))

    def test_primary_demo_classification_from_source_channel_match(self) -> None:
        story = {
            "title": "OpenAI presenta un nuevo sistema de agentes",
            "summary": "OpenAI mostró capacidades para agentes.",
            "source": "OpenAI",
            "date": "2026-08-27",
        }
        candidate = {
            "title": "Introducing our new agent system",
            "description": "OpenAI agent demonstration",
            "channel_title": "OpenAI",
            "published_at": "2026-08-27T15:00:00Z",
        }
        scored = score_candidate(story, candidate)
        self.assertIn(scored["footage_type"], {"DIRECT_EVENT", "PRIMARY_DEMO"})
        self.assertGreater(scored["relationship_score"], 0.25)

    def test_rights_never_assume_fair_use_or_download_permission(self) -> None:
        rights = rights_record({"license": "creativeCommon", "embeddable": True})
        self.assertTrue(rights["creative_commons_declared"])
        self.assertTrue(rights["embeddable"])
        self.assertFalse(rights["downloadable_via_youtube_api"])
        self.assertFalse(rights["publishable_permission_established"])
        self.assertEqual("NOT_ASSESSED", rights["fair_use_determination"])
        self.assertTrue(rights["manual_rights_review_required"])


if __name__ == "__main__":
    unittest.main()
