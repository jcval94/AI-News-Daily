from __future__ import annotations

import math
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Any


@dataclass(frozen=True)
class PipelineConfig:
    openai_model: str = "gpt-5.4-nano"
    words_per_second: float = 2.5
    target_min_seconds: int = 420
    target_max_seconds: int = 1200
    script_quality_threshold: float = 8.7
    judge_threshold: float = 8.5
    voice_threshold: float = 8.7
    max_refinement_iterations: int = 5
    max_selected_news: int = 8
    max_media_downloads: int = 12
    selection_history_days: int = 30
    essay_history_days: int = 120
    max_recent_essays: int = 12
    essay_duplicate_threshold: float = 0.42
    max_novelty_replans: int = 2
    agent_max_attempts: int = 3
    agent_retry_base_seconds: float = 2.0
    first_15_slot_seconds: int = 3
    normal_slot_seconds: int = 4
    news_source_mode: str = "scheduled_window"
    news_lookback_days: int = 4

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        return cls(
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-nano"),
            words_per_second=float(os.getenv("WORDS_PER_SECOND", "2.5")),
            target_min_seconds=int(os.getenv("TARGET_MIN_SECONDS", "420")),
            target_max_seconds=int(os.getenv("TARGET_MAX_SECONDS", "1200")),
            script_quality_threshold=float(os.getenv("SCRIPT_QUALITY_THRESHOLD", "8.7")),
            judge_threshold=float(os.getenv("JUDGE_THRESHOLD", "8.5")),
            voice_threshold=float(os.getenv("VOICE_THRESHOLD", "8.7")),
            max_refinement_iterations=int(os.getenv("MAX_REFINEMENT_ITERATIONS", "5")),
            max_selected_news=int(os.getenv("MAX_SELECTED_NEWS", "8")),
            max_media_downloads=int(os.getenv("MAX_MEDIA_DOWNLOADS", "12")),
            selection_history_days=int(os.getenv("SELECTION_HISTORY_DAYS", "30")),
            essay_history_days=int(os.getenv("ESSAY_HISTORY_DAYS", "120")),
            max_recent_essays=int(os.getenv("MAX_RECENT_ESSAYS", "12")),
            essay_duplicate_threshold=float(os.getenv("ESSAY_DUPLICATE_THRESHOLD", "0.42")),
            max_novelty_replans=int(os.getenv("MAX_NOVELTY_REPLANS", "2")),
            agent_max_attempts=int(os.getenv("AGENT_MAX_ATTEMPTS", "3")),
            agent_retry_base_seconds=float(os.getenv("AGENT_RETRY_BASE_SECONDS", "2.0")),
            news_source_mode=os.getenv("NEWS_SOURCE_MODE", "scheduled_window").strip().lower(),
            news_lookback_days=int(os.getenv("NEWS_LOOKBACK_DAYS", "4")),
        ).validated()

    def validated(self) -> "PipelineConfig":
        if self.words_per_second <= 0:
            raise ValueError("WORDS_PER_SECOND must be > 0")
        if self.target_min_seconds <= 0 or self.target_max_seconds < self.target_min_seconds:
            raise ValueError("TARGET_MIN_SECONDS/TARGET_MAX_SECONDS are invalid")
        if not (0 <= self.script_quality_threshold <= 10):
            raise ValueError("SCRIPT_QUALITY_THRESHOLD must be between 0 and 10")
        if not (0 <= self.judge_threshold <= 10):
            raise ValueError("JUDGE_THRESHOLD must be between 0 and 10")
        if not (0 <= self.voice_threshold <= 10):
            raise ValueError("VOICE_THRESHOLD must be between 0 and 10")
        if self.max_refinement_iterations < 1:
            raise ValueError("MAX_REFINEMENT_ITERATIONS must be >= 1")
        if not (1 <= self.max_selected_news <= 8):
            raise ValueError("MAX_SELECTED_NEWS must be between 1 and 8")
        if self.max_media_downloads < 0:
            raise ValueError("MAX_MEDIA_DOWNLOADS must be >= 0")
        if self.selection_history_days < 1:
            raise ValueError("SELECTION_HISTORY_DAYS must be >= 1")
        if self.essay_history_days < 1:
            raise ValueError("ESSAY_HISTORY_DAYS must be >= 1")
        if self.max_recent_essays < 1:
            raise ValueError("MAX_RECENT_ESSAYS must be >= 1")
        if not (0 < self.essay_duplicate_threshold <= 1):
            raise ValueError("ESSAY_DUPLICATE_THRESHOLD must be > 0 and <= 1")
        if self.max_novelty_replans < 0:
            raise ValueError("MAX_NOVELTY_REPLANS must be >= 0")
        if self.agent_max_attempts < 1:
            raise ValueError("AGENT_MAX_ATTEMPTS must be >= 1")
        if self.agent_retry_base_seconds < 0:
            raise ValueError("AGENT_RETRY_BASE_SECONDS must be >= 0")
        if self.news_source_mode not in {"scheduled_window", "recent_window"}:
            raise ValueError("NEWS_SOURCE_MODE must be scheduled_window or recent_window")
        if not (1 <= self.news_lookback_days <= 14):
            raise ValueError("NEWS_LOOKBACK_DAYS must be between 1 and 14")
        return self

    @property
    def target_min_words(self) -> int:
        return int(self.target_min_seconds * self.words_per_second)

    @property
    def target_max_words(self) -> int:
        return int(self.target_max_seconds * self.words_per_second)

    def as_report_dict(self) -> dict[str, Any]:
        return asdict(self)


APPROVED = "approved"
NO_SOURCE_NEWS = "no_source_news"
NO_RELEVANT_NEWS = "no_relevant_news"
NO_NOVEL_ESSAY_ANGLE = "no_novel_essay_angle"
SCRIPT_NOT_APPROVED = "script_not_approved"
FAILURE = "failure"
MISSING_OPENAI_SECRET = "missing_openai_secret"

PUBLISHABLE_STATUSES = {APPROVED}
NON_FATAL_SKIP_STATUSES = {NO_SOURCE_NEWS, NO_RELEVANT_NEWS, NO_NOVEL_ESSAY_ANGLE}
KNOWN_STATUSES = PUBLISHABLE_STATUSES | NON_FATAL_SKIP_STATUSES | {
    SCRIPT_NOT_APPROVED,
    FAILURE,
    MISSING_OPENAI_SECRET,
}

_TOPIC_STOPWORDS = {
    "a", "al", "algo", "ante", "como", "con", "cuando", "de", "del", "desde", "donde",
    "el", "en", "entre", "es", "esta", "este", "esto", "la", "las", "lo", "los", "mas",
    "nos", "nuestra", "nuestro", "o", "para", "pero", "por", "que", "se", "sin", "sobre",
    "su", "sus", "un", "una", "y", "ya", "the", "of", "to", "and", "in", "is", "are",
    "inteligencia", "artificial", "modelo", "modelos", "tecnologia", "tecnologias",
    "herramienta", "herramientas", "sistema", "sistemas",
}


def _topic_tokens(value: str) -> list[str]:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    return [token for token in tokens if len(token) > 2 and token not in _TOPIC_STOPWORDS]


def normalize_topic_text(value: str) -> str:
    return " ".join(_topic_tokens(value))


def _topic_roots(value: str) -> set[str]:
    """Use short lexical roots to make Spanish inflections less brittle.

    This is intentionally lightweight and deterministic; the LLM Director remains the
    semantic novelty layer, while this guardrail catches obvious/rephrased overlaps.
    """
    return {token[:6] for token in _topic_tokens(value)}


def topic_similarity(left: str, right: str) -> float:
    a = normalize_topic_text(left)
    b = normalize_topic_text(right)
    if not a or not b:
        return 0.0

    a_roots = _topic_roots(left)
    b_roots = _topic_roots(right)
    if not a_roots or not b_roots:
        return 0.0

    intersection = len(a_roots & b_roots)
    union = len(a_roots | b_roots)
    containment = intersection / min(len(a_roots), len(b_roots))
    jaccard = intersection / union if union else 0.0
    sequence = SequenceMatcher(
        None, " ".join(sorted(a_roots)), " ".join(sorted(b_roots))
    ).ratio()
    return round((0.55 * containment) + (0.30 * jaccard) + (0.15 * sequence), 4)


def nearest_essay_similarity(
    candidate: str, previous_essays: list[dict[str, Any]]
) -> dict[str, Any] | None:
    nearest: dict[str, Any] | None = None
    for essay in previous_essays:
        if not isinstance(essay, dict):
            continue
        comparison = " ".join(
            str(essay.get(key, "") or "")
            for key in ("topic_signature", "central_question", "thesis", "narrative_lens")
        ).strip()
        score = topic_similarity(candidate, comparison)
        if nearest is None or score > float(nearest.get("similarity", 0)):
            nearest = {
                "similarity": score,
                "episode_date": essay.get("episode_date"),
                "topic_signature": essay.get("topic_signature"),
                "central_question": essay.get("central_question"),
                "thesis": essay.get("thesis"),
                "narrative_lens": essay.get("narrative_lens"),
            }
    return nearest


def expected_news_dates(target_date: date) -> list[date]:
    """Resolve the deterministic source window for an episode.

    Scheduled production keeps the Tuesday/Friday editorial windows. Manual runs may
    set NEWS_SOURCE_MODE=recent_window to use the target date plus the preceding
    NEWS_LOOKBACK_DAYS-1 calendar days. Missing files remain non-fatal downstream.
    """
    mode = os.getenv("NEWS_SOURCE_MODE", "scheduled_window").strip().lower()
    if mode == "recent_window":
        lookback_days = int(os.getenv("NEWS_LOOKBACK_DAYS", "4"))
        if not (1 <= lookback_days <= 14):
            raise ValueError("NEWS_LOOKBACK_DAYS must be between 1 and 14")
        return [
            target_date - timedelta(days=offset)
            for offset in range(lookback_days - 1, -1, -1)
        ]
    if mode != "scheduled_window":
        raise ValueError("NEWS_SOURCE_MODE must be scheduled_window or recent_window")

    if target_date.weekday() == 1:  # Tuesday -> Friday through Monday
        offsets = (4, 3, 2, 1)
    elif target_date.weekday() == 4:  # Friday -> Tuesday through Thursday
        offsets = (3, 2, 1)
    else:
        raise ValueError(
            f"Scheduled script generation only runs on Tuesday or Friday; got {target_date.isoformat()}"
        )
    return [target_date - timedelta(days=offset) for offset in offsets]


def estimate_spoken_duration_seconds(script: str, config: PipelineConfig) -> int:
    words = max(1, len(script.split()))
    return max(1, math.ceil(words / config.words_per_second))


def timeline_duration_seconds(script: str, config: PipelineConfig) -> int:
    spoken = estimate_spoken_duration_seconds(script, config)
    if spoken <= 15:
        return 15
    return 15 + math.ceil((spoken - 15) / config.normal_slot_seconds) * config.normal_slot_seconds


def duration_within_target(script: str, config: PipelineConfig) -> bool:
    spoken = estimate_spoken_duration_seconds(script, config)
    return config.target_min_seconds <= spoken <= config.target_max_seconds


def build_timeline_slots(duration_seconds: int, config: PipelineConfig) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    cursor = 0
    slot_number = 1
    while cursor < duration_seconds:
        step = config.first_15_slot_seconds if cursor < 15 else config.normal_slot_seconds
        end = min(duration_seconds, cursor + step)
        slots.append(
            {
                "slot_number": slot_number,
                "start_seconds": cursor,
                "end_seconds": end,
                "duration_seconds": end - cursor,
            }
        )
        cursor = end
        slot_number += 1
    return slots


def evaluate_script_gate(
    script: str,
    editorial: dict[str, Any],
    seo: dict[str, Any],
    attention: dict[str, Any],
    voice: dict[str, Any],
    config: PipelineConfig,
) -> dict[str, Any]:
    duration_seconds = estimate_spoken_duration_seconds(script, config) if script else 0
    checks = {
        "script_present": bool(script.strip()),
        "duration_ok": bool(script.strip())
        and config.target_min_seconds <= duration_seconds <= config.target_max_seconds,
        "editorial_approved": bool(editorial.get("approved", False)),
        "editorial_score_ok": float(editorial.get("score", 0) or 0)
        >= config.script_quality_threshold,
        "factuality_low": str(editorial.get("factuality_risk", "")).lower() == "low",
        "seo_approved": bool(seo.get("approved", False)),
        "seo_score_ok": float(seo.get("score", 0) or 0) >= config.judge_threshold,
        "attention_approved": bool(attention.get("approved", False)),
        "attention_score_ok": float(attention.get("score", 0) or 0)
        >= config.judge_threshold,
        "voice_approved": bool(voice.get("approved", False)),
        "voice_score_ok": float(voice.get("score", 0) or 0) >= config.voice_threshold,
        "ai_smell_low": str(voice.get("ai_smell_risk", "")).lower() == "low",
    }
    return {
        "approved": all(checks.values()),
        "duration_seconds": duration_seconds,
        "checks": checks,
    }


def is_retryable_exception(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    if status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True

    name = type(exc).__name__.lower()
    retryable_names = (
        "ratelimit",
        "timeout",
        "apiconnection",
        "serviceunavailable",
        "internalserver",
        "connectionerror",
        "networkerror",
    )
    return any(token in name for token in retryable_names)
