import struct
import tempfile
import unittest
import wave
from pathlib import Path

from pipeline.tts.audio_qa import inspect_wav, validate_edit_wav


class AudioQATests(unittest.TestCase):
    def test_inspects_pcm_wav(self):
        path = Path(tempfile.mkdtemp()) / "x.wav"
        with wave.open(str(path),"wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000)
            wav.writeframes(struct.pack("<h",1000)*4800)
        metrics=inspect_wav(path)
        self.assertAlmostEqual(metrics["duration_seconds"],0.1,places=3)
        self.assertEqual(metrics["sample_rate_hz"],48000)
        self.assertNotIn("sample_rate_mismatch",validate_edit_wav(metrics))
