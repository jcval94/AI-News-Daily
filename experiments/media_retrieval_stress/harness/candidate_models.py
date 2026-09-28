"""Typed contracts for adversarial candidate selection."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Candidate(StrictModel):
    schema_version: Literal[1] = 1
    provider: str = Field(min_length=1, max_length=80)
    provider_asset_id: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=2000)
    title: str = Field(max_length=1000)
    description: str = Field(max_length=5000)
    media_type: Literal["image", "video"]
    rights_status: Literal["unknown", "eligible", "ineligible", "review_required"]
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_seconds: float | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidatePolicy(StrictModel):
    exactness: Literal["exact", "contextual"]
    required_identity_terms: list[str]
    forbidden_terms: list[str]
    period: str = ""
    geography: str = ""
    allow_lowres_exact: bool
    allow_contextual_fallback: bool
    prefer_highest_quality_same_identity: bool


class CandidateExpected(StrictModel):
    selected_provider_asset_ids: list[str]
    must_reject_provider_asset_ids: list[str]
    unresolved: bool
    required_warnings: list[
        Literal[
            "low_resolution", "clip_offset_required", "rights_blocked",
            "frame_level_review", "metadata_visual_mismatch", "duplicate_collapsed",
        ]
    ] = Field(default_factory=list)


class CandidateCase(StrictModel):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=3, max_length=80)
    title: str = Field(min_length=3, max_length=180)
    severity: Literal["medium", "high", "critical"]
    narration: str = Field(min_length=8, max_length=2000)
    semantic_case_id: str = Field(default="", max_length=80)
    policy: CandidatePolicy
    candidates: list[Candidate] = Field(min_length=2, max_length=20)
    expected: CandidateExpected

    @model_validator(mode="after")
    def validate_candidate_ids(self):
        ids = [candidate.provider_asset_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate provider_asset_id values must be unique")
        known = set(ids)
        if not set(self.expected.selected_provider_asset_ids).issubset(known):
            raise ValueError("expected selected ids must exist in candidate set")
        if not set(self.expected.must_reject_provider_asset_ids).issubset(known):
            raise ValueError("expected rejected ids must exist in candidate set")
        return self


CandidateFailureCode = Literal[
    "wrong_entity", "wrong_period", "wrong_geography", "generic_substitute",
    "metadata_only", "metadata_visual_mismatch", "preview_miss",
    "duplicate_lower_quality", "rights_ineligible", "low_resolution",
    "prompt_injection_metadata", "historical_anachronism", "other",
]


class CandidateAssessment(StrictModel):
    provider_asset_id: str = Field(min_length=1, max_length=300)
    verdict: Literal["direct", "contextual", "reject"]
    identity_match: bool
    period_match: Literal["match", "mismatch", "not_applicable", "unknown"]
    geography_match: Literal["match", "mismatch", "not_applicable", "unknown"]
    visual_utility: Literal["high", "usable", "low", "none", "unknown"]
    quality_status: Literal["high", "usable", "low", "unknown"]
    rights_eligible: bool
    failure_codes: list[CandidateFailureCode] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list, max_length=8)


class CandidateSelectionOutput(StrictModel):
    schema_version: Literal[1] = 1
    case_id: str = Field(min_length=3, max_length=80)
    assessments: list[CandidateAssessment] = Field(min_length=2, max_length=20)
    selected_provider_asset_ids: list[str] = Field(default_factory=list, max_length=10)
    unresolved: bool
    warnings: list[
        Literal[
            "low_resolution", "clip_offset_required", "rights_blocked",
            "frame_level_review", "metadata_visual_mismatch", "duplicate_collapsed",
        ]
    ] = Field(default_factory=list)
    selection_reason: str = Field(min_length=5, max_length=1200)

    @model_validator(mode="after")
    def validate_assessment_ids(self):
        ids = [item.provider_asset_id for item in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("each candidate may be assessed only once")
        if not set(self.selected_provider_asset_ids).issubset(set(ids)):
            raise ValueError("selected ids must have assessments")
        if self.unresolved and self.selected_provider_asset_ids:
            raise ValueError("unresolved selection cannot contain selected ids")
        if not self.unresolved and not self.selected_provider_asset_ids:
            raise ValueError("resolved selection requires at least one selected id")
        return self
