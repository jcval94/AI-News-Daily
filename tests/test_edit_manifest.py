from pipeline.edit_manifest import build_edit_manifest


def _sections():
    return {
        "schema_version": 2,
        "sections": [
            {
                "section_key": "opening",
                "kind": "opening",
                "beat_id": None,
                "beat_kind": None,
                "evidence_ids": [],
                "spoken_text": "uno dos tres cuatro cinco seis siete ocho nueve diez",
                "word_count": 10,
            },
            {
                "section_key": "beat:evidence",
                "kind": "development",
                "beat_id": "evidence",
                "beat_kind": "evidence",
                "evidence_ids": ["ev1"],
                "spoken_text": "once doce trece catorce quince dieciseis diecisiete dieciocho diecinueve veinte",
                "word_count": 10,
            },
        ],
    }


def test_edit_manifest_builds_presenter_and_media_timeline():
    payload = build_edit_manifest(
        episode_date="2026-09-24",
        script="uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis diecisiete dieciocho diecinueve veinte",
        script_sections=_sections(),
        media_plan={
            "segments": [
                {
                    "slot_number": 7,
                    "mode": "media",
                    "start_seconds": 2.0,
                    "end_seconds": 4.0,
                    "visual_query": "archival research documents",
                    "on_screen_text": "La evidencia",
                    "reason": "Make the evidence concrete",
                    "visual_role": "evidence",
                    "transition_in": "hard_cut",
                    "transition_out": "hard_cut",
                    "treatment": "slow_push_in",
                    "pacing": "normal",
                    "director_note": "Hold long enough to read the document.",
                }
            ]
        },
        media_manifest=[
            {
                "shot_number": 7,
                "file": "B01_evidence/S007.jpg",
                "asset_type": "image",
                "mime_type": "image/jpeg",
                "provider": "wikimedia_commons",
                "license": "CC BY-SA 4.0",
                "license_valid": True,
            }
        ],
        words_per_second=2.0,
    )

    assert payload["schema_version"] == 1
    assert payload["status"] == "pre_recording"
    assert payload["timing"]["requires_recording_retime"] is True
    assert payload["sources"]["script_sha256"]
    assert [item["mode"] for item in payload["timeline"]] == [
        "presenter",
        "media",
        "presenter",
        "presenter",
    ]
    media = next(item for item in payload["timeline"] if item["mode"] == "media")
    assert media["cue_id"] == "slot_007"
    assert media["media"]["file"] == "B01_evidence/S007.jpg"
    assert media["director"]["visual_role"] == "evidence"
    assert media["director"]["note"] == "Hold long enough to read the document."
    assert media["script_anchor"]["excerpt"]


def test_missing_asset_is_visible_not_silently_green():
    payload = build_edit_manifest(
        episode_date="2026-09-24",
        script="uno dos tres cuatro cinco seis siete ocho nueve diez",
        script_sections={
            "sections": [
                {
                    "section_key": "opening",
                    "kind": "opening",
                    "spoken_text": "uno dos tres cuatro cinco seis siete ocho nueve diez",
                    "word_count": 10,
                    "evidence_ids": [],
                }
            ]
        },
        media_plan={
            "segments": [
                {
                    "slot_number": 1,
                    "mode": "media",
                    "start_seconds": 0,
                    "end_seconds": 2,
                    "visual_query": "documentary notes",
                    "reason": "Cold open",
                }
            ]
        },
        media_manifest=[],
        words_per_second=2.0,
    )

    media = payload["timeline"][0]
    assert media["mode"] == "media"
    assert media["media"]["available"] is False
    assert "no downloaded asset" in " ".join(payload["validation_warnings"]).lower()
