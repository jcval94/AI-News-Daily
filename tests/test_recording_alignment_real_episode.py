import json
import unittest
from pathlib import Path

import yaml

from pipeline.recording_alignment import build_alignment_contract


ROOT = Path(__file__).resolve().parents[1]
REAL_PACK = (
    ROOT
    / "docs"
    / "examples"
    / "recording_pack"
    / "2026-09-04"
    / "recording_pack.json"
)
POLICY = ROOT / "config" / "recording_alignment.yaml"


class RealRecordingAlignmentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads(REAL_PACK.read_text(encoding="utf-8"))
        cls.policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))

    def test_real_episode_alignment_contract_preserves_all_take_ids(self):
        contract = build_alignment_contract(
            recording_pack=self.pack,
            ingest_contract={"episode_date": "2026-09-04"},
            policy=self.policy,
        )
        take_ids = [item["take_id"] for item in contract["expected_takes"]]
        self.assertEqual(len(take_ids), 25)
        self.assertEqual(len(take_ids), len(set(take_ids)))
        self.assertEqual(take_ids[0], "opening_t01")
        self.assertEqual(take_ids[-1], "cta_t01")

    def test_real_episode_stays_pre_alignment_until_recordings_exist(self):
        contract = build_alignment_contract(
            recording_pack=self.pack,
            ingest_contract={"episode_date": "2026-09-04"},
            policy=self.policy,
        )
        self.assertFalse(contract["readiness"]["ready_for_transcription"])
        self.assertFalse(contract["readiness"]["ready_for_alignment"])
        self.assertIn(
            "recording_ingest_manifest_required",
            contract["readiness"]["blockers"],
        )
        self.assertEqual(
            contract["resolve_handoff"]["primary_postproduction_host"],
            "davinci_resolve",
        )
        self.assertEqual(
            contract["resolve_handoff"]["external_audio_sync"],
            "waveform",
        )
        self.assertTrue(
            contract["resolve_handoff"][
                "native_transcription_is_not_alignment_authority"
            ]
        )


if __name__ == "__main__":
    unittest.main()
