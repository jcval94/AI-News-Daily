import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline.media_inspection import inspect_media, media_kind


class MediaInspectionTests(unittest.TestCase):
    def test_valid_and_broken_images_are_distinguished(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = root / "valid.png"
            broken = root / "broken.png"
            Image.new("RGB", (1280, 720), (20, 20, 20)).save(valid)
            broken.write_bytes(b"not-an-image")

            good = inspect_media(valid)
            bad = inspect_media(broken)

            self.assertTrue(good["ok"])
            self.assertEqual(good["width"], 1280)
            self.assertEqual(good["height"], 720)
            self.assertFalse(bad["ok"])
            self.assertEqual(bad["error_code"], "image_decode_failed")

    def test_media_kind_is_extension_based_for_preview_contract(self):
        self.assertEqual(media_kind("frame.webp"), "image")
        self.assertEqual(media_kind("clip.mp4"), "video")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg unavailable")
    def test_short_generated_video_is_probed_and_decoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.mp4"
            command = [
                shutil.which("ffmpeg"),
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=640x360:r=10:d=1",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

            inspection = inspect_media(path)
            self.assertTrue(inspection["ok"])
            self.assertEqual(inspection["kind"], "video")
            self.assertEqual(inspection["width"], 640)
            self.assertEqual(inspection["height"], 360)
            self.assertGreater(inspection["duration_seconds"], 0.8)


if __name__ == "__main__":
    unittest.main()
