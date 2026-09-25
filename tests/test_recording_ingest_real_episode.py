import json
import unittest
from pathlib import Path

from pipeline.recording_ingest import build_recording_ingest_contract


ROOT = Path(__file__).resolve().parents[1]
REAL_PACK = (
    ROOT
    / "docs"
    / "examples"
    / "recording_pack"
    / "2026-09-04"
    / "recording_pack.json"
)


class RealRecordingIngestContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads(REAL_PACK.read_text(encoding="utf-8"))

    def test_real_episode_contract_has_all_stable_take_ids(self):
        contract = build_recording_ingest_contract(self.pack)
        self.assertEqual(contract["episode_date"], "2026-09-04")
        self.assertEqual(contract["summary"]["expected_take_count"], 25)
        take_ids = [item["take_id"] for item in contract["expected_takes"]]
        self.assertEqual(take_ids[0], "opening_t01")
        self.assertEqual(take_ids[-1], "cta_t01")
        self.assertEqual(len(take_ids), len(set(take_ids)))

    def test_real_contract_remains_pre_alignment_without_recordings(self):
        contract = build_recording_ingest_contract(self.pack)
        self.assertEqual(contract["status"], "awaiting_recorded_media")
        self.assertFalse(contract["readiness"]["ready_for_alignment"])
        self.assertIn("recorded_media_required", contract["readiness"]["blockers"])
        self.assertTrue(contract["storage"]["never_commit_raw_recordings"])
        self.assertTrue(
            contract["selection_policy"]["technical_preferred_is_provisional"]
        )


if __name__ == "__main__":
    unittest.main()
