from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipeline.production_script import word_count


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EpicCandidate(Contract):
    memory_id: str
    epicity: float = Field(ge=0, le=10)
    relevance: float = Field(ge=0, le=10)
    reason: str = Field(min_length=15)


class LedgerEntry(Contract):
    evidence_id: str
    news_id: str
    supported_facts: list[str] = Field(min_length=1, max_length=12)
    allowed_interpretations: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    source_limitations: list[str] = Field(default_factory=list)


class StoryPlan(Contract):
    central_question: str = Field(min_length=15)
    provisional_thesis: str = Field(min_length=15)
    evolved_thesis: str = Field(min_length=15)
    core_ideas: list[str] = Field(min_length=3, max_length=3)
    motif: str = Field(min_length=3)
    pillars: list[str] = Field(min_length=3, max_length=3)
    epic_candidates: list[EpicCandidate] = Field(min_length=1, max_length=6)
    selected_memory_id: str
    protagonist: str = Field(min_length=3)
    opposing_force: str = Field(min_length=3)
    conflict: str = Field(min_length=15)
    setup_claim_indices: list[Annotated[int, Field(ge=1)]] = Field(min_length=1)
    payoff_claim_indices: list[Annotated[int, Field(ge=1)]] = Field(min_length=1)
    unresolved_question: str = Field(min_length=15)
    bridge_to_present: str = Field(min_length=15)
    analogy_limits: str = Field(min_length=15)
    ledger: list[LedgerEntry] = Field(min_length=1, max_length=3)


# Visible internal blocks, continuous spoken prose. SEO is metadata, never narration.
SECTION_SPECS = (
    ("step9_epica", "Historia · conflicto abierto", 350, 400),
    ("step10_reconexion", "Puente hacia el presente", 45, 80),
    ("hook_problema", "El problema humano", 45, 80),
    ("hook_cita", "Reflexión / cita documentada", 25, 60),
    ("idea_A", "Primer pilar", 150, 240),
    ("dato_1", "Primer dato y su límite", 25, 55),
    ("idea_B_explica", "Segundo pilar", 150, 240),
    ("idea_B_desafio", "Microexperimento", 25, 60),
    ("dato_2", "Segundo dato y su límite", 25, 55),
    ("idea_C", "Tercer pilar · transformación", 220, 380),
    ("story_payoff", "Regreso y desenlace de la historia", 90, 160),
    ("cierre", "Síntesis, pregunta y CTA", 55, 100),
)
SECTION_IDS = tuple(spec[0] for spec in SECTION_SPECS)
OPENING_MIN_WORDS = 300
OPENING_MAX_WORDS = 450


class Section(Contract):
    id: Literal["step9_epica", "step10_reconexion", "hook_problema", "hook_cita",
                "idea_A", "dato_1", "idea_B_explica", "idea_B_desafio", "dato_2",
                "idea_C", "story_payoff", "cierre"]
    text: str = Field(min_length=30)
    evidence_ids: list[str] = Field(default_factory=list, max_length=3)
    memory_claim_indices: list[int] = Field(default_factory=list, max_length=12)
    visual_queries: list[str] = Field(min_length=1, max_length=3)


class ScriptDraft(Contract):
    sections: list[Section] = Field(min_length=12, max_length=12)
    opening_last_sentence: str = Field(min_length=15)
    seo_title: str = Field(min_length=5, max_length=60)
    seo_description: str = Field(min_length=15, max_length=160)
    seo_keywords: list[str] = Field(min_length=4, max_length=4)


class OpeningDraft(Contract):
    text: str = Field(min_length=100)
    memory_claim_indices: list[Annotated[int, Field(ge=1)]] = Field(min_length=1)
    visual_queries: list[str] = Field(min_length=1, max_length=3)

    @field_validator("text")
    @classmethod
    def validate_word_budget(cls, value: str) -> str:
        count = word_count(value)
        if not OPENING_MIN_WORDS <= count <= OPENING_MAX_WORDS:
            raise ValueError(f"Opening contains {count} spoken words; allowed 300–450, target 350–400")
        return value


class DevelopmentDraft(Contract):
    sections: list[Section] = Field(min_length=9, max_length=9)


class EndingDraft(Contract):
    sections: list[Section] = Field(min_length=2, max_length=2)
    seo_title: str = Field(min_length=5, max_length=60)
    seo_description: str = Field(min_length=15, max_length=160)
    seo_keywords: list[str] = Field(min_length=4, max_length=4)


class FactualReview(Contract):
    approved: bool
    risk: Literal["low", "medium", "high"]
    historical_grounding: float = Field(ge=0, le=10)
    invented_details: list[str] = Field(default_factory=list)
    source_issues: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    repair_instructions: list[str] = Field(default_factory=list)


class NarrativeReview(Contract):
    editorial_score: float = Field(ge=0, le=10)
    attention_score: float = Field(ge=0, le=10)
    voice_score: float = Field(ge=0, le=10)
    seo_score: float = Field(ge=0, le=10)
    ai_smell_risk: Literal["low", "medium", "high"]
    opening_ends_at_peak_tension: bool
    opening_is_unresolved: bool
    premature_resolution: bool
    payoff_answers_opening: bool
    bridge_is_earned: bool
    approved: bool
    strengths: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)


class PairedReview(Contract):
    preference: Literal["experiment", "control", "tie"]
    opening_gain: str = Field(min_length=15)
    delay_cost: str = Field(min_length=15)
    continuity: str = Field(min_length=15)
    reasoning: str = Field(min_length=30)
