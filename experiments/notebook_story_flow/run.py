from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, create_model

from experiments.notebook_story_flow import prompts
from experiments.notebook_story_flow.contracts import (
    DevelopmentDraft, EndingDraft, FactualReview, LedgerEntry, NarrativeReview,
    OpeningDraft, PairedReview, ScriptDraft, Section, StoryPlan,
    OPENING_MIN_WORDS, OPENING_MAX_WORDS, SECTION_IDS, SECTION_SPECS,
)
from pipeline.narrative_memory import load_memory, load_usage_history, rank_candidates
from pipeline.news import NewsItem
from pipeline.news_resolution import collect_available_news
from pipeline.production_script import format_time, split_sentences, word_count
from pipeline.source_coverage import evaluate_source_coverage


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results"
NOTEBOOK_SHA256 = "9c9205c2a99e1b99284e0311e2140df8d9ff18715245554484e961fc707aba16"
MAX_LOGICAL_CALLS = 12


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def output_path(target: str, run_id: str) -> Path:
    date.fromisoformat(target)
    if not run_id or len(run_id) > 120 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in run_id):
        raise ValueError("run_id must be a simple alphanumeric identifier")
    path = (RESULTS / target / run_id).resolve()
    if not path.is_relative_to(RESULTS.resolve()):
        raise ValueError("Outputs must remain inside the experiment")
    return path


def resolve_control(*, episode_dir: Path | None, artifact: Path | None, latest: bool) -> Path | None:
    if sum((episode_dir is not None, artifact is not None, latest)) > 1:
        raise ValueError("Choose one control input")
    if artifact is not None:
        states = sorted(artifact.rglob("run_state.json"))
        if len(states) != 1:
            raise ValueError("Production artifact must contain exactly one episode state")
        return states[0].parent
    if latest:
        approved = [p.parent for p in sorted((ROOT / "scripts").glob("*/run_state.json"))
                    if read_json(p).get("status") == "approved"]
        if not approved:
            raise ValueError("No approved control episode available")
        return approved[-1]
    return episode_dir


def control_ledger(plan: dict[str, Any], news: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    evidence = {x["evidence_id"]: x for x in plan.get("evidence", [])}
    rows = plan.get("claim_ledger", [])
    if not rows or len(rows) != len(evidence):
        raise ValueError("Control lacks a complete Claim Ledger")
    seen = set()
    for entry in rows:
        identifier = entry["evidence_id"]
        index = entry["selected_news_index"]
        if identifier in seen or identifier not in evidence or not (1 <= index <= len(news)):
            raise ValueError("Invalid control ledger identity/index")
        if evidence[identifier]["selected_news_index"] != index or not entry.get("supported_facts"):
            raise ValueError("Control ledger disagrees with evidence")
        seen.add(identifier)
        result.append({"evidence_id": identifier, "news_id": news[index - 1]["news_id"],
                       **{k: entry.get(k, []) for k in (
                           "supported_facts", "allowed_interpretations", "hypotheses",
                           "uncertainties", "prohibited_claims", "source_limitations")}})
    if len(result) > 3:
        raise ValueError("This treatment supports at most three control evidences")
    return result


def prepare_inputs(target: str | None, episode_dir: Path | None, source_mode: str, lookback: int) -> dict[str, Any]:
    if source_mode not in {"scheduled_window", "recent_window"} or not 1 <= lookback <= 14:
        raise ValueError("Invalid source window")
    # The shared resolver reads these variables; restore caller state afterwards.
    old = {k: os.environ.get(k) for k in ("NEWS_SOURCE_MODE", "NEWS_LOOKBACK_DAYS")}
    os.environ.update(NEWS_SOURCE_MODE=source_mode, NEWS_LOOKBACK_DAYS=str(lookback))
    try:
        control = None
        coverage: dict[str, Any]
        if episode_dir is not None:
            state = read_json(episode_dir / "run_state.json")
            target = target or state["episode_date"]
            if target != state["episode_date"]:
                raise ValueError("Requested date differs from control episode")
            if state.get("status") not in {"approved", "script_not_approved"}:
                return {"target_date": target, "blocked": "control_has_no_usable_script",
                        "control_status": state.get("status")}
            plan = read_json(episode_dir / "episode_plan.json")
            news = read_json(episode_dir / "selected_news.json")["items"]
            if not news or len(news) > 8:
                raise ValueError("Control must have one to eight selected news items")
            # Validate IDs/locators/body shape through the repository model, preserving raw text.
            news = [NewsItem.model_validate(row).model_dump() for row in news]
            if len({row["news_id"] for row in news}) != len(news):
                raise ValueError("Duplicate control news IDs")
            ledger = control_ledger(plan, news)
            script = (episode_dir / "script.txt").read_text(encoding="utf-8").strip()
            if not script:
                raise ValueError("Control script is empty")
            coverage_files = [p / "source_coverage.json" for p in (episode_dir, *episode_dir.parents[:3])]
            found = next((p for p in coverage_files if p.exists()), None)
            coverage = read_json(found) if found else {"sufficient": state["status"] == "approved",
                                                     "origin": "approved_control_snapshot"}
            if coverage.get("episode_date", target) != target:
                raise ValueError("Coverage date differs from control")
            if not coverage.get("sufficient"):
                return {"target_date": target, "blocked": "insufficient_source_coverage", "coverage": coverage}
            control = {"state": state, "plan": plan, "ledger": ledger, "script": script,
                       "script_sha256": sha256(script), "episode_dir": str(episode_dir)}
        else:
            if target is None:
                raise ValueError("--target-date is required without a control")
            coverage = evaluate_source_coverage(target_date=target, news_dir=ROOT / "news", min_ratio=0.75)
            if not coverage["sufficient"]:
                return {"target_date": target, "blocked": "insufficient_source_coverage", "coverage": coverage}
            _, _, _, parsed = collect_available_news(ROOT / "news", date.fromisoformat(target))
            news = [row.model_dump() for row in parsed]
        target_date = date.fromisoformat(target)
        voice = (ROOT / "editorial/voice_profile.md").read_text(encoding="utf-8")
        discourse = (ROOT / "editorial/discourse_profile.md").read_text(encoding="utf-8")
        if not voice.strip() or not discourse.strip():
            raise ValueError("Editorial profiles must be present")
        memory, issues = load_memory(ROOT / "editorial/narrative_memory.jsonl")
        query = control["plan"]["central_question"] if control else " ".join(row["why_it_matters"] for row in news)
        candidates = rank_candidates(memory, query, load_usage_history(ROOT / "scripts", target_date), target_date, top_k=6)
        # Abstract two-claim parallels do not document a scene/conflict/outcome.
        candidates = [row for row in candidates if len(row["verified_claims"]) >= 3]
        for row in candidates:
            row["claim_catalog"] = [{"index": i, "text": text}
                                    for i, text in enumerate(row["verified_claims"], start=1)]
        if not candidates:
            return {"target_date": target, "blocked": "no_verified_history", "coverage": coverage}
        return {"target_date": target, "coverage": coverage, "news_items": news,
                "memory_candidates": candidates, "memory_warnings": issues, "control": control,
                "voice_profile": voice, "discourse_profile": discourse,
                "news_snapshot_sha256": sha256(json.dumps(news, sort_keys=True, ensure_ascii=False)),
                "profile_hashes": {"voice": sha256(voice), "discourse": sha256(discourse)},
                "next_video_url": ""}
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def validate_plan(plan: StoryPlan, inputs: dict[str, Any]) -> dict[str, Any]:
    memories = {row["id"]: row for row in inputs["memory_candidates"]}
    candidate_ids = [row.memory_id for row in plan.epic_candidates]
    if len(candidate_ids) != len(set(candidate_ids)) or not set(candidate_ids) <= memories.keys():
        raise ValueError("Epic candidates must be unique retrieved memory IDs")
    if plan.selected_memory_id not in candidate_ids:
        raise ValueError("Selected history must be a ranked candidate")
    memory = memories[plan.selected_memory_id]
    setup, payoff = set(plan.setup_claim_indices), set(plan.payoff_claim_indices)
    valid = set(range(1, len(memory["verified_claims"]) + 1))
    if len(setup) != len(plan.setup_claim_indices) or len(payoff) != len(plan.payoff_claim_indices):
        raise ValueError("Historical claim indices must be unique")
    if not setup <= valid or not payoff <= valid or setup & payoff:
        raise ValueError("Setup/payoff claims must exist and be disjoint")
    news_ids = {row["news_id"] for row in inputs["news_items"]}
    ids = [entry.evidence_id for entry in plan.ledger]
    if len(ids) != len(set(ids)) or any(row.news_id not in news_ids for row in plan.ledger):
        raise ValueError("Ledger must reference unique IDs and supplied news only")
    if len({row.news_id for row in plan.ledger}) != len(plan.ledger):
        raise ValueError("Do not duplicate one news item into multiple evidences")
    if inputs.get("control"):
        expected = inputs["control"]["ledger"]
        actual = [row.model_dump() for row in plan.ledger]
        if {row["evidence_id"] for row in actual} != {row["evidence_id"] for row in expected}:
            raise ValueError("Paired treatment must preserve the control evidence set")
        expected_by_id = {row["evidence_id"]: row for row in expected}
        if any(row != expected_by_id[row["evidence_id"]] for row in actual):
            raise ValueError("Control Claim Ledger semantics are frozen")
        if plan.central_question != inputs["control"]["plan"]["central_question"]:
            raise ValueError("Paired treatment must preserve the central question")
    return memory


def bind_control_boundary(plan: StoryPlan, inputs: dict[str, Any]) -> StoryPlan:
    """The approved control owns its question/ledger; never ask an LLM to retype it."""
    control = inputs.get("control")
    if not control:
        return plan
    return plan.model_copy(update={
        "central_question": control["plan"]["central_question"],
        "ledger": [LedgerEntry.model_validate(row) for row in control["ledger"]],
    })


def validate_draft(draft: ScriptDraft, plan: StoryPlan, memory: dict[str, Any]) -> list[str]:
    issues = []
    if tuple(row.id for row in draft.sections) != SECTION_IDS:
        return ["section_order_or_identity_invalid"]
    evidence = {row.evidence_id for row in plan.ledger}
    historical = set(range(1, len(memory["verified_claims"]) + 1))
    for row, (_, _, low, high) in zip(draft.sections, SECTION_SPECS):
        count = word_count(row.text)
        # Preserve the defining epic budget; other notebook block budgets are targets.
        # The original notebook allowed a much longer idea_C. Experiment flexibility
        # must not alter production's duration/quality thresholds.
        if row.id == "step9_epica" and not OPENING_MIN_WORDS <= count <= OPENING_MAX_WORDS:
            issues.append(f"{row.id}: {count} words outside {OPENING_MIN_WORDS}..{OPENING_MAX_WORDS}")
        elif row.id != "step9_epica" and not 10 <= count <= (800 if row.id == "idea_C" else 400):
            issues.append(f"{row.id}: block is empty or disproportionately long")
        if not set(row.evidence_ids) <= evidence or not set(row.memory_claim_indices) <= historical:
            issues.append(f"{row.id}: unknown evidence or memory claim reference")
        if row.id != "story_payoff" and set(row.memory_claim_indices) & set(plan.payoff_claim_indices):
            issues.append(f"{row.id}: reserved historical outcome disclosed early")
        if "<!--" in row.text or "```" in row.text:
            issues.append(f"{row.id}: spoken text contains markup/instructions")
    opening, payoff = draft.sections[0], draft.sections[-2]
    if not opening.text.rstrip().endswith(draft.opening_last_sentence.strip()):
        issues.append("opening_last_sentence is not the literal ending")
    if not set(opening.memory_claim_indices) or not set(opening.memory_claim_indices) <= set(plan.setup_claim_indices):
        issues.append("opening must use setup claims only")
    if not set(plan.payoff_claim_indices) <= set(payoff.memory_claim_indices):
        issues.append("payoff omits the reserved historical outcome")
    used_evidence = {identifier for row in draft.sections for identifier in row.evidence_ids}
    if used_evidence != evidence:
        issues.append("script omits planned current evidence")
    if not any(row.evidence_ids for row in draft.sections[:6]):
        issues.append("first current evidence delayed beyond dato_1 / before second pillar")
    closing = draft.sections[-1].text.casefold()
    if "suscr" not in closing:
        issues.append("closing lacks subscription CTA")
    total = sum(word_count(row.text) for row in draft.sections)
    if not 1050 <= total <= 3000:
        issues.append("duration outside 7..20 minutes at 150 words/minute")
    return issues


def factual_passes(review: FactualReview) -> bool:
    return (review.approved and review.risk == "low" and review.historical_grounding >= 8.7
            and not review.invented_details and not review.source_issues and not review.unsupported_claims)


def narrative_passes(review: NarrativeReview) -> bool:
    return (review.approved and review.editorial_score >= 8.7 and review.voice_score >= 8.7
            and review.attention_score >= 8.5 and review.seo_score >= 8.5
            and review.ai_smell_risk == "low" and review.opening_ends_at_peak_tension
            and review.opening_is_unresolved and not review.premature_resolution
            and review.payoff_answers_opening and review.bridge_is_earned)


class RepoAgentBackend:
    """Reuse ADK configuration, transient retries, schema repair and partial usage."""

    def __init__(self) -> None:
        from pipeline import runtime_hardening
        self.base = runtime_hardening.install()
        if not 1 <= self.base.CONFIG.agent_max_attempts <= 3:
            raise ValueError("Experiment retries must stay between one and three")
        self.calls = 0

    async def call(self, step: str, instruction: str, schema: Any, context: dict[str, Any], trace: list[dict[str, Any]]) -> Any:
        from app.agent import model
        from google.adk.agents import Agent
        from google.genai import types
        if self.calls >= MAX_LOGICAL_CALLS:
            raise RuntimeError("Experiment model-call budget exhausted")
        total = sum(row.get("usage", {}).get("total_tokens", 0) for row in trace)
        if total >= 250_000:
            raise RuntimeError("Experiment emitted-token budget exhausted")
        self.calls += 1
        agent = Agent(name=f"notebook_{step}", model=model(), instruction=instruction,
                      output_schema=scoped_schema(schema, context), output_key="result",
                      generate_content_config=types.GenerateContentConfig(max_output_tokens=10000))
        state = await self.base.run_agent(agent, {"context": json.dumps(context, ensure_ascii=False)},
                                          "Execute this step and return the required structured contract.",
                                          step=step, trace=trace)
        return schema.model_validate(state["result"])


def scoped_schema(schema: Any, context: dict[str, Any]) -> Any:
    """Give the provider enums for references instead of asking it to copy IDs."""
    if schema not in {OpeningDraft, DevelopmentDraft, EndingDraft, ScriptDraft}:
        return schema
    historical = tuple(context.get("allowed_memory_indices") or
                       range(1, len(context["selected_memory"]["verified_claims"]) + 1))
    if schema is OpeningDraft:
        return create_model("ScopedOpening", __base__=OpeningDraft,
                            memory_claim_indices=(list[Literal[historical]], Field(min_length=1)))
    evidence = tuple(context.get("allowed_evidence_ids") or
                     [row["evidence_id"] for row in context["plan"]["ledger"]])
    section = create_model("ScopedSection", __base__=Section,
        evidence_ids=(list[Literal[evidence]], Field(default_factory=list, max_length=3)),
        memory_claim_indices=(list[Literal[historical]], Field(default_factory=list)))
    count = 9 if schema is DevelopmentDraft else 12 if schema is ScriptDraft else 2
    return create_model(f"Scoped{schema.__name__}", __base__=schema,
                        sections=(list[section], Field(min_length=count, max_length=count)))


async def generate_flow(backend: Any, context: dict[str, Any], plan: StoryPlan,
                        memory: dict[str, Any], trace: list[dict[str, Any]], out: Path) -> ScriptDraft:
    setup = [{"index": i, "text": memory["verified_claims"][i - 1]} for i in plan.setup_claim_indices]
    opening_context = {
        "period": memory["period"], "location": memory["location"], "opening_claims": setup,
        "protagonist": plan.protagonist, "opposing_force": plan.opposing_force,
        "conflict": plan.conflict, "unresolved_question": plan.unresolved_question,
        "motif": plan.motif, "voice_profile": context["voice_profile"],
        "allowed_memory_indices": plan.setup_claim_indices,
    }
    opening = await backend.call("opening", prompts.OPENING, OpeningDraft, opening_context, trace)
    write_json(out / "opening_initial.json", opening.model_dump())
    count = word_count(opening.text)
    if not OPENING_MIN_WORDS <= count <= OPENING_MAX_WORDS:
        opening = await backend.call("opening_repair", prompts.OPENING, OpeningDraft,
            {**opening_context, "previous_opening": opening.model_dump(),
             "deterministic_errors": [f"Opening has {count} words; allowed 300–450, target 350–400."]}, trace)
    write_json(out / "opening.json", opening.model_dump())
    if not OPENING_MIN_WORDS <= word_count(opening.text) <= OPENING_MAX_WORDS:
        raise ValueError("Opening word budget failed after bounded repair")
    # Withhold the outcome from both the opener and the middle, not merely its marker.
    middle_context = {k: v for k, v in context.items() if k != "selected_memory"}
    middle_context.update(opening=opening.text, historical_claims=setup,
                          allowed_memory_indices=plan.setup_claim_indices,
                          allowed_evidence_ids=[row.evidence_id for row in plan.ledger])
    write_json(out / "prompt_development.json", {"instruction": prompts.DEVELOPMENT, "context": middle_context})
    development = await backend.call("development", prompts.DEVELOPMENT, DevelopmentDraft, middle_context, trace)
    write_json(out / "development.json", development.model_dump())
    ending_context = {**context, "opening": opening.text, "development": development.model_dump(),
                      "allowed_memory_indices": list(range(1, len(memory["verified_claims"]) + 1)),
                      "allowed_evidence_ids": [row.evidence_id for row in plan.ledger]}
    ending = await backend.call("ending", prompts.ENDING, EndingDraft, ending_context, trace)
    write_json(out / "ending.json", ending.model_dump())
    first = Section(id="step9_epica", text=opening.text, evidence_ids=[],
                    memory_claim_indices=opening.memory_claim_indices, visual_queries=opening.visual_queries)
    return ScriptDraft(sections=[first, *development.sections, *ending.sections],
                       opening_last_sentence=split_sentences(opening.text)[-1],
                       seo_title=ending.seo_title, seo_description=ending.seo_description,
                       seo_keywords=ending.seo_keywords)


def writer_context(inputs: dict[str, Any], plan: StoryPlan, memory: dict[str, Any]) -> dict[str, Any]:
    ids = {row.news_id for row in plan.ledger}
    return {"plan": plan.model_dump(), "selected_memory": memory,
            "news_items": [row for row in inputs["news_items"] if row["news_id"] in ids],
            "voice_profile": inputs["voice_profile"], "discourse_profile": inputs["discourse_profile"],
            "section_specs": [dict(id=i, title=t, min_words=lo, max_words=hi) for i, t, lo, hi in SECTION_SPECS],
            "next_video_url": inputs["next_video_url"]}


def export_draft(out: Path, draft: ScriptDraft, plan: StoryPlan) -> dict[str, Any]:
    spoken = "\n\n".join(row.text.strip() for row in draft.sections) + "\n"
    (out / "script.txt").write_text(spoken, encoding="utf-8")
    write_json(out / "flow.json", {"name": "notebook_epic_hero", "schema_version": 1,
        "steps": [{"id": row.id, "auto": True, "include_in_doc": True, "input_mode": "edit",
                   "needs_media": "text", "template": (
                       f"Escribe {SECTION_SPECS[i][1]}, apuntando a {SECTION_SPECS[i][2]}–{SECTION_SPECS[i][3]} palabras. "
                       "Usa story_plan y fuentes congeladas; conserva el orden y el suspenso hasta story_payoff."),
                   "response": row.text, "evidence_ids": row.evidence_ids,
                   "memory_claim_indices": row.memory_claim_indices}
                  for i, row in enumerate(draft.sections)],
        "seo_snippet": {"title": draft.seo_title, "description": draft.seo_description,
                        "keywords": draft.seo_keywords}})
    rows, fragments, markdown = [], [], [f"# {draft.seo_title}\n", "> EXPERIMENTO · pendiente de revisión humana\n"]
    cursor = 0
    first_current = None
    for section, (_, title, _, _) in zip(draft.sections, SECTION_SPECS):
        count = word_count(section.text)
        seconds = math.ceil(count / 2.5)
        if first_current is None and section.evidence_ids:
            first_current = cursor
        rows.append({**section.model_dump(), "word_count": count, "start_seconds": cursor,
                     "end_seconds": cursor + seconds})
        markdown.extend([f"## {format_time(cursor)} · {title}\n", section.text + "\n"])
        words = list(re.finditer(r"\b[\wáéíóúüñÁÉÍÓÚÜÑ'-]+\b", section.text, flags=re.UNICODE))
        for offset in range(0, seconds, 8):
            start_word = math.floor(offset * 2.5)
            stop_word = math.floor(min(offset + 8, seconds) * 2.5)
            excerpt_start = words[min(start_word, len(words) - 1)].start()
            excerpt_end = words[min(stop_word, len(words)) - 1].end()
            fragments.append({"slot_id": f"{section.id}-{offset // 8 + 1:03d}", "section_id": section.id,
                              "start_seconds": cursor + offset, "end_seconds": cursor + min(offset + 8, seconds),
                              "spoken_excerpt": section.text[excerpt_start:excerpt_end],
                              "queries": section.visual_queries, "downloaded": False,
                              "provenance": "model_proposal_not_verified_asset"})
        cursor += seconds
    (out / "camera_script.md").write_text("\n".join(markdown), encoding="utf-8")
    write_json(out / "script_sections.json", {"sections": rows, "duration_seconds": cursor})
    write_json(out / "media_queries.json", {"clip_seconds": 8, "max_candidates_per_fragment": 3,
        "slots": fragments, "policy": "Planning only; use repository acquisition/licensing/density gates before downloads."})
    return {"script_sha256": sha256(spoken), "word_count": sum(row["word_count"] for row in rows),
            "estimated_duration_seconds": cursor, "opening_seconds": rows[0]["end_seconds"],
            "first_current_evidence_seconds": first_current,
            "historical_payoff_seconds": rows[-2]["start_seconds"], "media_slot_count": len(fragments)}


async def execute(inputs: dict[str, Any], out: Path, backend: Any, *, dry_run: bool = False) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    # A repeated run must never leave stale ready artifacts next to a failed state.
    if any(out.iterdir()):
        raise ValueError("Output run already exists; choose a new run_id")
    trace: list[dict[str, Any]] = []
    report: dict[str, Any] = {"schema_version": 1, "experiment": "notebook_story_flow",
        "episode_date": inputs["target_date"], "publishable": False, "status": "running",
        "notebook_sha256": NOTEBOOK_SHA256, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": os.getenv("OPENAI_MODEL", "gpt-5.4-nano"), "max_logical_calls": MAX_LOGICAL_CALLS,
        "max_attempts_per_call": 3, "words_per_minute": 150,
        "experiment_code_sha": os.getenv("EXPERIMENT_CODE_SHA", "local"),
        "control_workflow_run_id": os.getenv("CONTROL_RUN_ID", ""),
        "control_code_sha": os.getenv("CONTROL_SHA", "")}
    write_json(out / "inputs.json", inputs)
    try:
        if inputs.get("blocked"):
            report.update(status="blocked_inputs", reason=inputs["blocked"])
            return report
        report.update(news_snapshot_sha256=inputs["news_snapshot_sha256"], profile_hashes=inputs["profile_hashes"])
        planning = {k: inputs[k] for k in ("news_items", "memory_candidates", "voice_profile", "discourse_profile")}
        control_plan = (inputs.get("control") or {}).get("plan")
        # Do not let the old opening/memory treatment anchor the experimental story choice.
        planning["control_plan"] = ({k: control_plan[k] for k in ("central_question", "thesis", "evidence")}
                                    if control_plan else None)
        planning["control_ledger"] = (inputs.get("control") or {}).get("ledger")
        write_json(out / "prompt_plan.json", {"instruction": prompts.PLAN, "context": planning,
                                             "section_specs": SECTION_SPECS})
        if dry_run:
            report.update(status="dry_run", reason="Inputs prepared; no model calls or generated script")
            return report
        if backend is None:
            if not os.getenv("OPENAI_API_KEY"):
                report.update(status="missing_openai_secret")
                return report
            backend = RepoAgentBackend()
        plan = await backend.call("plan", prompts.PLAN, StoryPlan, planning, trace)
        plan = bind_control_boundary(plan, inputs)
        try:
            memory = validate_plan(plan, inputs)
        except ValueError as exc:
            write_json(out / "story_plan_initial.json", plan.model_dump())
            plan = await backend.call("plan_repair", prompts.PLAN, StoryPlan,
                {**planning, "previous_plan": plan.model_dump(), "deterministic_error": str(exc)}, trace)
            write_json(out / "story_plan_repaired.json", plan.model_dump())
            plan = bind_control_boundary(plan, inputs)
            memory = validate_plan(plan, inputs)
        write_json(out / "story_plan.json", plan.model_dump())
        context = writer_context(inputs, plan, memory)
        write_json(out / "prompt_writer.json", {"instruction": prompts.WRITE, "context": context})
        draft = await generate_flow(backend, context, plan, memory, trace, out)
        write_json(out / "draft_initial.json", draft.model_dump())
        issues = validate_draft(draft, plan, memory)
        write_json(out / "deterministic_gate_initial.json", {"passed": not issues, "issues": issues})
        if issues:
            # One deterministic structural repair, before quality judgment. No relaxed constraints.
            draft = await backend.call("structure_repair", prompts.WRITE, ScriptDraft,
                {**context, "previous_draft": draft.model_dump(), "deterministic_errors": issues}, trace)
        write_json(out / "draft.json", draft.model_dump())
        report.update(export_draft(out, draft, plan))
        issues = validate_draft(draft, plan, memory)
        write_json(out / "deterministic_gate.json", {"passed": not issues, "issues": issues})
        if issues:
            report.update(status="rejected_structure", reason="; ".join(issues))
            return report
        factual_context = {"news_items": context["news_items"], "plan": plan.model_dump(),
                           "selected_memory": memory, "draft": draft.model_dump()}
        factual = await backend.call("factual_review", prompts.FACT, FactualReview, factual_context, trace)
        write_json(out / "factual_review_initial.json", factual.model_dump())
        if not factual_passes(factual):
            draft = await backend.call("factual_repair", prompts.FACT_REPAIR, ScriptDraft,
                {**factual_context, "review": factual.model_dump(), "section_specs": context["section_specs"]}, trace)
            write_json(out / "draft.json", draft.model_dump())
            report.update(export_draft(out, draft, plan))
            issues = validate_draft(draft, plan, memory)
            write_json(out / "deterministic_gate.json", {"passed": not issues, "issues": issues})
            if issues:
                report.update(status="rejected_structure", reason="; ".join(issues))
                return report
            factual = await backend.call("factual_recheck", prompts.FACT, FactualReview,
                {**factual_context, "draft": draft.model_dump()}, trace)
        write_json(out / "factual_review.json", factual.model_dump())
        if not factual_passes(factual):
            report.update(status="rejected_factual", reason="Factual review did not pass")
            return report
        # Separate context: the style/retention judge cannot rewrite source claims.
        narrative = await backend.call("narrative_review", prompts.NARRATIVE, NarrativeReview,
            {"draft": draft.model_dump(), "plan": plan.model_dump(),
             "voice_profile": inputs["voice_profile"], "discourse_profile": inputs["discourse_profile"]}, trace)
        write_json(out / "narrative_review.json", narrative.model_dump())
        report.update(status="ready_for_review" if narrative_passes(narrative) else "rejected_narrative",
                      scores=narrative.model_dump())
        if inputs.get("control"):
            # Comparative review is advisory; it never promotes or invalidates the control.
            try:
                paired = await backend.call("paired_review", prompts.PAIRED, PairedReview,
                    {"control": inputs["control"]["script"], "experiment": draft.model_dump(),
                     "central_question": plan.central_question, "metrics": report}, trace)
                write_json(out / "paired_review.json", paired.model_dump())
                report["paired_preference"] = paired.preference
            except Exception as exc:
                report["comparison_status"] = f"unavailable:{type(exc).__name__}"
        return report
    except Exception as exc:
        # Do not echo provider payloads/credentials in a public run report.
        report.update(status="failure", error_type=type(exc).__name__)
        if isinstance(exc, ValueError) and type(exc).__module__ == "builtins":
            report["reason"] = str(exc)[:1000]
        return report
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["attempted_calls"] = len(trace)
        report["emitted_usage"] = {key: sum(row.get("usage", {}).get(key, 0) for row in trace)
                                   for key in ("prompt_tokens", "output_tokens", "reasoning_tokens", "total_tokens")}
        write_json(out / "execution_trace.json", trace)
        write_json(out / "run_report.json", report)
        (out / "RESULTS.md").write_text(
            f"# Notebook Story Flow · {inputs['target_date']}\n\n"
            f"Estado: **{report['status']}**. Publicable: **no**.\n\n"
            f"Apertura: {report.get('opening_seconds', '—')} s. Primera evidencia actual: "
            f"{report.get('first_current_evidence_seconds', '—')} s.\n\n"
            f"Duración estimada: {report.get('estimated_duration_seconds', '—')} s; "
            f"preferencia comparativa: {report.get('paired_preference', '—')}.\n\n"
            "Los jueces son proxies de calidad, no métricas reales de retención. "
            "Consultar guion, plan, gates, revisiones y traza junto a este archivo.\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replicate JC's epic/hero notebook inside experiments only")
    parser.add_argument("--target-date")
    parser.add_argument("--episode-dir", type=Path)
    parser.add_argument("--production-artifact", type=Path)
    parser.add_argument("--latest-approved", action="store_true")
    parser.add_argument("--source-mode", choices=("scheduled_window", "recent_window"), default="scheduled_window")
    parser.add_argument("--lookback-days", type=int, default=4)
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("local-%Y%m%dT%H%M%S"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    control = resolve_control(episode_dir=args.episode_dir, artifact=args.production_artifact, latest=args.latest_approved)
    inputs = prepare_inputs(args.target_date, control, args.source_mode, args.lookback_days)
    out = output_path(inputs["target_date"], args.run_id)
    report = asyncio.run(execute(inputs, out, None, dry_run=args.dry_run))
    print(json.dumps({"status": report["status"], "output": str(out)}, ensure_ascii=False))
    if report["status"] in {"failure", "missing_openai_secret"}:
        raise SystemExit(1)
    if report["status"].startswith("rejected"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
