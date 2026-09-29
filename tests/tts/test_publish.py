import unittest
from pipeline.tts.publish import build_web_manifest


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
