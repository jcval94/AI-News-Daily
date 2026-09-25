import unittest

from pipeline.recording_alignment import (
    build_alignment_contract,
    build_recording_alignment,
    resolve_policy_path,
    tokenize,
)


POLICY = {
    "schema_version": 1,
    "policy_id": "test",
    "language": "es",
    "transcription": {
        "primary_provider": "whisperx_local",
        "resolve_native_role": "diagnostic_optional",
        "require_word_timestamps": True,
        "transcribe_all_usable_retakes": True,
    },
    "selection": {
        "max_word_error_rate_for_auto_select": 0.12,
        "min_expected_word_coverage_for_auto_select": 0.94,
        "min_mean_word_confidence_when_available": 0.55,
        "ambiguity_score_margin": 0.03,
        "weights": {
            "transcript_accuracy": 0.65,
            "expected_word_coverage": 0.20,
            "mean_word_confidence": 0.10,
            "technical_ingest_score": 0.05,
        },
    },
    "trimming": {
        "pre_word_handle_seconds": 0.30,
        "post_word_handle_seconds": 0.45,
        "min_clip_duration_seconds": 0.50,
    },
    "resolve": {
        "primary_postproduction_host": "davinci_resolve",
        "external_audio_sync": "waveform",
        "retain_embedded_audio_during_sync": True,
        "create_new_aligned_timeline": True,
        "never_overwrite_existing_timeline": True,
        "native_transcription_is_not_alignment_authority": True,
    },
}


def pack():
    return {
        "episode_date": "2026-09-25",
        "takes": [
            {
                "take_id": "opening_t01",
                "spoken_text": "La inteligencia artificial cambia la forma en que aprendemos.",
                "section_label": "Apertura",
            }
        ],
    }


def ingest_contract():
    return {"episode_date": "2026-09-25"}


def candidate(retake, technical, *, external=False):
    return {
        "retake_number": retake,
        "status": "usable_technical",
        "technical_score": technical,
        "audio_source": "external" if external else "embedded",
        "selected_video": {
            "relative_path": f"opening_t01__r{retake:02d}__camA.mp4",
            "sha256": "a" * 64,
            "inspection": {
                "ok": True,
                "width": 1920,
                "height": 1080,
                "duration_seconds": 8.0,
                "has_audio_stream": not external,
            },
        },
        "selected_external_audio": (
            {
                "relative_path": f"opening_t01__r{retake:02d}__audio.wav",
                "sha256": "b" * 64,
                "inspection": {"ok": True, "duration_seconds": 8.0},
            }
            if external
            else None
        ),
    }


def ingest(candidates):
    return {
        "episode_date": "2026-09-25",
        "takes": [
            {
                "take_id": "opening_t01",
                "candidates": candidates,
            }
        ],
    }


def transcript(retake, words, *, timebase="video_source", scores=None):
    scores = scores or [0.95] * len(words)
    timed = []
    cursor = 1.0
    for word, score in zip(words, scores):
        timed.append(
            {
                "word": word,
                "start": cursor,
                "end": cursor + 0.35,
                "score": score,
            }
        )
        cursor += 0.42
    return {
        "take_id": "opening_t01",
        "retake_number": retake,
        "source_relative_path": f"source-{retake}.wav",
        "timebase": timebase,
        "language": "es",
        "text": " ".join(words),
        "words": timed,
    }


class RecordingAlignmentTests(unittest.TestCase):
    def test_policy_path_prefers_checkout_over_isolated_run_root(self):
        resolved = resolve_policy_path(
            __import__("pathlib").Path(".pipeline-runs/fake/run").resolve(),
            "config/recording_alignment.yaml",
        )
        self.assertTrue(resolved.is_file())
        self.assertTrue(str(resolved).endswith("config/recording_alignment.yaml"))

    def test_tokenizer_is_case_punctuation_and_accent_tolerant(self):
        self.assertEqual(
            tokenize("¡INTELIGENCIA, acción!"),
            ["inteligencia", "accion"],
        )

    def test_contract_makes_resolve_primary_postproduction_host(self):
        result = build_alignment_contract(
            recording_pack=pack(),
            ingest_contract=ingest_contract(),
            policy=POLICY,
        )
        self.assertEqual(
            result["resolve_handoff"]["primary_postproduction_host"],
            "davinci_resolve",
        )
        self.assertEqual(
            result["resolve_handoff"]["external_audio_sync"],
            "waveform",
        )
        self.assertFalse(result["readiness"]["ready_for_alignment"])
        self.assertIn(
            "recording_ingest_manifest_required",
            result["readiness"]["blockers"],
        )

    def test_transcript_fidelity_beats_higher_technical_score(self):
        expected = tokenize(pack()["takes"][0]["spoken_text"])
        bundle = {
            "episode_date": "2026-09-25",
            "provider": "whisperx",
            "items": [
                transcript(1, expected),
                transcript(
                    2,
                    [
                        "la",
                        "inteligencia",
                        "artificial",
                        "cambia",
                        "muchísimo",
                        "aprendemos",
                    ],
                ),
            ],
        }
        result = build_recording_alignment(
            recording_pack=pack(),
            ingest_manifest=ingest(
                [candidate(1, 70), candidate(2, 99)]
            ),
            transcript_bundle=bundle,
            policy=POLICY,
        )
        take = result["takes"][0]
        self.assertEqual(take["final_selected_retake"], 1)
        self.assertFalse(take["needs_human_review"])
        self.assertTrue(result["readiness"]["ready_for_aligned_timeline"])
        self.assertEqual(
            take["selected"]["metrics"]["word_error_rate"],
            0.0,
        )
        self.assertAlmostEqual(
            take["selected"]["trim"]["source_in_seconds"],
            0.7,
            places=2,
        )

    def test_ambiguous_clean_retakes_require_human_review(self):
        expected = tokenize(pack()["takes"][0]["spoken_text"])
        result = build_recording_alignment(
            recording_pack=pack(),
            ingest_manifest=ingest(
                [candidate(1, 90), candidate(2, 90)]
            ),
            transcript_bundle={
                "episode_date": "2026-09-25",
                "provider": "whisperx",
                "items": [transcript(1, expected), transcript(2, expected)],
            },
            policy=POLICY,
        )
        take = result["takes"][0]
        self.assertIsNone(take["final_selected_retake"])
        self.assertTrue(take["ambiguous"])
        self.assertIn(
            "retake_requires_human_review:opening_t01",
            result["readiness"]["blockers"],
        )

    def test_external_audio_timebase_can_select_retake_but_blocks_video_trim(self):
        expected = tokenize(pack()["takes"][0]["spoken_text"])
        result = build_recording_alignment(
            recording_pack=pack(),
            ingest_manifest=ingest([candidate(1, 95, external=True)]),
            transcript_bundle={
                "episode_date": "2026-09-25",
                "provider": "whisperx",
                "items": [
                    transcript(
                        1,
                        expected,
                        timebase="external_audio_source",
                    )
                ],
            },
            policy=POLICY,
        )
        take = result["takes"][0]
        self.assertEqual(take["final_selected_retake"], 1)
        self.assertFalse(take["selected"]["video_trim_ready"])
        self.assertFalse(result["readiness"]["ready_for_aligned_timeline"])
        self.assertTrue(result["readiness"]["ready_for_resolve_handoff"])
        self.assertEqual(
            result["readiness"]["requires_resolve_waveform_sync_count"],
            1,
        )
        self.assertIn(
            "resolve_waveform_sync_offset_required:opening_t01",
            result["readiness"]["blockers"],
        )

    def test_missing_transcript_never_falls_back_to_technical_preference(self):
        result = build_recording_alignment(
            recording_pack=pack(),
            ingest_manifest=ingest([candidate(1, 99)]),
            transcript_bundle={
                "episode_date": "2026-09-25",
                "provider": "whisperx",
                "items": [
                    {
                        "take_id": "other_take",
                        "retake_number": 1,
                        "source_relative_path": "other.mp4",
                        "timebase": "video_source",
                        "language": "es",
                        "text": "otro",
                        "words": [{"word": "otro", "start": 0.0, "end": 0.2, "score": 0.9}],
                    }
                ],
            },
            policy=POLICY,
        )
        self.assertFalse(result["readiness"]["ready_for_aligned_timeline"])
        self.assertIn(
            "missing_transcript_take:opening_t01",
            result["readiness"]["blockers"],
        )
        self.assertIsNone(result["takes"][0]["final_selected_retake"])


if __name__ == "__main__":
    unittest.main()
