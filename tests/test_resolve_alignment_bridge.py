import tempfile
import unittest
from pathlib import Path

from pipeline.resolve_alignment_bridge import (
    build_resolve_alignment_plan,
    execute_resolve_media_sync,
)


def alignment_payload(*, external=True, video_trim_ready=True):
    return {
        "episode_date": "2026-09-25",
        "readiness": {
            "ready_for_aligned_timeline": bool(video_trim_ready),
        },
        "takes": [
            {
                "take_id": "opening_t01",
                "selected": {
                    "retake_number": 2,
                    "timebase": (
                        "video_source"
                        if video_trim_ready
                        else "external_audio_source"
                    ),
                    "video_trim_ready": bool(video_trim_ready),
                    "trim": {
                        "source_in_seconds": 1.0,
                        "source_out_seconds": 8.0,
                        "duration_seconds": 7.0,
                    },
                    "audio_source": "external" if external else "embedded",
                    "video": {
                        "relative_path": "opening_t01__r02__camA.mp4",
                    },
                    "external_audio": (
                        {"relative_path": "opening_t01__r02__audio.wav"}
                        if external
                        else None
                    ),
                },
            }
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


class FakeMediaItem:
    def __init__(self, path):
        self.path = path
        self.props = {}
    def GetClipProperty(self, key=None):
        if key is None:
            return dict(self.props)
        return self.props.get(key, "")


class FakeMediaPool:
    def __init__(self, *, verify_sync=True):
        self.root = FakeFolder("Master")
        self.current = self.root
        self.verify_sync = verify_sync
        self.imported = []
        self.sync_calls = []
    def GetRootFolder(self):
        return self.root
    def AddSubFolder(self, parent, name):
        folder = FakeFolder(name)
        parent.children.append(folder)
        return folder
    def SetCurrentFolder(self, folder):
        self.current = folder
        return True
    def ImportMedia(self, paths):
        item = FakeMediaItem(paths[0])
        self.imported.append((self.current.name, item))
        return [item]
    def AutoSyncAudio(self, items, settings):
        self.sync_calls.append((items, settings))
        if self.verify_sync:
            items[0].props["Synced Audio"] = "opening_t01__r02__audio.wav"
        return True


class FakeProject:
    def __init__(self, media_pool):
        self.media_pool = media_pool
    def GetMediaPool(self):
        return self.media_pool


class FakeManager:
    def __init__(self, media_pool):
        self.media_pool = media_pool
        self.project = None
        self.saved = False
    def GetProjectListInCurrentFolder(self):
        return [self.project_name] if self.project else []
    @property
    def project_name(self):
        return "AI News Daily · 2026-09-25"
    def CreateProject(self, name):
        self.project = FakeProject(self.media_pool)
        return self.project
    def LoadProject(self, name):
        return self.project
    def SaveProject(self):
        self.saved = True
        return True


class FakeResolve:
    AUDIO_SYNC_MODE = "mode_enum"
    AUDIO_SYNC_WAVEFORM = "waveform_enum"
    AUDIO_SYNC_CHANNEL_NUMBER = "channel_enum"
    AUDIO_SYNC_CHANNEL_AUTOMATIC = -1
    AUDIO_SYNC_RETAIN_EMBEDDED_AUDIO = "retain_audio_enum"
    AUDIO_SYNC_RETAIN_VIDEO_METADATA = "retain_video_metadata_enum"

    def __init__(self, *, verify_sync=True):
        self.pool = FakeMediaPool(verify_sync=verify_sync)
        self.manager = FakeManager(self.pool)
    def GetProjectManager(self):
        return self.manager


class ResolveAlignmentBridgeTests(unittest.TestCase):
    def test_plan_declares_resolve_waveform_sync(self):
        plan = build_resolve_alignment_plan(
            recording_alignment=alignment_payload(external=True)
        )
        self.assertTrue(plan["readiness"]["ready_for_media_sync"])
        self.assertEqual(plan["audio_sync"]["mode"], "waveform")
        self.assertTrue(plan["audio_sync"]["use_live_resolve_enum_constants"])
        self.assertEqual(plan["summary"]["waveform_sync_pair_count"], 1)
        self.assertEqual(
            plan["project"]["future_timeline_name"],
            "2026-09-25 · Aligned Rough Cut",
        )

    def test_external_timebase_blocks_aligned_timeline_build(self):
        plan = build_resolve_alignment_plan(
            recording_alignment=alignment_payload(
                external=True,
                video_trim_ready=False,
            )
        )
        self.assertFalse(plan["readiness"]["ready_for_media_sync"])
        self.assertIn(
            "video_timebase_unresolved:opening_t01",
            plan["readiness"]["blockers"],
        )

    def test_resolve_exec_uses_live_enum_keys_and_verifies_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "opening_t01__r02__camA.mp4").write_bytes(b"video")
            (root / "opening_t01__r02__audio.wav").write_bytes(b"audio")
            plan = build_resolve_alignment_plan(
                recording_alignment=alignment_payload(external=True)
            )
            fake = FakeResolve(verify_sync=True)
            result = execute_resolve_media_sync(
                plan,
                recordings_root=root,
                resolve=fake,
            )
            self.assertTrue(result["all_required_syncs_verified"])
            self.assertEqual(result["sync_pair_count"], 1)
            self.assertEqual(result["verified_sync_pair_count"], 1)
            self.assertFalse(result["timeline_created"])
            settings = fake.pool.sync_calls[0][1]
            self.assertEqual(settings["mode_enum"], "waveform_enum")
            self.assertEqual(settings["channel_enum"], -1)
            self.assertTrue(settings["retain_audio_enum"])
            self.assertTrue(fake.manager.saved)

    def test_resolve_exec_fails_closed_when_sync_cannot_be_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "opening_t01__r02__camA.mp4").write_bytes(b"video")
            (root / "opening_t01__r02__audio.wav").write_bytes(b"audio")
            plan = build_resolve_alignment_plan(
                recording_alignment=alignment_payload(external=True)
            )
            with self.assertRaisesRegex(RuntimeError, "could not be verified"):
                execute_resolve_media_sync(
                    plan,
                    recordings_root=root,
                    resolve=FakeResolve(verify_sync=False),
                )

    def test_embedded_audio_only_needs_no_waveform_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "opening_t01__r02__camA.mp4").write_bytes(b"video")
            plan = build_resolve_alignment_plan(
                recording_alignment=alignment_payload(external=False)
            )
            fake = FakeResolve()
            result = execute_resolve_media_sync(
                plan,
                recordings_root=root,
                resolve=fake,
            )
            self.assertEqual(result["sync_pair_count"], 0)
            self.assertEqual(fake.pool.sync_calls, [])
            self.assertTrue(result["all_required_syncs_verified"])


if __name__ == "__main__":
    unittest.main()
