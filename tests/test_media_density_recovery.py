from __future__ import annotations

import unittest

from pipeline.media_density_recovery import recommend_recovery_budget


class MediaDensityRecoveryTests(unittest.TestCase):
    def test_sep25_shape_gets_bounded_retry_without_relaxing_gate(self) -> None:
        retry = recommend_recovery_budget(
            {
                "ready": False,
                "blockers": ["unique_density:34<36"],
                "asset_count": 34,
                "attempted_asset_count": 54,
                "required_unique_assets": 36,
                "candidate_slot_count": 82,
            },
            current_attempt_budget=54,
        )
        self.assertEqual(retry, 60)

    def test_other_quality_blockers_do_not_trigger_recovery(self) -> None:
        retry = recommend_recovery_budget(
            {
                "ready": False,
                "blockers": ["unique_density:34<36", "timeline_reach:0.7000<0.8500"],
                "asset_count": 34,
                "attempted_asset_count": 54,
                "required_unique_assets": 36,
                "candidate_slot_count": 82,
            },
            current_attempt_budget=54,
        )
        self.assertIsNone(retry)

    def test_retry_is_capped_by_available_slots_and_extra_budget(self) -> None:
        retry = recommend_recovery_budget(
            {
                "ready": False,
                "blockers": ["unique_density:20<36"],
                "asset_count": 20,
                "attempted_asset_count": 54,
                "required_unique_assets": 36,
                "candidate_slot_count": 100,
            },
            current_attempt_budget=54,
            max_extra_attempts=8,
        )
        self.assertEqual(retry, 62)

        retry = recommend_recovery_budget(
            {
                "ready": False,
                "blockers": ["unique_density:20<36"],
                "asset_count": 20,
                "attempted_asset_count": 54,
                "required_unique_assets": 36,
                "candidate_slot_count": 58,
            },
            current_attempt_budget=54,
            max_extra_attempts=12,
        )
        self.assertEqual(retry, 58)

    def test_ready_or_exhausted_plan_does_not_retry(self) -> None:
        self.assertIsNone(
            recommend_recovery_budget(
                {
                    "ready": True,
                    "blockers": [],
                    "asset_count": 40,
                    "attempted_asset_count": 54,
                    "required_unique_assets": 36,
                    "candidate_slot_count": 82,
                },
                current_attempt_budget=54,
            )
        )
        self.assertIsNone(
            recommend_recovery_budget(
                {
                    "ready": False,
                    "blockers": ["unique_density:34<36"],
                    "asset_count": 34,
                    "attempted_asset_count": 54,
                    "required_unique_assets": 36,
                    "candidate_slot_count": 54,
                },
                current_attempt_budget=54,
            )
        )


if __name__ == "__main__":
    unittest.main()
