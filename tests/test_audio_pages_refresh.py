from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.audio_pages_refresh import REQUIRED, refresh_audio_pages, validate_snapshot


def _setup(root: Path) -> tuple[Path, Path]:
    pages = root / "pages-site"
    for relative in REQUIRED:
        path = pages / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"episodes":[{"id":"2026-10-24"}]}'
                        if relative == "episodes.json"
                        else "dashboard fixture\n", encoding="utf-8")
    (pages / "index.html").write_text(
        '<a id="audioLibraryLink" href="audio/index.html">Sounds</a>'
        '<a class="audio-mobile-link" href="audio/index.html">Mobile</a>'
        '<iframe id="episodeFrame"></iframe>',
        encoding="utf-8",
    )
    episode = pages / "episodes" / "2026-10-24" / "index.html"
    episode.parent.mkdir(parents=True, exist_ok=True)
    episode.write_text("<h1>Previously published episode</h1>", encoding="utf-8")
    audio = pages / "audio"
    audio.mkdir()
    (audio / "obsolete.html").write_text("old version", encoding="utf-8")
    (pages / "episodes" / "2026-10-24" / "original-media.bin").write_bytes(
        b"Previously deployed heavy media must not be regenerated or lost."
    )
    catalog = root / "catalog.json"
    catalog.write_text('{"schema_version":1,"items":[]}', encoding="utf-8")
    return pages, catalog


def _hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file() and "audio" not in p.relative_to(root).parts
    }


class AudioPagesRefreshTests(unittest.TestCase):
    def test_replaces_only_audio_preserving_episodes_and_dashboards(self):
        with tempfile.TemporaryDirectory() as temp:
            pages, catalog = _setup(Path(temp))
            originals = _hashes(pages)
            output = refresh_audio_pages(pages_root=pages, catalog=catalog)
            self.assertEqual(output, pages / "audio/index.html")
            self.assertIn('data-audio-library="v1"', output.read_text(encoding="utf-8"))
            self.assertTrue((pages / "audio/audio.js").exists())
            self.assertFalse((pages / "audio/obsolete.html").exists())
            self.assertEqual(_hashes(pages), originals)

    def test_repeated_refresh_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            pages, catalog = _setup(Path(temp))
            first = refresh_audio_pages(pages_root=pages, catalog=catalog).read_bytes()
            second = refresh_audio_pages(pages_root=pages, catalog=catalog).read_bytes()
            self.assertEqual(first, second)

    def test_missing_dashboard_rejected_before_replacing_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            pages, catalog = _setup(Path(temp))
            (pages / "memory/index.html").unlink()
            with self.assertRaisesRegex(ValueError, "snapshot"):
                refresh_audio_pages(pages_root=pages, catalog=catalog)
            self.assertTrue((pages / "audio/obsolete.html").is_file())

    def test_old_snapshot_without_audio_navigation_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            pages, catalog = _setup(Path(temp))
            (pages / "index.html").write_text("<iframe id='episodeFrame'>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "predates"):
                refresh_audio_pages(pages_root=pages, catalog=catalog)

    def test_invalid_episode_or_missing_media_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            pages, catalog = _setup(Path(temp))
            (pages / "episodes.json").write_text(
                json.dumps({"episodes": [{"id": "../../bad"}]}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "unsafe episode"):
                refresh_audio_pages(pages_root=pages, catalog=catalog)
            self.assertTrue((pages / "audio/obsolete.html").exists())

    def test_bad_catalog_prevents_all_filesystem_mutations(self):
        with tempfile.TemporaryDirectory() as temp:
            pages, catalog = _setup(Path(temp))
            catalog.write_text('{"schema_version":2,"items":[]}', encoding="utf-8")
            original = _hashes(pages)
            with self.assertRaises(ValueError):
                refresh_audio_pages(pages_root=pages, catalog=catalog)
            self.assertEqual(_hashes(pages), original)
            self.assertTrue((pages / "audio/obsolete.html").exists())

    def test_audio_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pages, catalog = _setup(root)
            external = root / "external"
            external.mkdir()
            (pages / "audio/obsolete.html").unlink()
            (pages / "audio").rmdir()
            try:
                (pages / "audio").symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "unsafe"):
                validate_snapshot(pages)
            self.assertEqual(list(external.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
