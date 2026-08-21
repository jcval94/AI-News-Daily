from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from pipeline import run as pipeline_run


class OrchestrationE2ETests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_episode_reaches_multimedia_without_external_calls(self) -> None:
        script = " ".join(["noticia"] * 1050)

        async def fake_run_agent(agent, initial_state, prompt, *, step, trace, iteration=None):
            trace.append(
                {
                    "step": step,
                    "agent": getattr(agent, "name", step),
                    "iteration": iteration,
                    "attempt": 1,
                    "status": "success",
                    "elapsed_seconds": 0.0,
                    "usage": {},
                }
            )
            if step == "select_news":
                return {
                    "selected_news": {
                        "items": [
                            {
                                "title": "Noticia importante",
                                "date": "2026-08-20",
                                "source": "Fuente primaria",
                                "url": "https://example.com/story",
                                "summary": "Resumen verificable",
                                "why_it_matters": "Impacto claro",
                                "category": "producto",
                            }
                        ],
                        "discarded_duplicates": [],
                        "selection_notes": [],
                    }
                }
            if step == "write_script":
                return {"draft_script": script}
            if step == "editorial_judge":
                return {
                    "review": {
                        "score": 9.2,
                        "approved": True,
                        "factuality_risk": "low",
                        "strengths": [],
                        "problems": [],
                        "improvements": [],
                    }
                }
            if step == "seo_judge":
                return {
                    "seo_review": {
                        "score": 9.0,
                        "approved": True,
                        "strengths": [],
                        "problems": [],
                        "improvements": [],
                    }
                }
            if step == "attention_judge":
                return {
                    "attention_review": {
                        "score": 9.0,
                        "approved": True,
                        "strengths": [],
                        "problems": [],
                        "improvements": [],
                    }
                }
            if step == "plan_multimedia":
                return {"multimedia_plan": {"segments": []}}
            self.fail(f"Unexpected orchestration step: {step}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "news"
            scripts = root / "scripts"
            media = root / "multimedia"
            history = root / "history"
            news.mkdir()
            history.mkdir()
            (news / "2026-08-20.txt").write_text(
                "Título: Noticia importante\nFuente: Fuente primaria\nEnlace: https://example.com/story\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch.object(
                pipeline_run, "run_agent", side_effect=fake_run_agent
            ):
                result = await pipeline_run.build(
                    target_date=date(2026, 8, 21),
                    news_dir=news,
                    scripts_root=scripts,
                    multimedia_root=media,
                    history_scripts_root=history,
                    max_media_downloads=0,
                    download_multimedia=False,
                )

            self.assertEqual(result, scripts / "2026-08-21")
            state = json.loads((result / "run_state.json").read_text(encoding="utf-8"))
            reviews = json.loads((result / "reviews.json").read_text(encoding="utf-8"))
            trace = json.loads((result / "execution_trace.json").read_text(encoding="utf-8"))
            plan = json.loads((media / "2026-08-21" / "plan.json").read_text(encoding="utf-8"))

            self.assertEqual(state["status"], "approved")
            self.assertTrue(state["approved_for_publication"])
            self.assertTrue(reviews["gate"]["approved"])
            self.assertGreaterEqual(plan["timeline_duration_seconds"], 420)
            self.assertEqual(plan["segments"][0]["start_seconds"], 0)
            self.assertEqual(plan["segments"][0]["end_seconds"], 3)
            self.assertGreaterEqual(len(trace["agent_calls"]), 6)
            self.assertEqual(trace["refinement_iterations"][0]["approved"], True)


if __name__ == "__main__":
    unittest.main()
