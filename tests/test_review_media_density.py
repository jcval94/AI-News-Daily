from __future__ import annotations

import unittest

from pipeline.review_media_density import (
    DENSE_DEFAULT_MAX_MEDIA,
    dense_candidate_slots,
    effective_budget,
    install_density_policy,
)
from pipeline import review_media as review_media_base


class ReviewMediaDensityTests(unittest.TestCase):
    def test_minimum_supported_episode_can_satisfy_production_floor(self) -> None:
        sections = [
            {
                "position": 0,
                "section_key": "beat:minimum",
                "beat_id": "minimum",
                "beat_kind": "evidence",
                "evidence_ids": ["e1"],
                "start_seconds": 0.0,
                "end_seconds": 420.0,
            }
        ]
        slots = dense_candidate_slots(sections)
        opening = [slot for slot in slots if float(slot["start_seconds"]) < 20]

        self.assertGreaterEqual(len(slots), 45)
        self.assertGreaterEqual(len(opening), 5)
        self.assertGreaterEqual(float(slots[-1]["end_seconds"]), 410.0)

    def test_eleven_minute_episode_offers_more_than_triple_previous_media(self) -> None:
        sections = [
            {
                "position": index,
                "section_key": f"beat:b{index}",
                "beat_id": f"b{index}",
                "beat_kind": "turn" if index % 2 else "evidence",
                "evidence_ids": [f"e{index}"] if index % 2 == 0 else [],
                "start_seconds": index * 66.0,
                "end_seconds": (index + 1) * 66.0,
            }
            for index in range(10)
        ]
        slots = dense_candidate_slots(sections)
        opening = [slot for slot in slots if float(slot["start_seconds"]) < 20]
        late = [slot for slot in slots if float(slot["start_seconds"]) >= 20]

        self.assertEqual(len(opening), 6)
        self.assertGreaterEqual(len(slots), 54)
        self.assertGreater(len(slots), 45)
        self.assertGreater(len(late), 39)
        self.assertGreater(float(late[-1]["end_seconds"]), 630)

    def test_legacy_default_is_upgraded_to_dense_budget(self) -> None:
        self.assertEqual(DENSE_DEFAULT_MAX_MEDIA, 54)
        self.assertEqual(effective_budget(18), 54)
        self.assertEqual(effective_budget(60), 60)
        self.assertEqual(effective_budget(12), 12)

    def test_density_policy_fills_budget_and_keeps_video_mix(self) -> None:
        install_density_policy()
        sections = [
            {
                "position": 0,
                "section_key": "beat:test",
                "beat_id": "test",
                "beat_kind": "turn",
                "evidence_ids": [],
                "start_seconds": 0.0,
                "end_seconds": 660.0,
            }
        ]
        slots = review_media_base.build_review_candidate_slots(sections)
        plan = [
            {
                **slot,
                "mode": "media" if float(slot["start_seconds"]) < 20 else "presenter",
                "visual_query": "opening" if float(slot["start_seconds"]) < 20 else "",
                "on_screen_text": "",
            }
            for slot in slots
        ]
        dense = review_media_base.select_spread_media_budget(plan, max_media_downloads=54)
        media = [item for item in dense if item.get("mode") == "media"]
        late_media = [item for item in media if float(item["start_seconds"]) >= 20]
        late_video_first = [item for item in late_media if item.get("preferred_asset_type") == "video"]

        self.assertEqual(len(media), 54)
        self.assertGreaterEqual(len(late_video_first), 10)
        self.assertGreater(max(float(item["end_seconds"]) for item in media), 620)
        self.assertTrue(all(str(item.get("visual_query", "")).strip() for item in media))


if __name__ == "__main__":
    unittest.main()
