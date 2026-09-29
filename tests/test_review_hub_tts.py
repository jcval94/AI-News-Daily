import json
import tempfile
import unittest
from pathlib import Path

from pipeline.review_hub_v15 import apply_voice_panel


class ReviewHubTTSTests(unittest.TestCase):
    def _episode(self):
        root=Path(tempfile.mkdtemp())
        (root/"script_sections.json").write_text(json.dumps({"schema_version":4,"sections":[{"section_key":"opening","kind":"opening","beat_id":None,"beat_kind":None,"evidence_ids":[],"spoken_text":"Hola","word_count":1}]}),encoding="utf-8")
        (root/"episode_plan.json").write_text('{"beats":[],"evidence":[]}',encoding="utf-8")
        (root/"selected_news.json").write_text('{"items":[]}',encoding="utf-8")
        (root/"narrative_memory_selection.json").write_text('{"items":[]}',encoding="utf-8")
        return root

    def test_unavailable_panel_is_non_blocking(self):
        episode=self._episode()
        doc='<style></style><div id="scriptText" class="script" data-search-script></div>'
        out=apply_voice_panel(doc,episode_dir=episode)
        self.assertIn('data-tts-status="unavailable"',out)
        self.assertIn('No disponible',out)

    def test_available_audio_is_never_preloaded(self):
        episode=self._episode(); (episode/"tts").mkdir()
        (episode/"tts/narration_web.json").write_text(json.dumps({
            "schema_version":"1.0","available":True,"episode_date":"2026-09-25","script_id":"a"*64,
            "generated_at_utc":"2026-09-28T00:00:00Z","engine":"kokoro","voice":"ef_dora",
            "duration_seconds":12.0,"section_count":1,"qa_status":"pass","warnings":[],
            "master_preview_url":"https://example.com/master.mp3",
            "sections":[{"id":"opening","order":0,"kind":"opening","duration_seconds":12.0,"preview_url":"https://example.com/opening.mp3"}]
        }),encoding="utf-8")
        out=apply_voice_panel('<style></style><div id="scriptText" class="script" data-search-script></div>',episode_dir=episode)
        self.assertEqual(out.count('preload="none"'),2)
        self.assertIn('TTS disponible',out)
        self.assertIn('Introducción',out)

    def test_benchmark_candidates_are_lazy_and_share_common_text(self):
        episode=self._episode(); (episode/"tts").mkdir()
        (episode/"tts/benchmark_web.json").write_text(json.dumps({
            "schema_version":"1.0","available":True,
            "generated_at_utc":"2026-09-29T00:00:00Z",
            "fixture":"evals/tts/voice_bakeoff_es.txt",
            "common_text":"OpenAI, GPT-5 y 18.7 por ciento.",
            "candidates":[{
                "engine":"kokoro","voice":"ef_dora","status":"ok","error":None,
                "generation_seconds":0.5,"duration_seconds":2.0,"real_time_factor":0.25,
                "file_size_bytes":96000,"preview_url":"https://example.com/kokoro.mp3",
                "perceptual":{
                    "naturalness":None,"pronunciation":None,"prosody":None,
                    "energy":None,"clarity":None,"pace":None,"stability":None,
                    "notes":"manual listening only"
                }
            }]
        }),encoding="utf-8")
        out=apply_voice_panel('<style></style><div id="scriptText" class="script" data-search-script></div>',episode_dir=episode)
        self.assertIn('data-tts-benchmark="v1"',out)
        self.assertIn('Voice Bake-off',out)
        self.assertIn('OpenAI, GPT-5 y 18.7 por ciento.',out)
        self.assertIn('kokoro · ef_dora',out)
        self.assertEqual(out.count('preload="none"'),1)
