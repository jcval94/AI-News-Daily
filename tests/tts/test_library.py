import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.tts.contracts import write_manifest
from pipeline.tts.library import render_pending_library
from pipeline.tts.render import _script_id, approved_episodes


def _episode(root: Path, day: str, status: str | None = "approved") -> Path:
    path = root / "scripts" / day
    path.mkdir(parents=True)
    (path / "script.txt").write_text("Hola", encoding="utf-8")
    (path / "script_sections.json").write_text('{"sections": []}', encoding="utf-8")
    if status is not None:
        (path / "run_state.json").write_text(
            json.dumps({"status": status}), encoding="utf-8"
        )
    return path


def _run(
    root: Path,
    episode: Path,
    *,
    run_id: str = "20261005T000000Z-kokoro-test",
    script_id: str | None = None,
    qa: str = "pass",
) -> tuple[Path, dict]:
    run_dir = root / ".local" / "tts" / episode.name / run_id
    master = run_dir / "audio/edit/narration_master.wav"
    preview = run_dir / "web/narration_preview.mp3"
    master.parent.mkdir(parents=True)
    preview.parent.mkdir(parents=True)
    master.write_bytes(b"wav")
    preview.write_bytes(b"mp3")
    payload = {
        "schema_version": "1.0",
        "manifest_id": f"tts:{episode.name}:{run_id}",
        "run_id": run_id,
        "script_id": script_id or _script_id(episode),
        "episode_date": episode.name,
        "generated_at_utc": "2026-10-05T00:00:00Z",
        "status": "complete",
        "engine": {
            "requested": "kokoro",
            "used": "kokoro",
            "voice": "ef_dora",
            "language": "es",
            "local_first": True,
            "network_required": False,
        },
        "render": {
            "edit_sample_rate_hz": 48000,
            "channels": 1,
            "sample_format": "pcm_s16le",
            "speed": 1.0,
        },
        "source": {
            "script_path": f"scripts/{episode.name}/script.txt",
            "sections_path": f"scripts/{episode.name}/script_sections.json",
            "sections_schema_version": 1,
        },
        "files": {
            "master_edit": "audio/edit/narration_master.wav",
            "web_preview": "web/narration_preview.mp3",
        },
        "sections": [
            {
                "id": "opening",
                "order": 0,
                "section_key": "opening",
                "source_text": "Hola",
                "spoken_text": "Hola",
                "audio_native_file": "audio/native/sections/00_opening.wav",
                "audio_edit_file": "audio/edit/sections/00_opening.wav",
                "start_seconds": 0.0,
                "end_seconds": 1.0,
                "duration_seconds": 1.0,
                "qa": {"status": "pass", "warnings": []},
            }
        ],
        "metrics": {
            "section_count": 1,
            "duration_seconds": 1.0,
            "generation_seconds": 0.1,
            "real_time_factor": 0.1,
            "web_preview_size_bytes": 3,
        },
        "qa": {"status": qa, "warnings": [], "master": {}},
        "errors": [],
    }
    path = write_manifest(run_dir / "narration_manifest.json", payload)
    return path, payload


class TtsLibraryTests(unittest.TestCase):
    def test_only_modern_approved_episodes_are_selected(self):
        root = Path(tempfile.mkdtemp())
        approved = _episode(root, "2026-09-01")
        _episode(root, "2026-09-02", "failure")
        legacy = root / "scripts/2026-08-21"
        legacy.mkdir(parents=True)
        (legacy / "script.txt").write_text("legacy", encoding="utf-8")

        self.assertEqual(approved_episodes(root / "scripts"), [approved])

    def test_current_audio_is_reused_and_catalog_paths_are_relative(self):
        root = Path(tempfile.mkdtemp())
        episode = _episode(root, "2026-09-25")
        _run(root, episode)

        with patch("pipeline.tts.library.render_episode") as render:
            payload = render_pending_library(config_path=root / "tts.yaml", repo_root=root)

        render.assert_not_called()
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["summary"]["current"], 1)
        catalog = (root / ".local/tts/library/index.html").read_text(encoding="utf-8")
        self.assertNotIn(str(root), catalog)
        self.assertIn("narration_preview.mp3", catalog)
        self.assertIn("narration_master.wav", catalog)

    def test_changed_script_or_missing_asset_is_rendered_again(self):
        for cause in ("script", "asset"):
            with self.subTest(cause=cause):
                root = Path(tempfile.mkdtemp())
                episode = _episode(root, "2026-09-25")
                old_path, _ = _run(root, episode)
                if cause == "script":
                    (episode / "script.txt").write_text("Texto nuevo", encoding="utf-8")
                else:
                    (old_path.parent / "web/narration_preview.mp3").unlink()

                def render(**kwargs):
                    return _run(root, episode, run_id="20261006T000000Z-kokoro-test")

                with patch("pipeline.tts.library.render_episode", side_effect=render) as mocked:
                    payload = render_pending_library(
                        config_path=root / "tts.yaml", repo_root=root
                    )

                mocked.assert_called_once()
                self.assertEqual(payload["summary"]["rendered"], 1)

    def test_failure_does_not_block_other_episodes(self):
        root = Path(tempfile.mkdtemp())
        first = _episode(root, "2026-09-01")
        second = _episode(root, "2026-09-04")

        def render(*, episode_dir, **kwargs):
            if episode_dir == first:
                raise RuntimeError("engine failed")
            return _run(root, second)

        with patch("pipeline.tts.library.render_episode", side_effect=render):
            payload = render_pending_library(config_path=root / "tts.yaml", repo_root=root)

        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["summary"]["failed"], 1)
        self.assertEqual(payload["summary"]["rendered"], 1)
        self.assertEqual([item["episode_date"] for item in payload["episodes"]], [
            "2026-09-01",
            "2026-09-04",
        ])


if __name__ == "__main__":
    unittest.main()
