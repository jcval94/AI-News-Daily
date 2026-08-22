from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PLASTIC_PATTERNS = (
    "en un mundo cada vez más",
    "esto cambiará las reglas del juego",
    "esto promete revolucionar",
    "pero eso no es todo",
    "cambio de paradigma",
    "las posibilidades son infinitas",
    "solo el tiempo lo dirá",
)
NEWS_SECTION_RE = re.compile(r"(?mi)^\s*(?:#{1,4}\s*)?(?:evidencia|historia|noticia)\s+\d+\b")
NEWS_LED_OPENING_RE = re.compile(
    r"(?i)^(?:hoy salió una noticia|esta semana .{0,60} anunció|[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÜÑ.-]+ (?:presentó|anunció|lanzó))"
)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def evaluate_episode(episode_dir: Path) -> dict[str, Any]:
    script = (episode_dir / "script.txt").read_text(encoding="utf-8").strip() if (episode_dir / "script.txt").exists() else ""
    plan = _read_json(episode_dir / "episode_plan.json", {})
    sections = _read_json(episode_dir / "script_sections.json", {})
    reviews = _read_json(episode_dir / "reviews.json", {})
    state = _read_json(episode_dir / "run_state.json", {})
    beats = plan.get("beats", []) if isinstance(plan, dict) else []
    evidence = plan.get("evidence", []) if isinstance(plan, dict) else []
    section_items = sections.get("sections", []) if isinstance(sections, dict) else []
    expected_keys = ["opening"] + [f"beat:{beat.get('beat_id')}" for beat in beats if isinstance(beat, dict)] + ["synthesis"]
    actual_keys = [str(item.get("section_key", "")) for item in section_items if isinstance(item, dict)]
    opening = str(section_items[0].get("spoken_text", "") if section_items else "").strip()
    lowered = script.lower()

    structural_checks = {
        "has_episode_plan": bool(plan),
        "uses_idea_led_beats": bool(beats) and "stories" not in plan,
        "has_evidence_catalog": bool(evidence),
        "section_keys_match_beats": bool(section_items) and actual_keys == expected_keys,
        "no_news_numbered_headings": not bool(NEWS_SECTION_RE.search(script)),
        "opening_not_news_desk": not bool(NEWS_LED_OPENING_RE.search(opening)),
        "no_plastic_ai_phrases": not any(pattern in lowered for pattern in PLASTIC_PATTERNS),
    }
    voice = reviews.get("voice_humanity", {}) if isinstance(reviews, dict) else {}
    editorial = reviews.get("editorial", {}) if isinstance(reviews, dict) else {}
    return {
        "episode_dir": str(episode_dir),
        "status": state.get("status"),
        "structural_pass": all(structural_checks.values()),
        "structural_checks": structural_checks,
        "word_count": len(script.split()),
        "beat_count": len(beats),
        "evidence_count": len(evidence),
        "best_candidate": reviews.get("best_candidate", {}) if isinstance(reviews, dict) else {},
        "editorial_score": editorial.get("score"),
        "voice_score": voice.get("score"),
        "voice_dimensions": {
            name: voice.get(name)
            for name in ("voice_fidelity", "intellectual_depth", "human_relevance", "analogy_quality")
        },
        "ai_smell_risk": voice.get("ai_smell_risk"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate current-runtime editorial regression artifacts")
    parser.add_argument("--episode-dir", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = evaluate_episode(Path(args.episode_dir))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if result["structural_pass"] else 1)


if __name__ == "__main__":
    main()
