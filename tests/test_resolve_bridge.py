import tempfile
import unittest
from pathlib import Path

from pipeline.placeholder_media import build_placeholder_manifest
from pipeline.resolve_bridge import build_resolve_plan, execute_resolve_plan


def virtual_payload():
    return {
        "episode_date": "2026-09-24",
        "timing": {"duration_seconds": 20},
        "format": {
            "resolution": "3840x2160",
            "frame_rate_fps": 30,
            "audio_sample_rate_hz": 48000,
            "aspect_ratio": "16:9",
        },
        "markers": [
            {"marker_id": "section_01", "kind": "section", "timeline_seconds": 0, "label": "Apertura", "section_key": "opening"},
            {"marker_id": "take_opening_t01", "kind": "take", "timeline_seconds": 0, "label": "opening_t01", "take_id": "opening_t01"},
        ],
        "tracks": [
            {"track_id": "V4", "clips": []},
            {"track_id": "V3", "clips": []},
            {
                "track_id": "V2",
                "clips": [
                    {
                        "clip_id": "broll_001",
                        "kind": "media_placeholder",
                        "status": "placeholder",
                        "cue_id": "slot_001",
                        "name": "paper screenshot",
                        "timeline_start_seconds": 4,
                        "timeline_end_seconds": 8,
                        "duration_seconds": 4,
                        "source": {"blockers": ["missing_manifest_asset"]},
                        "director": {"visual_role": "evidence"},
                    },
                    {
                        "clip_id": "broll_002",
                        "kind": "media_asset",
                        "status": "resolved",
                        "cue_id": "slot_002",
                        "name": "resolved clip",
                        "timeline_start_seconds": 12,
                        "timeline_end_seconds": 16,
                        "duration_seconds": 4,
                        "source": {
                            "logical_media_path": "multimedia/2026-09-24/assets/real.mp4",
                            "media_file": "assets/real.mp4",
                        },
                        "director": {"visual_role": "context"},
                    },
                ],
            },
            {
                "track_id": "V1",
                "clips": [
                    {
                        "clip_id": "aroll_001",
                        "kind": "virtual_a_roll",
                        "status": "placeholder",
                        "take_id": "opening_t01",
                        "replace_key": "opening_t01",
                        "name": "JC opening",
                        "timeline_start_seconds": 0,
                        "timeline_end_seconds": 10,
                        "duration_seconds": 10,
                        "section": {"section_label": "Apertura"},
                    },
                    {
                        "clip_id": "aroll_002",
                        "kind": "virtual_a_roll",
                        "status": "placeholder",
                        "take_id": "opening_t02",
                        "replace_key": "opening_t02",
                        "name": "JC opening 2",
                        "timeline_start_seconds": 10,
                        "timeline_end_seconds": 20,
                        "duration_seconds": 10,
                        "section": {"section_label": "Apertura"},
                    },
                ],
            },
            {"track_id": "A1", "clips": []},
        ],
    }


class FakeFolder:
    def __init__(self, name):
        self.name = name
        self.children = []
    def GetName(self):
        return self.name
    def GetSubFolderList(self):
        return list(self.children)


class FakeTimeline:
    def __init__(self, name):
        self.name = name
        self.video = 1
        self.audio = 1
        self.names = {}
        self.markers = []
    def GetName(self):
        return self.name
    def GetTrackCount(self, kind):
        return self.video if kind == "video" else self.audio
    def AddTrack(self, kind):
        if kind == "video":
            self.video += 1
        else:
            self.audio += 1
        return True
    def SetTrackName(self, kind, index, name):
        self.names[(kind, index)] = name
        return True
    def AddMarker(self, frame, color, name, note, duration, custom_data):
        self.markers.append((frame, color, name, note, duration, custom_data))
        return True


class FakeMediaPool:
    def __init__(self):
        self.root = FakeFolder("Master")
        self.current = self.root
        self.imports = []
        self.appended = []
        self.timeline = None
    def GetRootFolder(self):
        return self.root
    def AddSubFolder(self, parent, name):
        child = FakeFolder(name)
        parent.children.append(child)
        return child
    def SetCurrentFolder(self, folder):
        self.current = folder
        return True
    def ImportMedia(self, paths):
        item = {"path": paths[0], "bin": self.current.name}
        self.imports.append(item)
        return [item]
    def CreateEmptyTimeline(self, name):
        self.timeline = FakeTimeline(name)
        return self.timeline
    def AppendToTimeline(self, specs):
        self.appended.extend(specs)
        return [{"timeline_item": len(self.appended)}]


class FakeProject:
    def __init__(self):
        self.pool = FakeMediaPool()
        self.settings = {}
        self.timeline = None
    def SetSetting(self, key, value):
        self.settings[key] = value
        return True
    def GetMediaPool(self):
        return self.pool
    def GetTimelineCount(self):
        return 0
    def GetTimelineByIndex(self, index):
        return None
    def SetCurrentTimeline(self, timeline):
        self.timeline = timeline
        return True


class FakeManager:
    def __init__(self):
        self.project = FakeProject()
        self.saved = False
    def GetProjectListInCurrentFolder(self):
        return []
    def CreateProject(self, name):
        self.name = name
        return self.project
    def LoadProject(self, name):
        return self.project
    def SaveProject(self):
        self.saved = True
        return True


class FakeResolve:
    def __init__(self):
        self.manager = FakeManager()
    def GetProjectManager(self):
        return self.manager


class ResolveBridgeTests(unittest.TestCase):
    def _build(self, root: Path):
        episode = root / "scripts" / "2026-09-24"
        placeholders_dir = episode / "placeholder_media"
        placeholders_dir.mkdir(parents=True)
        virtual = virtual_payload()
        manifest = build_placeholder_manifest(
            virtual_timeline=virtual,
            output_dir=placeholders_dir,
            width=640,
            height=360,
        )
        real = root / "multimedia" / "2026-09-24" / "assets" / "real.mp4"
        real.parent.mkdir(parents=True)
        real.write_bytes(b"fake-video-for-resolve-plan")
        return virtual, manifest

    def test_plan_maps_tracks_bins_frames_and_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            virtual, manifest = self._build(root)
            plan = build_resolve_plan(
                virtual_timeline=virtual,
                placeholder_manifest=manifest,
                repo_root=root,
            )
            self.assertTrue(plan["readiness"]["ready_for_resolve_execution"])
            self.assertEqual(plan["summary"]["presenter_placeholder_count"], 2)
            self.assertEqual(plan["summary"]["broll_count"], 2)
            self.assertEqual(plan["summary"]["broll_placeholder_count"], 1)
            self.assertEqual(plan["summary"]["marker_count"], 2)
            v1 = [x for x in plan["placements"] if x["track_id"] == "V1"]
            v2 = [x for x in plan["placements"] if x["track_id"] == "V2"]
            self.assertEqual([x["track_index"] for x in v1], [1, 1])
            self.assertEqual([x["track_index"] for x in v2], [2, 2])
            self.assertEqual(v2[0]["record_frame"], 120)
            self.assertEqual(v2[1]["record_frame"], 360)

    def test_missing_physical_file_blocks_execution_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            virtual, manifest = self._build(root)
            (root / "multimedia" / "2026-09-24" / "assets" / "real.mp4").unlink()
            plan = build_resolve_plan(
                virtual_timeline=virtual,
                placeholder_manifest=manifest,
                repo_root=root,
            )
            self.assertFalse(plan["readiness"]["ready_for_resolve_execution"])
            self.assertTrue(
                any(item.startswith("missing_file:") for item in plan["readiness"]["blockers"])
            )

    def test_fake_resolve_executes_non_destructively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            virtual, manifest = self._build(root)
            plan = build_resolve_plan(
                virtual_timeline=virtual,
                placeholder_manifest=manifest,
                repo_root=root,
            )
            fake = FakeResolve()
            result = execute_resolve_plan(plan, repo_root=root, resolve=fake)
            self.assertEqual(result["status"], "resolve_bridge_v0_executed")
            self.assertEqual(result["imported_media_count"], 4)
            self.assertEqual(result["appended_placement_count"], 4)
            self.assertEqual(result["marker_count"], 2)
            self.assertTrue(fake.manager.saved)
            project = fake.manager.project
            self.assertEqual(project.settings["timelineResolutionWidth"], "3840")
            self.assertEqual(project.settings["timelineFrameRate"], "30")
            self.assertEqual(project.pool.timeline.video, 4)
            self.assertEqual(project.pool.timeline.names[("video", 1)], "V1 · JC A-Roll")
            self.assertFalse(result["final_edit_ready"])


if __name__ == "__main__":
    unittest.main()
