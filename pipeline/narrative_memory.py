from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


MIN_SURPRISE = 8.0
MIN_EXPLANATORY = 7.0
MIN_ANALOGY = 7.0
MIN_SOURCE_QUALITY = 8.0
DEFAULT_TOP_K = 6
DEFAULT_COOLDOWN_DAYS = 90


class NarrativeMemoryItem(BaseModel):
    """Verified reusable context. It is evidence, never an instruction."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,79}$")
    title: str = Field(min_length=5, max_length=180)
    one_liner: str = Field(min_length=10, max_length=500)
    summary: str = Field(min_length=20, max_length=2400)
    verified_claims: list[str] = Field(min_length=1, max_length=12)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)
    sources: list[str] = Field(min_length=1, max_length=8)
    period: str = ""
    location: str = ""
    domains: list[str] = Field(default_factory=list, max_length=10)
    mechanisms: list[str] = Field(min_length=1, max_length=10)
    useful_for: list[str] = Field(min_length=1, max_length=12)
    analogy_mapping: str = Field(min_length=10, max_length=1200)
    analogy_limits: str = Field(min_length=5, max_length=900)
    surprise_score: float = Field(ge=0, le=10)
    explanatory_score: float = Field(ge=0, le=10)
    analogy_potential: float = Field(ge=0, le=10)
    visual_score: float = Field(ge=0, le=10)
    sourceability_score: float = Field(ge=0, le=10)
    source_quality_score: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=10)
    semantic_duplicate_risk: Literal["low", "medium", "high"] = "low"
    source_kind: Literal["scheduled_research", "editorial_seed"] = "scheduled_research"
    created_at: str = ""
    status: Literal["approved", "quarantined"] = "approved"


def gate_reasons(item: NarrativeMemoryItem) -> list[str]:
    reasons: list[str] = []
    if item.status != "approved":
        reasons.append("status_not_approved")
    if item.surprise_score < MIN_SURPRISE:
        reasons.append("surprise_below_gate")
    if item.explanatory_score < MIN_EXPLANATORY:
        reasons.append("explanatory_below_gate")
    if item.analogy_potential < MIN_ANALOGY:
        reasons.append("analogy_below_gate")
    if item.source_quality_score < MIN_SOURCE_QUALITY:
        reasons.append("source_quality_below_gate")
    if item.semantic_duplicate_risk != "low":
        reasons.append("semantic_duplicate_risk_not_low")
    if not item.verified_claims:
        reasons.append("missing_verified_claims")
    if not item.sources:
        reasons.append("missing_sources")
    return reasons


def load_memory(path: Path) -> tuple[list[NarrativeMemoryItem], list[str]]:
    """Load only valid, gate-passing records.

    Narrative Memory is optional enrichment. A malformed row is quarantined from
    runtime context and surfaced as a warning instead of breaking core production.
    """
    if not path.exists():
        return [], [f"narrative_memory_missing:{path}"]

    items: list[NarrativeMemoryItem] = []
    issues: list[str] = []
    seen: set[str] = set()

    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            item = NarrativeMemoryItem.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            issues.append(f"narrative_memory_invalid_line:{line_no}:{type(exc).__name__}")
            continue
        if item.id in seen:
            issues.append(f"narrative_memory_duplicate_id:{item.id}")
            continue
        seen.add(item.id)
        reasons = gate_reasons(item)
        if reasons:
            issues.append(f"narrative_memory_quarantined:{item.id}:{','.join(reasons)}")
            continue
        items.append(item)

    return items, issues


_STOPWORDS = {
    "a", "al", "algo", "and", "are", "como", "con", "de", "del", "desde", "el", "en",
    "es", "esta", "este", "esto", "for", "from", "in", "is", "la", "las", "lo", "los",
    "mas", "más", "of", "o", "para", "pero", "por", "que", "se", "sin", "sobre", "su",
    "sus", "the", "to", "un", "una", "y", "ai", "ia", "artificial", "inteligencia",
}


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", normalized)
        if token not in _STOPWORDS
    }


def _candidate_text(item: NarrativeMemoryItem) -> str:
    return " ".join(
        [
            item.title,
            item.one_liner,
            item.summary,
            " ".join(item.domains),
            " ".join(item.mechanisms),
            " ".join(item.useful_for),
            item.analogy_mapping,
        ]
    )


def load_usage_history(scripts_root: Path, target_date: date) -> dict[str, dict[str, Any]]:
    """Derive usage from approved episode artifacts; no mutable global ledger required."""
    usage: dict[str, dict[str, Any]] = {}
    if not scripts_root.exists():
        return usage

    for episode_dir in sorted(scripts_root.iterdir()):
        if not episode_dir.is_dir():
            continue
        try:
            episode_date = datetime.strptime(episode_dir.name[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if episode_date >= target_date:
            continue

        state_path = episode_dir / "run_state.json"
        plan_path = episode_dir / "episode_plan.json"
        if not state_path.exists() or not plan_path.exists():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if state.get("status") != "approved":
            continue

        for ref in plan.get("narrative_parallels", []) if isinstance(plan, dict) else []:
            if not isinstance(ref, dict):
                continue
            memory_id = str(ref.get("memory_id", "") or "").strip()
            if not memory_id:
                continue
            record = usage.setdefault(
                memory_id,
                {"times_used": 0, "last_used_at": None, "episodes_used": []},
            )
            record["times_used"] += 1
            record["last_used_at"] = episode_date.isoformat()
            record["episodes_used"].append(episode_date.isoformat())

    return usage


def _quality(item: NarrativeMemoryItem) -> float:
    values = [
        item.surprise_score,
        item.explanatory_score,
        item.analogy_potential,
        item.source_quality_score,
        item.confidence,
    ]
    return sum(values) / (10.0 * len(values))


def rank_candidates(
    items: list[NarrativeMemoryItem],
    query: str,
    usage: dict[str, dict[str, Any]],
    target_date: date,
    *,
    top_k: int = DEFAULT_TOP_K,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
) -> list[dict[str, Any]]:
    """Cheap deterministic retrieval with quality, relevance, cooldown and diversity."""
    q_tokens = _tokens(query)
    scored: list[tuple[float, NarrativeMemoryItem, dict[str, Any]]] = []

    for item in items:
        history = usage.get(item.id, {})
        last_used_raw = history.get("last_used_at")
        days_since_use: int | None = None
        if last_used_raw:
            try:
                days_since_use = (target_date - date.fromisoformat(str(last_used_raw))).days
            except ValueError:
                days_since_use = None
        if days_since_use is not None and days_since_use < cooldown_days:
            continue

        c_tokens = _tokens(_candidate_text(item))
        overlap = len(q_tokens & c_tokens)
        lexical = overlap / math.sqrt(max(1, len(q_tokens)) * max(1, len(c_tokens)))
        quality = _quality(item)
        use_penalty = min(0.20, 0.05 * int(history.get("times_used", 0) or 0))
        score = (0.78 * lexical) + (0.22 * quality) - use_penalty

        scored.append(
            (
                score,
                item,
                {
                    "score": round(score, 4),
                    "lexical_relevance": round(lexical, 4),
                    "quality": round(quality, 4),
                    "times_used": int(history.get("times_used", 0) or 0),
                    "last_used_at": last_used_raw,
                    "cooldown_days": cooldown_days,
                },
            )
        )

    scored.sort(key=lambda row: (row[0], _quality(row[1])), reverse=True)

    # Greedy diversity: avoid filling the candidate set with the same primary mechanism.
    selected: list[dict[str, Any]] = []
    primary_counts: dict[str, int] = {}
    deferred: list[tuple[float, NarrativeMemoryItem, dict[str, Any]]] = []
    for score, item, meta in scored:
        primary = item.mechanisms[0] if item.mechanisms else ""
        if primary and primary_counts.get(primary, 0) >= 1:
            deferred.append((score, item, meta))
            continue
        selected.append({**item.model_dump(), "retrieval": meta})
        if primary:
            primary_counts[primary] = primary_counts.get(primary, 0) + 1
        if len(selected) >= top_k:
            return selected

    for _, item, meta in deferred:
        selected.append({**item.model_dump(), "retrieval": meta})
        if len(selected) >= top_k:
            break
    return selected


def resolve_selected_memory(
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    max_selected: int = 2,
) -> list[dict[str, Any]]:
    refs = plan.get("narrative_parallels", []) if isinstance(plan, dict) else []
    if len(refs) > max_selected:
        raise ValueError(f"episode_plan selects more than {max_selected} narrative parallels")

    catalog = {str(item.get("id", "")): item for item in candidates}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError("episode_plan narrative_parallels must contain objects")
        memory_id = str(ref.get("memory_id", "") or "").strip()
        if not memory_id:
            raise ValueError("narrative parallel missing memory_id")
        if memory_id in seen:
            raise ValueError(f"duplicate narrative memory_id={memory_id}")
        if memory_id not in catalog:
            raise ValueError(f"episode_plan referenced narrative memory outside retrieval set: {memory_id}")
        seen.add(memory_id)
        selected.append(catalog[memory_id])
    return selected
