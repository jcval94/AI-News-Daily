"""Typed contracts for the isolated multimedia retrieval stress lab."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


EntityType = Literal[
    "person", "event", "place", "organization", "product",
    "franchise_object", "artifact", "concept", "other",
]


class TargetContract(StrictModel):
    surface_mention: str = Field(min_length=1, max_length=240)
    entity_type: EntityType
    ambiguity_policy: Literal["exact", "contextual", "refuse_if_ambiguous"]
    domain_context: list[str] = Field(default_factory=list, max_length=8)
    expected_canonical_terms: list[str] = Field(default_factory=list, max_length=10)
    forbidden_identity_terms: list[str] = Field(default_factory=list, max_length=20)


class RetrievalContract(StrictModel):
    exactness: Literal["exact", "contextual", "analogy"]
    media_types: list[Literal["image", "video"]] = Field(min_length=1)
    period: str = Field(default="", max_length=100)
    geography: str = Field(default="", max_length=160)
    query_term_groups: list[list[str]] = Field(default_factory=list, max_length=8)
    forbidden_terms: list[str] = Field(default_factory=list, max_length=30)


class ExpectedContract(StrictModel):
    planner_action: Literal["search", "refuse"]
    min_queries: int = Field(ge=0, le=5)
    max_queries: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.min_queries > self.max_queries:
            raise ValueError("min_queries cannot exceed max_queries")
        if self.planner_action == "refuse" and (self.min_queries != 0 or self.max_queries != 0):
            raise ValueError("refuse cases must require zero queries")
        if self.planner_action == "search" and self.min_queries < 1:
            raise ValueError("search cases must require at least one query")
        return self


class StressCase(StrictModel):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=3, max_length=80)
    title: str = Field(min_length=3, max_length=180)
    category: str = Field(min_length=3, max_length=80)
    severity: Literal["medium", "high", "critical"]
    narration: str = Field(min_length=8, max_length=2000)
    target: TargetContract
    retrieval: RetrievalContract
    expected: ExpectedContract

    @model_validator(mode="after")
    def validate_grounding(self):
        needle = " ".join(self.target.surface_mention.casefold().split())
        haystack = " ".join(self.narration.casefold().split())
        if needle not in haystack:
            raise ValueError("surface_mention must occur literally in narration")
        return self


class ResolvedEntity(StrictModel):
    canonical_name: str = Field(min_length=1, max_length=240)
    entity_type: EntityType
    identity_anchors: list[str] = Field(min_length=1, max_length=10)
    qualifiers: list[str] = Field(default_factory=list, max_length=10)


class SearchQuery(StrictModel):
    query: str = Field(min_length=2, max_length=240)
    language: str = Field(min_length=2, max_length=12)
    media_type: Literal["image", "video"]
    purpose: Literal[
        "canonical_identity", "localized_alias", "period_specific",
        "geography_specific", "contextual_support",
    ]
    anchors: list[str] = Field(min_length=1, max_length=8)


class PlannerOutput(StrictModel):
    schema_version: Literal[1] = 1
    case_id: str = Field(min_length=1, max_length=80)
    decision: Literal["search", "refuse"]
    surface_mention: str = Field(min_length=1, max_length=240)
    ambiguity_status: Literal["unambiguous", "ambiguous", "unsupported"]
    interpretation: str = Field(min_length=5, max_length=900)
    resolved_entity: ResolvedEntity | None
    queries: list[SearchQuery] = Field(default_factory=list, max_length=5)
    exclusions: list[str] = Field(default_factory=list, max_length=20)
    risk_flags: list[str] = Field(default_factory=list, max_length=20)
    rights_boundary_acknowledged: Literal[True] = True

    @model_validator(mode="after")
    def validate_decision_shape(self):
        if self.decision == "refuse":
            if self.queries or self.resolved_entity is not None:
                raise ValueError("refuse requires no queries and no resolved_entity")
            if self.ambiguity_status == "unambiguous":
                raise ValueError("refuse cannot claim unambiguous identity")
        else:
            if not self.queries or self.resolved_entity is None:
                raise ValueError("search requires queries and a resolved_entity")
            if self.ambiguity_status != "unambiguous":
                raise ValueError("search requires an unambiguous identity")
        return self


class CriticChecks(StrictModel):
    identity_preserved: bool
    qualifiers_preserved: bool
    ambiguity_handled: bool
    no_forbidden_drift: bool
    negation_respected: bool
    exactness_preserved: bool
    queries_searchable: bool


FailureCode = Literal[
    "wrong_entity", "missing_qualifier", "query_drift", "forbidden_term",
    "ambiguity_guess", "unsupported_alias", "literalized_metaphor",
    "negation_violation", "period_loss", "geography_loss",
    "generic_substitution", "unsearchable_query", "other",
]


class CriticOutput(StrictModel):
    schema_version: Literal[1] = 1
    case_id: str = Field(min_length=1, max_length=80)
    verdict: Literal["pass", "fail"]
    checks: CriticChecks
    failure_codes: list[FailureCode] = Field(default_factory=list, max_length=12)
    summary: str = Field(min_length=5, max_length=900)

    @model_validator(mode="after")
    def validate_verdict(self):
        values = list(self.checks.model_dump().values())
        if self.verdict == "pass" and (not all(values) or self.failure_codes):
            raise ValueError("pass requires all checks true and no failure_codes")
        if self.verdict == "fail" and all(values) and not self.failure_codes:
            raise ValueError("fail requires a failed check or failure_code")
        return self


class RunConfig(StrictModel):
    schema_version: Literal[1] = 1
    model: str = Field(min_length=2, max_length=100)
    repetitions: int = Field(ge=1, le=10)
    reasoning_effort: Literal["none", "low", "medium", "high"] = "low"
    timeout_seconds: int = Field(ge=5, le=300, default=90)
    max_output_tokens: int = Field(ge=200, le=8000, default=2500)
    critic_enabled: bool = True


class ProfileThresholds(StrictModel):
    min_overall_pass_rate: float = Field(ge=0, le=1)
    min_case_pass_rate: float = Field(ge=0, le=1)
    require_identity_stability: bool
    max_errors: int = Field(ge=0, le=100)
    hard_fail_checks: list[str]
    hard_fail_critic_codes: list[FailureCode]


class ExperimentProfile(StrictModel):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=3, max_length=80)
    description: str = Field(min_length=5, max_length=500)
    case_ids: list[str] = Field(default_factory=list)
    repetitions: int = Field(ge=1, le=10)
    critic_enabled: bool
    reasoning_effort: Literal["none", "low", "medium", "high"]
    thresholds: ProfileThresholds
