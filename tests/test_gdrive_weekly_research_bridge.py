from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.gdrive_weekly_research_bridge import process_envelope

REPO = "jcval94/AI-News-Daily"


def payload() -> dict:
    return {
        "schema_version": "1.0",
        "digest_date": "2026-10-02",
        "window": {"from": "2026-09-26", "to": "2026-10-02"},
        "topics": ["agents", "evaluation"],
        "weekly_changes": [
            {
                "summary": "Agent evaluation became more operational.",
                "why_it_matters": "Teams can test behaviors closer to production.",
            }
        ],
        "items": [
            {
                "id": "arxiv:2609.12345",
                "title": "A practical agent evaluation paper",
                "type": "paper",
                "selection_basis": "new_publication",
                "published_at": "2026-10-01",
                "updated_at": None,
                "authors": ["Example Author"],
                "organization": None,
                "url": "https://arxiv.org/abs/2609.12345",
                "topics": ["agents", "evaluation"],
                "summary": "A practical study of evaluation methods for production agents.",
                "what_changed": "The work tests longer-running agent behavior.",
                "why_it_matters": "It makes evaluation closer to operational failure modes.",
                "evidence": ["The paper reports a controlled benchmark."],
                "limitations": ["Results are limited to the evaluated tasks."],
                "practical_applications": ["evaluation", "agents"],
                "reading_recommendation": "full_read",
                "priority": "high",
                "source_tier": "primary",
            }
        ],
        "practical_implications": {
            "design": ["Separate planning from irreversible actions."],
            "evaluation": ["Measure recovery, not only task success."],
            "deployment": ["Log tool calls and intervention points."],
        },
    }


def write_envelope(path: Path, value: dict) -> None:
    text = json.dumps(value, ensure_ascii=False)
    raw = text.encode("utf-8")
    path.write_text(
        "\n".join(
            [
                "format=base64-payload-v1",
                "schema_version=1.0",
                "message_id=ai-news-daily.research-weekly.2026-10-02.080000",
                f"target_repo={REPO}",
                "target_path=research/weekly/2026-10-02.json",
                "content_type=application/json",
                f"sha256={hashlib.sha256(raw).hexdigest()}",
                f"payload_b64={base64.b64encode(raw).decode('ascii')}",
                "",
            ]
        ),
        encoding="utf-8",
    )


class GDriveWeeklyResearchBridgeTests(unittest.TestCase):
    def test_valid_payload_writes_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "research"
            research.mkdir()
            schema = Path("research/weekly_digest.schema.json").read_text(encoding="utf-8")
            (research / "weekly_digest.schema.json").write_text(schema, encoding="utf-8")
            env = root / "env.txt"
            write_envelope(env, payload())

            status, json_path, md_path = process_envelope(
                env, REPO, research, apply=True
            )

            self.assertEqual(status, "created")
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertIn("## Cambios de la semana", md_path.read_text(encoding="utf-8"))
            self.assertIn("A practical agent evaluation paper", md_path.read_text(encoding="utf-8"))

    def test_digest_date_must_match_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "research"
            research.mkdir()
            schema = Path("research/weekly_digest.schema.json").read_text(encoding="utf-8")
            (research / "weekly_digest.schema.json").write_text(schema, encoding="utf-8")
            env = root / "env.txt"
            value = payload()
            value["digest_date"] = "2026-10-01"
            write_envelope(env, value)

            with self.assertRaisesRegex(ValueError, "digest_date"):
                process_envelope(env, REPO, research, apply=False)

    def test_existing_id_requires_material_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research = root / "research"
            weekly = research / "weekly"
            weekly.mkdir(parents=True)
            schema = Path("research/weekly_digest.schema.json").read_text(encoding="utf-8")
            (research / "weekly_digest.schema.json").write_text(schema, encoding="utf-8")

            old = payload()
            old["digest_date"] = "2026-09-25"
            old["window"] = {"from": "2026-09-19", "to": "2026-09-25"}
            (weekly / "2026-09-25.json").write_text(
                json.dumps(old, ensure_ascii=False), encoding="utf-8"
            )
            env = root / "env.txt"
            write_envelope(env, payload())

            with self.assertRaisesRegex(ValueError, "material_update"):
                process_envelope(env, REPO, research, apply=False)


if __name__ == "__main__":
    unittest.main()
