from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.staged_narrative_memory_issue import process_event

TZ = ZoneInfo("America/Mexico_City")
NOW = datetime(2026, 9, 28, 10, 0, 0, tzinfo=TZ)


def _item(item_id: str = "new-case") -> dict:
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
        "created_at": "2026-09-28",
        "status": "approved",
    }


def _event(records: list[dict], stamp: str = "2026-09-28 10:00:00") -> dict:
    return {
        "issue": {
            "title": f"NARRATIVE_MEMORY_STAGING — {stamp} America/Mexico_City",
            "body": "\n".join(
                [
                    f"# Narrative Memory Staging — {stamp} America/Mexico_City",
                    *[json.dumps(record, ensure_ascii=False) for record in records],
                ]
            ),
        }
    }


class StagedNarrativeMemoryIssueTests(unittest.TestCase):
    def _paths(self, initial: list[dict] | None = None):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        memory = root / "memory.jsonl"
        memory.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in (initial or [])),
            encoding="utf-8",
        )
        event = root / "event.json"
        return tmp, memory, event

    def test_valid_record_appends_exactly_once(self) -> None:
        tmp, memory, event = self._paths()
        with tmp:
            event.write_text(json.dumps(_event([_item()])), encoding="utf-8")
            status, ids = process_event(event, memory, apply=True, now=NOW)
            self.assertEqual(status, "applied")
            self.assertEqual(ids, ["new-case"])
            lines = memory.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["id"], "new-case")

            status2, ids2 = process_event(event, memory, apply=True, now=NOW)
            self.assertEqual(status2, "already_exists")
            self.assertEqual(ids2, ["new-case"])
            self.assertEqual(len(memory.read_text(encoding="utf-8").splitlines()), 1)

    def test_rejects_gate_failure(self) -> None:
        tmp, memory, event = self._paths()
        with tmp:
            weak = _item()
            weak["surprise_score"] = 3
            event.write_text(json.dumps(_event([weak])), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "surprise_below_gate"):
                process_event(event, memory, apply=False, now=NOW)

    def test_rejects_conflicting_existing_id(self) -> None:
        existing = _item("same-id")
        tmp, memory, event = self._paths([existing])
        with tmp:
            changed = _item("same-id")
            changed["summary"] += " Changed."
            event.write_text(json.dumps(_event([changed])), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "contenido diferente"):
                process_event(event, memory, apply=True, now=NOW)

    def test_rejects_more_than_four_records(self) -> None:
        tmp, memory, event = self._paths()
        with tmp:
            records = [_item(f"case-{i}") for i in range(5)]
            event.write_text(json.dumps(_event(records)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "entre 1 y 4"):
                process_event(event, memory, apply=False, now=NOW)

    def test_rejects_wrong_created_at(self) -> None:
        tmp, memory, event = self._paths()
        with tmp:
            item = _item()
            item["created_at"] = "2026-09-27"
            event.write_text(json.dumps(_event([item])), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "created_at"):
                process_event(event, memory, apply=False, now=NOW)


if __name__ == "__main__":
    unittest.main()
