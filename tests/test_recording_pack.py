import json
import tempfile
import unittest
from pathlib import Path

from pipeline.recording_pack import (
    build_recording_pack,
    render_teleprompter,
    split_recording_takes,
    write_recording_pack,
)


class RecordingPackTests(unittest.TestCase):
    def test_take_splitter_preserves_narration_and_reasonable_duration(self):
        sentence = "Esta es una oración suficientemente clara para probar el corte automático."
        text = " ".join([sentence] * 14)
        takes = split_recording_takes(
            text,
            words_per_second=2.5,
            min_seconds=20,
            target_seconds=35,
            max_seconds=60,
        )
        self.assertGreater(len(takes), 1)
        self.assertEqual(" ".join(" ".join(takes).split()), " ".join(text.split()))
        for take in takes:
            duration = len(take.split()) / 2.5
            self.assertLessEqual(duration, 60.5)

    def test_pack_reconstructs_approved_script_and_keeps_cta_separate(self):
        script = (
            "Primera idea con suficiente contexto para explicar el problema con claridad. "
            "Segunda idea que continúa el argumento y conserva el sentido del ensayo."
        )
        sections = {
            "sections": [
                {
                    "section_key": "opening",
                    "kind": "opening",
                    "beat_id": None,
                    "beat_kind": None,
                    "evidence_ids": [],
                    "spoken_text": script,
                    "word_count": len(script.split()),
                }
            ]
        }
        production = {
            "sections": [
                {
                    "kind": "cta",
                    "spoken_text": "Si te sirvió, suscríbete y cuéntame qué piensas.",
                }
            ]
        }
        pack = build_recording_pack(
            episode_date="2026-09-24",
            script=script,
            script_sections=sections,
            edit_manifest={},
            production_script=production,
            words_per_second=2.5,
            min_take_seconds=5,
            target_take_seconds=8,
            max_take_seconds=15,
        )
        original = " ".join(
            take["spoken_text"]
            for take in pack["takes"]
            if take["section_kind"] != "cta"
        )
        self.assertEqual(" ".join(original.split()), " ".join(script.split()))
        cta = [take for take in pack["takes"] if take["section_kind"] == "cta"]
        self.assertEqual(len(cta), 1)
        self.assertGreater(pack["summary"]["cta_word_count"], 0)
        self.assertTrue(pack["readiness"]["ready_to_record"])

    def test_edit_manifest_cues_are_attached_to_overlapping_take(self):
        script = "uno dos tres cuatro cinco seis siete ocho nueve diez"
        sections = {
            "sections": [
                {
                    "section_key": "opening",
                    "kind": "opening",
                    "spoken_text": script,
                    "word_count": 10,
                    "evidence_ids": [],
                }
            ]
        }
        edit = {
            "timeline": [
                {
                    "mode": "media",
                    "cue_id": "slot_001",
                    "start_seconds": 0.5,
                    "end_seconds": 2.5,
                    "director": {
                        "visual_role": "evidence",
                        "intent": "Aterrizar el dato",
                        "note": "Mostrar evidencia concreta.",
                    },
                    "media": {
                        "preferred_asset_type": "image",
                        "visual_query": "research document",
                        "on_screen_text": "Dato",
                    },
                }
            ]
        }
        pack = build_recording_pack(
            episode_date="2026-09-24",
            script=script,
            script_sections=sections,
            edit_manifest=edit,
            production_script={},
            words_per_second=2.0,
            min_take_seconds=1,
            target_take_seconds=3,
            max_take_seconds=10,
        )
        cues = [cue for take in pack["takes"] for cue in take["edit_cues"]]
        self.assertEqual(cues[0]["cue_id"], "slot_001")
        self.assertEqual(cues[0]["visual_role"], "evidence")

    def test_stale_script_sections_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "does not match script.txt"):
            build_recording_pack(
                episode_date="2026-09-24",
                script="texto aprobado",
                script_sections={
                    "sections": [
                        {
                            "section_key": "opening",
                            "kind": "opening",
                            "spoken_text": "texto viejo",
                            "word_count": 2,
                        }
                    ]
                },
                edit_manifest={},
                production_script={},
                words_per_second=2.5,
            )

    def test_teleprompter_is_standalone_and_contains_controls(self):
        pack = {
            "episode_date": "2026-09-24",
            "teleprompter_defaults": {
                "font_size_px": 64,
                "line_height": 1.35,
                "scroll_speed_px_per_second": 42,
                "countdown_seconds": 3,
            },
            "takes": [
                {
                    "take_id": "opening_t01",
                    "spoken_slate": "TAKE opening_t01",
                    "spoken_text": "Texto <seguro> & visible.",
                    "section_label": "Apertura",
                    "estimated_duration_seconds": 12,
                    "delivery": {"energy": "high", "pace": "deliberate", "note": "Mirar a lente."},
                    "edit_cues": [],
                }
            ],
        }
        output = render_teleprompter(pack)
        self.assertIn("<!doctype html>", output.lower())
        self.assertNotIn("http://", output.lower())
        self.assertNotIn("https://", output.lower())
        self.assertIn("Pantalla completa", output)
        self.assertIn("Espejo", output)
        self.assertIn("countdown", output)
        self.assertIn("opening_t01", output)

    def test_write_recording_pack_emits_three_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "scripts" / "2026-09-24"
            media = root / "multimedia" / "2026-09-24"
            episode.mkdir(parents=True)
            media.mkdir(parents=True)
            script = "Uno dos tres cuatro cinco seis siete ocho nueve diez."
            (episode / "script.txt").write_text(script, encoding="utf-8")
            (episode / "script_sections.json").write_text(
                json.dumps(
                    {
                        "sections": [
                            {
                                "section_key": "opening",
                                "kind": "opening",
                                "spoken_text": script,
                                "word_count": 10,
                                "evidence_ids": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (episode / "run_state.json").write_text(
                json.dumps({"episode_date": "2026-09-24"}),
                encoding="utf-8",
            )
            paths = write_recording_pack(
                episode_dir=episode,
                media_dir=media,
                words_per_second=2.5,
                min_take_seconds=1,
                target_take_seconds=2,
                max_take_seconds=10,
            )
            for path in paths:
                self.assertTrue(path.exists())
            payload = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["take_count"], 1)


    def test_short_tail_rebalances_when_merge_would_exceed_max(self):
        s1 = " ".join([f"a{i}" for i in range(20)]) + "."
        s2 = " ".join([f"b{i}" for i in range(30)]) + "."
        s3 = " ".join([f"c{i}" for i in range(15)]) + "."
        text = f"{s1} {s2} {s3}"
        takes = split_recording_takes(
            text,
            words_per_second=1.0,
            min_seconds=20,
            target_seconds=35,
            max_seconds=60,
        )
        durations = [len(take.split()) for take in takes]
        self.assertEqual(len(takes), 2)
        self.assertGreaterEqual(min(durations), 20)
        self.assertLessEqual(max(durations), 60)
        self.assertEqual(" ".join(" ".join(takes).split()), " ".join(text.split()))

    def test_existing_cta_is_not_appended_twice(self):
        script = (
            "Esta es la idea final del ensayo. "
            "Si te sirvió, suscríbete y cuéntame qué piensas."
        )
        sections = {
            "sections": [
                {
                    "section_key": "synthesis",
                    "kind": "synthesis",
                    "spoken_text": script,
                    "word_count": len(script.split()),
                    "evidence_ids": [],
                }
            ]
        }
        production = {
            "cta_injected": False,
            "sections": [
                {
                    "kind": "cta",
                    "spoken_text": "Si te sirvió, suscríbete y cuéntame qué piensas.",
                }
            ],
        }
        pack = build_recording_pack(
            episode_date="2026-09-24",
            script=script,
            script_sections=sections,
            edit_manifest={},
            production_script=production,
            words_per_second=2.5,
            min_take_seconds=1,
            target_take_seconds=5,
            max_take_seconds=15,
        )
        narration = " ".join(take["spoken_text"] for take in pack["takes"])
        self.assertEqual(" ".join(narration.split()), " ".join(script.split()))
        self.assertEqual(pack["summary"]["cta_word_count"], 0)

    def test_teleprompter_escapes_script_closing_sequence(self):
        pack = {
            "episode_date": "2026-09-24",
            "teleprompter_defaults": {},
            "takes": [
                {
                    "take_id": "opening_t01",
                    "spoken_slate": "TAKE opening_t01",
                    "spoken_text": "Texto </script><script>alert(1)</script> seguro.",
                    "section_label": "Apertura",
                    "estimated_duration_seconds": 10,
                    "delivery": {"energy": "natural", "pace": "normal", "note": ""},
                    "edit_cues": [],
                }
            ],
        }
        output = render_teleprompter(pack)
        self.assertNotIn("</script><script>alert(1)</script>", output)



if __name__ == "__main__":
    unittest.main()
