import unittest

from pipeline.tts.publish import build_benchmark_web_manifest, build_web_manifest


class PublishTests(unittest.TestCase):
    def test_web_contract_is_small_and_lazy_ready(self):
        source={
            "episode_date":"2026-09-25","script_id":"a"*64,"generated_at_utc":"2026-09-28T00:00:00Z",
            "engine":{"used":"kokoro","voice":"ef_dora"},
            "metrics":{"duration_seconds":10.0,"section_count":1},
            "qa":{"status":"pass","warnings":[]},
            "sections":[{"id":"opening","order":0,"kind":"opening","duration_seconds":10.0}]
        }
        web=build_web_manifest(source,master_url="https://example.com/master.mp3",section_urls={"opening":"https://example.com/opening.mp3"})
        self.assertTrue(web["available"])
        self.assertNotIn("spoken_text",web["sections"][0])
        self.assertEqual(web["sections"][0]["preview_url"],"https://example.com/opening.mp3")

    def test_benchmark_web_contract_keeps_manual_and_technical_metrics_separate(self):
        report={
            "schema_version":1,
            "generated_at_utc":"2026-09-29T00:00:00Z",
            "fixture":"evals/tts/voice_bakeoff_es.txt",
            "results":[{
                "engine":"kokoro","voice":"ef_dora","status":"ok","error":None,
                "generation_seconds":0.5,"duration_seconds":2.0,"real_time_factor":0.25,
                "file_size_bytes":96000,
                "perceptual":{
                    "naturalness":None,"pronunciation":None,"prosody":None,
                    "energy":None,"clarity":None,"pace":None,"stability":None,
                    "notes":"manual listening only",
                },
            }],
        }
        web=build_benchmark_web_manifest(
            report,
            common_text="OpenAI, GPT-5 y 18.7 por ciento.",
            preview_urls={"kokoro::ef_dora":"https://example.com/kokoro.mp3"},
        )
        self.assertTrue(web["available"])
        self.assertEqual(web["candidates"][0]["real_time_factor"],0.25)
        self.assertIsNone(web["candidates"][0]["perceptual"]["naturalness"])
        self.assertEqual(web["candidates"][0]["preview_url"],"https://example.com/kokoro.mp3")


if __name__ == "__main__":
    unittest.main()
