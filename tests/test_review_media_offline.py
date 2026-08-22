from __future__ import annotations

import unittest

from pipeline.review_media_offline import build_deterministic_plan


class OfflineReviewMediaTests(unittest.TestCase):
    def test_plan_keeps_dense_opening_and_full_narrative_arc(self) -> None:
        opening = [
            {
                "slot_number": index + 1,
                "start_seconds": index * 3.5,
                "end_seconds": min(20.0, (index + 1) * 3.5),
                "section_key": "opening",
                "beat_id": "",
                "beat_kind": "opening",
                "evidence_ids": [],
                "preferred_asset_type": "video",
                "slot_priority": "opening_dense_media",
            }
            for index in range(6)
        ]
        later = [
            {
                "slot_number": 7,
                "start_seconds": 80,
                "end_seconds": 84,
                "section_key": "beat:b1",
                "beat_id": "b1",
                "beat_kind": "first_reveal",
                "evidence_ids": ["traces"],
            },
            {
                "slot_number": 8,
                "start_seconds": 260,
                "end_seconds": 264,
                "section_key": "beat:b2",
                "beat_id": "b2",
                "beat_kind": "turn",
                "evidence_ids": [],
            },
            {
                "slot_number": 9,
                "start_seconds": 520,
                "end_seconds": 524,
                "section_key": "beat:b3",
                "beat_id": "b3",
                "beat_kind": "evolved_thesis",
                "evidence_ids": [],
            },
            {
                "slot_number": 10,
                "start_seconds": 640,
                "end_seconds": 644,
                "section_key": "synthesis",
                "beat_id": "",
                "beat_kind": "synthesis",
                "evidence_ids": [],
            },
        ]
        plan = build_deterministic_plan(
            episode_plan={
                "evidence": [{"evidence_id": "traces", "selected_news_index": 1}],
                "beats": [
                    {"beat_id": "b1", "kind": "first_reveal", "purpose": "Introduce auditable evidence", "evidence_ids": ["traces"]},
                    {"beat_id": "b2", "kind": "turn", "purpose": "Change the interpretation", "evidence_ids": []},
                    {"beat_id": "b3", "kind": "evolved_thesis", "purpose": "Land the evolved thesis", "evidence_ids": []},
                ],
            },
            selected_news={"items": [{"title": "TRACES benchmark for scientific discovery"}]},
            candidate_slots=opening + later,
            max_media_downloads=18,
        )
        media = [item for item in plan if item.get("mode") == "media"]
        opening_media = [item for item in media if float(item["start_seconds"]) < 20]
        self.assertEqual(len(opening_media), 6)
        self.assertTrue(all(item["preferred_asset_type"] == "video" for item in opening_media))
        self.assertEqual({item["section_key"] for item in media if item["start_seconds"] >= 20}, {"beat:b1", "beat:b2", "beat:b3", "synthesis"})
        self.assertGreater(max(float(item["end_seconds"]) for item in media), 600)
        b1 = next(item for item in media if item["section_key"] == "beat:b1")
        self.assertIn("TRACES benchmark", b1["visual_query"])

    def test_small_budget_preserves_opening_and_synthesis(self) -> None:
        slots = [
            {"slot_number": 1, "start_seconds": 0, "end_seconds": 4, "section_key": "opening", "beat_id": "", "beat_kind": "opening", "evidence_ids": []},
            {"slot_number": 2, "start_seconds": 4, "end_seconds": 8, "section_key": "opening", "beat_id": "", "beat_kind": "opening", "evidence_ids": []},
            {"slot_number": 3, "start_seconds": 8, "end_seconds": 12, "section_key": "opening", "beat_id": "", "beat_kind": "opening", "evidence_ids": []},
            {"slot_number": 4, "start_seconds": 12, "end_seconds": 16, "section_key": "opening", "beat_id": "", "beat_kind": "opening", "evidence_ids": []},
            {"slot_number": 5, "start_seconds": 16, "end_seconds": 20, "section_key": "opening", "beat_id": "", "beat_kind": "opening", "evidence_ids": []},
            {"slot_number": 6, "start_seconds": 200, "end_seconds": 204, "section_key": "beat:x", "beat_id": "x", "beat_kind": "turn", "evidence_ids": []},
            {"slot_number": 7, "start_seconds": 650, "end_seconds": 654, "section_key": "synthesis", "beat_id": "", "beat_kind": "synthesis", "evidence_ids": []},
        ]
        plan = build_deterministic_plan(
            episode_plan={"evidence": [], "beats": [{"beat_id": "x", "kind": "turn", "purpose": "Turn", "evidence_ids": []}]},
            selected_news={"items": []},
            candidate_slots=slots,
            max_media_downloads=6,
        )
        media = [item for item in plan if item.get("mode") == "media"]
        self.assertEqual(len(media), 6)
        self.assertEqual(len([item for item in media if item["start_seconds"] < 20]), 5)
        self.assertTrue(any(item["section_key"] == "synthesis" for item in media))


if __name__ == "__main__":
    unittest.main()
