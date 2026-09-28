from __future__ import annotations

import unittest

from pipeline.media_density_gate import evaluate_dense_media_handoff


class MediaDensityGateTests(unittest.TestCase):
    def _manifest(self, count: int, opening: int = 5) -> list[dict]:
        items = []
        for index in range(count):
            start = float(index * 12)
            if index < opening:
                start = float(index * 3)
            items.append(
                {
                    "shot_number": index + 1,
                    "start_seconds": start,
                    "end_seconds": start + 4,
                }
            )
        return items

    def test_post_dedup_package_can_pass_when_density_was_attempted(self) -> None:
        report = evaluate_dense_media_handoff(
            manifest=self._manifest(39),
            plan={
                "candidate_slot_count": 54,
                "coverage_ratio": 0.9993,
                "deduplication": {"removed_count": 15},
            },
            budget=54,
        )
        self.assertTrue(report["ready"])
        self.assertEqual(report["required_unique_assets"], 36)
        self.assertEqual(report["attempted_asset_count"], 54)

    def test_raw_underproduction_still_fails(self) -> None:
        report = evaluate_dense_media_handoff(
            manifest=self._manifest(39),
            plan={
                "candidate_slot_count": 54,
                "coverage_ratio": 0.99,
                "deduplication": {"removed_count": 0},
            },
            budget=54,
        )
        self.assertFalse(report["ready"])
        self.assertTrue(any(item.startswith("attempted_density:") for item in report["blockers"]))

    def test_excessive_dedup_loss_still_fails_unique_density(self) -> None:
        report = evaluate_dense_media_handoff(
            manifest=self._manifest(25),
            plan={
                "candidate_slot_count": 54,
                "coverage_ratio": 0.99,
                "deduplication": {"removed_count": 29},
            },
            budget=54,
        )
        self.assertFalse(report["ready"])
        self.assertTrue(any(item.startswith("unique_density:") for item in report["blockers"]))

    def test_opening_and_timeline_reach_remain_hard_gates(self) -> None:
        report = evaluate_dense_media_handoff(
            manifest=self._manifest(40, opening=4),
            plan={
                "candidate_slot_count": 54,
                "coverage_ratio": 0.70,
                "deduplication": {"removed_count": 14},
            },
            budget=54,
        )
        self.assertFalse(report["ready"])
        self.assertTrue(any(item.startswith("opening_density:") for item in report["blockers"]))
        self.assertTrue(any(item.startswith("timeline_reach:") for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
