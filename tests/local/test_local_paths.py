import tempfile
import unittest
from pathlib import Path

from pipeline.local.paths import RootMap, looks_absolute


class LocalPathSafetyTests(unittest.TestCase):
    def test_windows_absolute_paths_are_detected_cross_platform(self):
        self.assertTrue(looks_absolute(r"C:\\Users\\JC\\video.mov"))
        self.assertTrue(looks_absolute(r"\\\\server\\share\\video.mov"))

    def test_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            roots = RootMap(root, root / "recordings", root / "work", root / "cache", root / "previews")
            with self.assertRaisesRegex(ValueError, "escapes root"):
                roots.resolve_ref({"root_id": "recordings", "relative_path": "../secret.txt"})

    def test_policy_can_disable_a_known_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            roots = RootMap(
                root,
                root / "recordings",
                root / "work",
                root / "cache",
                root / "previews",
                allowed_roots=frozenset({"repo", "work"}),
            )
            with self.assertRaises(PermissionError):
                roots.resolve_ref(
                    {
                        "root_id": "recordings",
                        "relative_path": "episode/clip.mov",
                    }
                )

    def test_known_roots_are_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            roots = RootMap(root, root / "recordings", root / "work", root / "cache", root / "previews")
            redacted = roots.redact(str(root / "recordings" / "episode" / "clip.mov"))
            self.assertNotIn(str(root), redacted)
            self.assertIn("<ROOT:recordings>", redacted)


if __name__ == "__main__":
    unittest.main()
