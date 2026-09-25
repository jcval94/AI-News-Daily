import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline.asset_readiness import build_asset_readiness, render_html, resolve_policy_path, write_asset_readiness


POLICY = {
    "schema_version": 1,
    "policy_id": "test",
    "mode": "enforce",
    "thresholds": {
        "min_planned_cue_count": 1,
        "min_resolved_cue_ratio": 0.80,
        "min_resolved_visual_seconds_ratio": 0.80,
        "max_missing_noncritical_cues": 3,
        "max_unresolved_critical_cues": 0,
        "max_technical_failure_cues": 0,
    },
    "quality": {
        "min_short_edge_px": 720,
        "min_video_duration_ratio": 0.75,
        "low_resolution_blocks": False,
        "short_video_blocks": False,
        "missing_license_label_blocks": False,
    },
    "critical_visual_roles": ["evidence", "historical_mirror"],
}


def _image(path: Path, size=(1280, 720)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (70, 70, 70)).save(path)


def payloads(root: Path):
    clips = []
    placements = []
    for i in range(5):
        clip_id = f"broll_{i+1:03d}_slot_{i+1:03d}"
        cue = f"slot_{i+1:03d}"
        placeholder = i == 4
        role = "evidence" if i == 0 else "context"
        clips.append({
            "clip_id": clip_id,
            "cue_id": cue,
            "status": "placeholder" if placeholder else "resolved",
            "duration_seconds": 5.0,
            "director": {"visual_role": role},
            "source": {"license": "test-license"},
        })
        logical = f"multimedia/2026-09-24/assets/{cue}.png"
        placements.append({
            "placement_id": clip_id,
            "track_id": "V2",
            "timeline_start_seconds": i * 5.0,
            "duration_seconds": 5.0,
            "logical_repo_path": (
                f"scripts/2026-09-24/placeholder_media/v2/{cue}.png"
                if placeholder else logical
            ),
            "placeholder": placeholder,
        })
        if not placeholder:
            _image(root / logical, size=(640, 360) if i == 1 else (1280, 720))
    virtual = {
        "episode_date": "2026-09-24",
        "tracks": [{"track_id": "V2", "clips": clips}],
    }
    resolve = {
        "episode_date": "2026-09-24",
        "placements": placements,
    }
    return virtual, resolve


class AssetReadinessTests(unittest.TestCase):
    def test_policy_path_prefers_checkout_over_isolated_run_root(self):
        resolved = resolve_policy_path(
            Path(".pipeline-runs/fake/run").resolve(),
            "config/asset_readiness.yaml",
        )
        self.assertTrue(resolved.is_file())
        self.assertTrue(str(resolved).endswith("config/asset_readiness.yaml"))

    def test_eighty_percent_coverage_with_low_res_warning_can_be_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            virtual, resolve = payloads(root)
            result = build_asset_readiness(
                virtual_timeline=virtual,
                resolve_plan=resolve,
                preview_validation=None,
                repo_root=root,
                policy=POLICY,
            )
            self.assertTrue(result["gate"]["ready_to_record"])
            self.assertEqual(result["summary"]["resolved_cue_ratio"], 0.8)
            self.assertEqual(result["summary"]["resolved_visual_seconds_ratio"], 0.8)
            self.assertEqual(result["summary"]["missing_cue_count"], 1)
            self.assertEqual(result["summary"]["degraded_cue_count"], 1)
            self.assertIn("low_resolution", result["gate"]["warnings"])
            self.assertEqual(result["gate"]["blockers"], [])

    def test_missing_critical_evidence_blocks_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            virtual, resolve = payloads(root)
            virtual["tracks"][0]["clips"][0]["status"] = "placeholder"
            resolve["placements"][0]["placeholder"] = True
            resolve["placements"][0]["logical_repo_path"] = (
                "scripts/2026-09-24/placeholder_media/v2/slot_001.png"
            )
            result = build_asset_readiness(
                virtual_timeline=virtual,
                resolve_plan=resolve,
                preview_validation=None,
                repo_root=root,
                policy=POLICY,
            )
            self.assertFalse(result["gate"]["ready_to_record"])
            self.assertEqual(result["summary"]["unresolved_critical_cue_count"], 1)
            self.assertIn("critical_visual_unresolved", result["gate"]["blockers"])

    def test_broken_resolved_asset_is_technical_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            virtual, resolve = payloads(root)
            broken = root / resolve["placements"][2]["logical_repo_path"]
            broken.write_bytes(b"not-an-image")
            result = build_asset_readiness(
                virtual_timeline=virtual,
                resolve_plan=resolve,
                preview_validation=None,
                repo_root=root,
                policy=POLICY,
            )
            self.assertFalse(result["gate"]["ready_to_record"])
            self.assertEqual(result["summary"]["technical_failure_cue_count"], 1)
            self.assertIn("technical_media_failure", result["gate"]["blockers"])

    def test_preview_decode_fallback_is_visible_as_degradation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            virtual, resolve = payloads(root)
            validation = {
                "warnings": [
                    {
                        "code": "preview_decode_fallback",
                        "placement_id": resolve["placements"][1]["placement_id"],
                    }
                ]
            }
            result = build_asset_readiness(
                virtual_timeline=virtual,
                resolve_plan=resolve,
                preview_validation=validation,
                repo_root=root,
                policy=POLICY,
            )
            target = next(x for x in result["items"] if x["clip_id"] == resolve["placements"][1]["placement_id"])
            self.assertEqual(target["state"], "resolved_degraded")
            self.assertIn("preview_decode_fallback", target["issues"])


    def test_zero_visual_cues_is_not_a_false_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_asset_readiness(
                virtual_timeline={"episode_date": "2026-09-24", "tracks": [{"track_id": "V2", "clips": []}]},
                resolve_plan={"episode_date": "2026-09-24", "placements": []},
                preview_validation=None,
                repo_root=Path(tmp),
                policy=POLICY,
            )
            self.assertFalse(result["gate"]["ready_to_record"])
            self.assertIn("no_planned_visual_cues", result["gate"]["blockers"])


    def test_enforced_block_persists_diagnosis_before_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "scripts" / "2026-09-24"
            episode.mkdir(parents=True)
            virtual = {
                "episode_date": "2026-09-24",
                "tracks": [{
                    "track_id": "V2",
                    "clips": [{
                        "clip_id": "broll_001_slot_001",
                        "cue_id": "slot_001",
                        "status": "placeholder",
                        "duration_seconds": 5.0,
                        "director": {"visual_role": "evidence"},
                        "source": {},
                    }],
                }],
            }
            resolve = {
                "episode_date": "2026-09-24",
                "placements": [{
                    "placement_id": "broll_001_slot_001",
                    "track_id": "V2",
                    "timeline_start_seconds": 0.0,
                    "duration_seconds": 5.0,
                    "logical_repo_path": "scripts/2026-09-24/placeholder_media/v2/slot_001.png",
                    "placeholder": True,
                }],
            }
            (episode / "virtual_timeline.json").write_text(json.dumps(virtual), encoding="utf-8")
            (episode / "resolve_bridge_plan.json").write_text(json.dumps(resolve), encoding="utf-8")
            policy_path = root / "asset_readiness.yaml"
            import yaml
            policy_path.write_text(yaml.safe_dump(POLICY), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "Asset readiness gate blocked"):
                write_asset_readiness(
                    repo_root=root,
                    episode_dir=episode,
                    policy_path=policy_path,
                    enforce=True,
                )
            self.assertTrue((episode / "asset_readiness.json").is_file())
            self.assertTrue((episode / "asset_readiness.html").is_file())
            saved = json.loads((episode / "asset_readiness.json").read_text(encoding="utf-8"))
            self.assertFalse(saved["gate"]["ready_to_record"])
            self.assertIn("critical_visual_unresolved", saved["gate"]["blockers"])

    def test_html_contains_operational_radiography(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            virtual, resolve = payloads(root)
            result = build_asset_readiness(
                virtual_timeline=virtual,
                resolve_plan=resolve,
                preview_validation=None,
                repo_root=root,
                policy=POLICY,
            )
            rendered = render_html(result)
            self.assertIn("Cue coverage", rendered)
            self.assertIn("Critical unresolved", rendered)
            self.assertIn("slot_001", rendered)


if __name__ == "__main__":
    unittest.main()
