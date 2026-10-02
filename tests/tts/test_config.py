import copy
import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.tts.config import load_tts_config


class TTSConfigTests(unittest.TestCase):
    def test_repository_config_is_valid(self):
        payload = load_tts_config(
            Path("config/tts.yaml")
        )
        self.assertEqual(
            payload["tts"]["engine"],
            "kokoro",
        )
        self.assertEqual(
            payload["tts"]["fallback"]["engine"],
            "piper",
        )
        self.assertEqual(
            payload["tts"]["edit_sample_rate_hz"],
            48000,
        )
        self.assertGreater(
            payload["tts"]["speech"]["pauses"]["default_ms"],
            0,
        )
        self.assertEqual(
            payload["tts"]["web"]["release"]["preview_prefix"],
            "tts-preview-",
        )

    def test_edge_cannot_be_automatic_fallback(self):
        payload = load_tts_config(
            Path("config/tts.yaml")
        )
        bad = copy.deepcopy(payload)
        bad["tts"]["fallback"] = {
            "enabled": True,
            "engine": "edge",
        }
        path = Path(tempfile.mkdtemp()) / "tts.yaml"
        path.write_text(
            yaml.safe_dump(bad, sort_keys=False),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            ValueError,
            "automatic fallback",
        ):
            load_tts_config(path)

    def test_speed_must_be_positive(self):
        payload = load_tts_config(
            Path("config/tts.yaml")
        )
        bad = copy.deepcopy(payload)
        bad["tts"]["speech"]["speed"] = 0
        path = Path(tempfile.mkdtemp()) / "tts.yaml"
        path.write_text(
            yaml.safe_dump(bad, sort_keys=False),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            ValueError,
            "speed",
        ):
            load_tts_config(path)

    def test_pause_must_be_bounded(self):
        payload = load_tts_config(
            Path("config/tts.yaml")
        )
        bad = copy.deepcopy(payload)
        bad["tts"]["speech"]["pauses"]["default_ms"] = -1
        path = Path(tempfile.mkdtemp()) / "tts.yaml"
        path.write_text(
            yaml.safe_dump(bad, sort_keys=False),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            ValueError,
            "default_ms",
        ):
            load_tts_config(path)


if __name__ == "__main__":
    unittest.main()
