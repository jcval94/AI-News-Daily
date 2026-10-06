from __future__ import annotations

import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from experiments.notebook_story_flow import run
from experiments.notebook_story_flow.contracts import (
    FactualReview, NarrativeReview, PairedReview, ScriptDraft, StoryPlan,
    SECTION_SPECS,
)


def inputs_fixture() -> dict:
    return {"target_date": "2026-10-06", "coverage": {"sufficient": True},
            "news_items": [{"news_id": "news-one", "raw_content": "Original source text"}],
            "memory_candidates": [{"id": "documented-event", "verified_claims": [
                "A documented conflict occurred.", "The documented outcome followed."],
                "sources": ["https://example.org/archive"], "analogy_limits": "Different mechanisms today."}],
            "voice_profile": "Reflective first-person narrator", "discourse_profile": "Earned progression",
            "news_snapshot_sha256": "fixture-hash", "profile_hashes": {}, "control": None,
            "next_video_url": ""}


def plan_fixture() -> StoryPlan:
    return StoryPlan.model_validate({
        "central_question": "What changes when we delegate decisions?",
        "provisional_thesis": "Delegation offers useful help with work.",
        "evolved_thesis": "Responsibility needs explicit limits and ownership.",
        "core_ideas": ["Authority", "Visibility", "Responsibility"], "motif": "An unopened door",
        "pillars": ["Authority", "Visibility", "Responsibility"],
        "epic_candidates": [{"memory_id": "documented-event", "epicity": 8.5, "relevance": 9,
                             "reason": "Documented structural connection to delegation."}],
        "selected_memory_id": "documented-event", "protagonist": "A documented team",
        "opposing_force": "A limited resource", "conflict": "The team must choose which work survives.",
        "setup_claim_indices": [1], "payoff_claim_indices": [2],
        "unresolved_question": "Which task will the team preserve?",
        "bridge_to_present": "This reveals a problem in how we delegate work.",
        "analogy_limits": "This does not prove how present systems behave.",
        "ledger": [{"evidence_id": "e-one", "news_id": "news-one",
                    "supported_facts": ["A provider announced an agent."],
                    "uncertainties": ["Independent outcomes are unknown."]}]})


def draft_fixture() -> ScriptDraft:
    # Synthetic text tests deterministic boundaries, not narrative quality.
    sections = []
    for identifier, _, low, _ in SECTION_SPECS:
        text = " ".join(["palabra"] * (low + 2))
        if identifier == "cierre":
            text += " suscríbete"
        sections.append({"id": identifier, "text": text,
                         "evidence_ids": ["e-one"] if identifier == "idea_A" else [],
                         "memory_claim_indices": [1] if identifier == "step9_epica" else [2] if identifier == "story_payoff" else [],
                         "visual_queries": ["documented archive"]})
    return ScriptDraft.model_validate({"sections": sections, "opening_last_sentence": "palabra " * 2 + "palabra",
                                      "seo_title": "A documented question", "seo_description": "An explanation grounded in evidence.",
                                      "seo_keywords": ["agents", "responsibility", "authority", "decisions"]})


def fact_fixture(**changes) -> FactualReview:
    return FactualReview.model_validate({"approved": True, "risk": "low", "historical_grounding": 9,
                                        **changes})


def narrative_fixture(**changes) -> NarrativeReview:
    return NarrativeReview.model_validate({"editorial_score": 9, "attention_score": 9, "voice_score": 9,
        "seo_score": 9, "ai_smell_risk": "low", "opening_ends_at_peak_tension": True,
        "opening_is_unresolved": True, "premature_resolution": False,
        "payoff_answers_opening": True, "bridge_is_earned": True, "approved": True, **changes})


class FakeBackend:
    def __init__(self, fact_reviews=None, narrative=None, fail_step=None):
        self.fact_reviews = list(fact_reviews or [fact_fixture()])
        self.narrative = narrative or narrative_fixture()
        self.fail_step = fail_step
        self.calls = []

    async def call(self, step, instruction, schema, context, trace):
        self.calls.append((step, copy.deepcopy(context)))
        trace.append({"step": step, "status": "success", "usage": {"total_tokens": 23}})
        if step == self.fail_step:
            raise RuntimeError("fixture provider failure")
        if schema is StoryPlan:
            return plan_fixture()
        if schema is ScriptDraft:
            return draft_fixture()
        if schema is FactualReview:
            return self.fact_reviews.pop(0)
        if schema is NarrativeReview:
            return self.narrative
        return PairedReview(preference="tie", opening_gain="The opening adds curiosity.",
                            delay_cost="The first evidence arrives later.", continuity="The callback restores continuity.",
                            reasoning="The tradeoff deserves human review across several episodes.")


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.inputs, self.plan, self.draft = inputs_fixture(), plan_fixture(), draft_fixture()
        self.memory = run.validate_plan(self.plan, self.inputs)

    def test_valid_structure_and_exact_spoken_duration(self):
        self.assertEqual(run.validate_draft(self.draft, self.plan, self.memory), [])
        with tempfile.TemporaryDirectory() as directory:
            metrics = run.export_draft(Path(directory), self.draft, self.plan)
            self.assertGreater(metrics["opening_seconds"], 140)
            self.assertLess(metrics["first_current_evidence_seconds"], metrics["historical_payoff_seconds"])
            self.assertEqual(run.word_count((Path(directory) / "script.txt").read_text()), metrics["word_count"])
            self.assertNotIn(self.draft.seo_title, (Path(directory) / "script.txt").read_text())

    def test_spoiler_in_bridge_is_rejected(self):
        self.draft.sections[1].memory_claim_indices = [2]
        self.assertTrue(any("disclosed early" in x for x in run.validate_draft(self.draft, self.plan, self.memory)))

    def test_no_invented_memory_or_outcome_indices(self):
        self.plan.payoff_claim_indices = [99]
        with self.assertRaisesRegex(ValueError, "exist and be disjoint"):
            run.validate_plan(self.plan, self.inputs)
        self.plan = plan_fixture()
        self.plan.selected_memory_id = "made-up-history"
        with self.assertRaises(ValueError):
            run.validate_plan(self.plan, self.inputs)

    def test_setup_and_payoff_cannot_overlap(self):
        self.plan.setup_claim_indices = [1, 2]
        with self.assertRaises(ValueError):
            run.validate_plan(self.plan, self.inputs)

    def test_block_order_and_missing_actual_payoff(self):
        self.draft.sections[-2].memory_claim_indices = []
        self.assertTrue(any("payoff omits" in x for x in run.validate_draft(self.draft, self.plan, self.memory)))
        self.draft.sections.reverse()
        self.assertEqual(run.validate_draft(self.draft, self.plan, self.memory), ["section_order_or_identity_invalid"])

    def test_unknown_current_evidence_is_rejected(self):
        self.draft.sections[4].evidence_ids = ["fabricated-evidence"]
        self.assertTrue(any("unknown evidence" in x for x in run.validate_draft(self.draft, self.plan, self.memory)))

    def test_opening_word_budget_is_not_silently_truncated(self):
        self.draft.sections[0].text = " ".join(["palabra"] * 401)
        self.assertTrue(any("401 words outside" in x for x in run.validate_draft(self.draft, self.plan, self.memory)))

    def test_literal_opening_end_and_cta(self):
        self.draft.opening_last_sentence = "An ending that was not written."
        self.draft.sections[-1].text = " ".join(["palabra"] * 70)
        errors = run.validate_draft(self.draft, self.plan, self.memory)
        self.assertTrue(any("literal ending" in x for x in errors))
        self.assertTrue(any("subscription CTA" in x for x in errors))

    def test_comparison_freezes_claim_semantics(self):
        self.inputs["control"] = {"ledger": [row.model_dump() for row in self.plan.ledger],
                                  "plan": {"central_question": self.plan.central_question}}
        self.plan.ledger[0].supported_facts = ["This now falsely proves profitability."]
        with self.assertRaisesRegex(ValueError, "semantics are frozen"):
            run.validate_plan(self.plan, self.inputs)

    def test_judge_approval_is_not_the_gate_authority(self):
        self.assertFalse(run.factual_passes(fact_fixture(risk="high")))
        self.assertFalse(run.factual_passes(fact_fixture(invented_details=["A fictional dialogue"])))
        self.assertFalse(run.narrative_passes(narrative_fixture(voice_score=8.6)))
        self.assertFalse(run.narrative_passes(narrative_fixture(premature_resolution=True)))
        self.assertFalse(run.narrative_passes(narrative_fixture(payoff_answers_opening=False)))

    def test_output_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            run.output_path("2026-10-06", "../../scripts")


class ExecutionTests(unittest.TestCase):
    def execute_fixture(self, backend, inputs=None, dry_run=False):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            report = asyncio.run(run.execute(inputs or inputs_fixture(), out, backend, dry_run=dry_run))
            files = {p.name: p.read_text() for p in out.iterdir() if p.is_file()}
        return report, files

    def test_ready_is_never_publishable_or_approved_history(self):
        backend = FakeBackend()
        report, files = self.execute_fixture(backend)
        self.assertEqual(report["status"], "ready_for_review")
        self.assertFalse(report["publishable"])
        self.assertNotIn("run_state.json", files)
        self.assertEqual([s for s, _ in backend.calls], ["plan", "write", "factual_review", "narrative_review"])

    def test_factual_repair_precedes_style_and_preserves_separation(self):
        backend = FakeBackend(fact_reviews=[fact_fixture(approved=False, risk="medium"), fact_fixture()])
        report, files = self.execute_fixture(backend)
        self.assertEqual(report["status"], "ready_for_review")
        steps = [s for s, _ in backend.calls]
        self.assertLess(steps.index("factual_recheck"), steps.index("narrative_review"))
        contexts = dict(backend.calls)
        self.assertNotIn("voice_profile", contexts["factual_repair"])
        self.assertNotIn("news_items", contexts["narrative_review"])
        self.assertIn("factual_review_initial.json", files)

    def test_failed_factual_recheck_stops_narrative_and_preserves_script(self):
        backend = FakeBackend(fact_reviews=[fact_fixture(risk="high"), fact_fixture(risk="medium")])
        report, files = self.execute_fixture(backend)
        self.assertEqual(report["status"], "rejected_factual")
        self.assertNotIn("narrative_review", [s for s, _ in backend.calls])
        self.assertIn("script.txt", files)

    def test_failure_keeps_partial_usage_and_trace(self):
        report, files = self.execute_fixture(FakeBackend(fail_step="write"))
        self.assertEqual(report["status"], "failure")
        self.assertEqual(report["emitted_usage"]["total_tokens"], 46)
        self.assertEqual(len(json.loads(files["execution_trace.json"])), 2)

    def test_blocked_sources_and_dry_run_use_no_models(self):
        backend = FakeBackend()
        report, _ = self.execute_fixture(backend, {"target_date": "2026-10-06", "blocked": "insufficient_source_coverage"})
        self.assertEqual(report["status"], "blocked_inputs")
        report, _ = self.execute_fixture(backend, dry_run=True)
        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(backend.calls, [])

    def test_missing_secret_is_explicit_and_does_not_import_backend(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            report, files = self.execute_fixture(None)
        self.assertEqual(report["status"], "missing_openai_secret")
        self.assertIn("run_report.json", files)

    def test_output_run_cannot_be_reused_with_stale_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "script.txt").write_text("old approved-looking output")
            with self.assertRaisesRegex(ValueError, "already exists"):
                asyncio.run(run.execute(inputs_fixture(), out, FakeBackend()))


class RepositoryWiringTests(unittest.TestCase):
    def test_next_episode_has_real_sources_and_retrieved_history(self):
        prepared = run.prepare_inputs("2026-10-06", None, "scheduled_window", 4)
        self.assertNotIn("blocked", prepared)
        self.assertEqual(prepared["coverage"]["expected_dates"], ["2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"])
        self.assertGreater(len(prepared["news_items"]), 0)

    def test_real_control_snapshot_matches_its_ledger(self):
        prepared = run.prepare_inputs(None, run.ROOT / "scripts/2026-09-25", "scheduled_window", 4)
        self.assertEqual(prepared["target_date"], "2026-09-25")
        self.assertEqual(len(prepared["control"]["ledger"]), 3)
        self.assertTrue(all(row["raw_content"] for row in prepared["news_items"]))

    def test_no_source_window_blocks_before_models(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run, "ROOT", Path(directory)):
            prepared = run.prepare_inputs("2026-10-06", None, "scheduled_window", 4)
        self.assertEqual(prepared["blocked"], "insufficient_source_coverage")

    def test_exact_production_artifact_is_used_not_latest_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            episode = root / "scripts/2026-10-06"
            episode.mkdir(parents=True)
            (episode / "run_state.json").write_text('{}')
            self.assertEqual(run.resolve_control(episode_dir=None, artifact=root, latest=False), episode)
            (root / "run_state.json").write_text('{}')
            with self.assertRaises(ValueError):
                run.resolve_control(episode_dir=None, artifact=root, latest=False)

    def test_workflow_is_trusted_main_only_and_results_cannot_retrigger(self):
        workflow = yaml.safe_load((run.ROOT / ".github/workflows/notebook-story-flow.yml").read_text())
        triggers = workflow.get("on", workflow.get(True))
        self.assertEqual(triggers["workflow_run"]["workflows"], ["Build AI News Video Kit"])
        self.assertNotIn("schedule", triggers)
        self.assertIn("!experiments/notebook_story_flow/results/**", triggers["push"]["paths"])
        gate = workflow["jobs"]["replicate"]["if"]
        self.assertIn("head_branch == 'main'", gate)
        self.assertIn("head_repository.full_name == github.repository", gate)
        self.assertIn("github.event_name != 'pull_request'", gate)
        download = next(s for s in workflow["jobs"]["replicate"]["steps"] if s.get("name") == "Download the exact production attempt")
        self.assertIn("github.event.workflow_run.id", download["with"]["run-id"])


if __name__ == "__main__":
    unittest.main()
