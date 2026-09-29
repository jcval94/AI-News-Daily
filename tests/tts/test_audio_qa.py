import struct
import tempfile
import unittest
import wave
from pathlib import Path

from pipeline.tts.audio_qa import inspect_wav, validate_edit_wav, validate_ffmpeg_audio


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

    def test_ffmpeg_observations_are_advisory_and_explicit(self):
        warnings = validate_ffmpeg_audio(
            {
                "available": True,
                "integrated_lufs": -32.0,
                "longest_silence_seconds": 4.2,
            },
            long_silence_seconds=3.0,
            advisory_lufs_min=-28.0,
            advisory_lufs_max=-12.0,
        )
        self.assertIn("long_silence", warnings)
        self.assertIn("loudness_outside_advisory_band", warnings)
