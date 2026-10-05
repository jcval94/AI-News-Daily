import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.tts.benchmark import benchmark_status, benchmark_voices


class BenchmarkTests(unittest.TestCase):
    def test_local_benchmark_skips_edge_and_records_audio_format(self):
        output = Path(tempfile.mkdtemp())
        metrics = {
            "file_size_bytes": 100,
            "duration_seconds": 2.0,
            "sample_rate_hz": 48000,
            "channels": 1,
            "sample_width_bytes": 2,
            "peak_linear": 0.5,
            "peak_dbfs": -6.0,
            "rms_dbfs": -20.0,
            "clipping_suspected": False,
            "silent_suspected": False,
        }
        ffmpeg = {
            "available": True,
            "integrated_lufs": -20.0,
            "true_peak_dbfs": -6.0,
            "silence_events": [],
            "longest_silence_seconds": 0.0,
            "error": None,
        }
        with (
            patch(
                "pipeline.tts.benchmark.render_native",
                return_value={"generation_seconds": 1.0},
            ) as render,
            patch("pipeline.tts.benchmark._convert_edit"),
            patch("pipeline.tts.benchmark.inspect_wav", return_value=metrics),
            patch(
                "pipeline.tts.benchmark.inspect_ffmpeg_audio",
                return_value=ffmpeg,
            ),
        ):
            path = benchmark_voices(
                fixture=Path("evals/tts/voice_bakeoff_es.txt"),
                output_dir=output,
                config_path=Path("config/tts.yaml"),
                repo_root=Path("."),
            )

        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(all(item["engine"] != "edge" for item in payload["results"]))
        self.assertTrue(all(item["sample_rate_hz"] == 48000 for item in payload["results"]))
        self.assertEqual(payload["status"], "pass")
        self.assertTrue((output / "index.html").is_file())
        self.assertEqual(len(render.call_args_list), 5)

    def test_benchmark_status_fails_without_success(self):
        self.assertEqual(benchmark_status([]), "fail")
        self.assertEqual(benchmark_status([{"status": "error"}]), "fail")


if __name__ == "__main__":
    unittest.main()
