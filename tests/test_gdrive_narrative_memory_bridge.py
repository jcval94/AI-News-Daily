from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pipeline.gdrive_narrative_memory_bridge import process_envelope

TZ = ZoneInfo("America/Mexico_City")
NOW = datetime(2026, 10, 1, 19, 0, 0, tzinfo=TZ)
REPO = "jcval94/AI-News-Daily"


def item(item_id: str = "bridge-case") -> dict:
    return {
        "id": item_id,
        "title": f"A verified unusual case {item_id}",
        "one_liner": "A surprising verified case with a transferable systems mechanism.",
        "summary": "A detailed verified summary long enough to provide reusable factual context without inventing causal equivalence.",
        "verified_claims": ["A source-backed fact."],
        "uncertainties": ["The causal interpretation has explicit limits."],
        "sources": ["https://example.org/source"],
        "period": "1960s",
        "location": "Example",
        "domains": ["history", "systems"],
        "mechanisms": ["constraint_overshoot"],
        "useful_for": ["systems scaling beyond constraints"],
        "analogy_mapping": "Use the shared structure of growth outrunning a limiting resource.",
        "analogy_limits": "Do not claim literal or causal equivalence across domains.",
        "surprise_score": 9,
        "explanatory_score": 9,
        "analogy_potential": 9,
        "visual_score": 8,
        "sourceability_score": 8,
        "source_quality_score": 9,
        "confidence": 9,
        "semantic_duplicate_risk": "low",
        "source_kind": "scheduled_research",
        "created_at": "2026-10-01",
        "status": "approved",
    }


def payload() -> str:
    return "\n".join(
        [
            "# Narrative Memory Staging — 2026-10-01 19:00:00 America/Mexico_City",
            json.dumps(item(), ensure_ascii=False),
        ]
    )


def write_envelope(path: Path, text: str) -> None:
    raw = text.encode("utf-8")
    path.write_text(
        "\n".join(
            [
                "format=base64-payload-v1",
                "schema_version=1.0",
                "message_id=ai-news-daily.narrative-memory.2026-10-01.190000",
                f"target_repo={REPO}",
                "target_path=editorial/narrative_memory.jsonl",
                "content_type=text/plain",
                f"sha256={hashlib.sha256(raw).hexdigest()}",
                f"payload_b64={base64.b64encode(raw).decode('ascii')}",
                "",
            ]
        ),
        encoding="utf-8",
    )


class GDriveNarrativeMemoryBridgeTests(unittest.TestCase):
    @patch("pipeline.staged_narrative_memory_issue.datetime")
    def test_valid_envelope_appends(self, mock_datetime) -> None:
        mock_datetime.now.return_value = NOW
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory.jsonl"
            memory.write_text("", encoding="utf-8")
            env = root / "env.txt"
            write_envelope(env, payload())

            status, ids = process_envelope(env, REPO, memory, apply=True)

            self.assertEqual(status, "applied")
            self.assertEqual(ids, ["bridge-case"])
            self.assertEqual(json.loads(memory.read_text(encoding="utf-8"))["id"], "bridge-case")

    @patch("pipeline.staged_narrative_memory_issue.datetime")
    def test_message_timestamp_must_match_payload(self, mock_datetime) -> None:
        mock_datetime.now.return_value = NOW
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory.jsonl"
            memory.write_text("", encoding="utf-8")
            env = root / "env.txt"
            text = payload().replace("19:00:00", "19:01:00")
            write_envelope(env, text)

            with self.assertRaisesRegex(ValueError, "message_id"):
                process_envelope(env, REPO, memory, apply=False)


if __name__ == "__main__":
    unittest.main()
