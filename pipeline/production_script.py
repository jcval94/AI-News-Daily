from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from pipeline.core import PipelineConfig

CONFIG = PipelineConfig.from_env()

CTA_MARKERS = (
    "suscrib",
    "suscríb",
    "subscribe",
    "comentarios",
    "comenta",
    "te leo",
    "sígueme",
    "sigueme",
    "compártelo",
    "compartelo",
)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\wáéíóúüñÁÉÍÓÚÜÑ'-]+\b", text, flags=re.UNICODE))


def estimate_seconds(text: str, words_per_second: float) -> int:
    words = word_count(text)
    return 0 if words <= 0 else max(1, math.ceil(words / words_per_second))


def format_time(seconds: int | float) -> str:
    value = max(0, int(round(seconds)))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return []
    chunks = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ¿¡0-9])", normalized)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def extract_or_build_cta(script: str, closing_question: str) -> tuple[str, str, bool]:
    """Separate a closing CTA or provide a channel-safe default.

    Only the final three sentence units are candidates. A marker must appear in the
    candidate sentence itself; a later CTA cannot pull an earlier reflective sentence
    into the CTA block.
    """
    units = split_sentences(script)
    if not units:
        return "", "", False

    start_floor = max(0, len(units) - 3)
    for index in range(start_floor, len(units)):
        lowered_sentence = units[index].lower()
        if any(marker in lowered_sentence for marker in CTA_MARKERS):
            body = " ".join(units[:index]).strip()
            tail = " ".join(units[index:]).strip()
            return body, tail, False

    configured = os.getenv("PRODUCTION_CTA_TEXT", "").strip()
    if configured:
        return script.strip(), configured, True

    if closing_question.strip():
        cta = (
            "Si este ensayo te sirvió para pensar la IA más allá del titular, suscríbete y "
            "cuéntame en los comentarios cómo responderías la pregunta con la que cerramos. "
            "Te leo y nos vemos en el siguiente."
        )
    else:
        cta = (
            "Si este ensayo te sirvió para pensar la IA más allá del titular, suscríbete y "
            "cuéntame en los comentarios qué parte te dejó pensando. Nos vemos en el siguiente."
        )
    return script.strip(), cta, True


def _clean_heading(value: str, fallback: str, limit: int = 78) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" .:-")
    if not text:
        return fallback
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_section_specs(
    episode_plan: dict[str, Any],
    selected_news: dict[str, Any],
    body_duration_seconds: int,
) -> list[dict[str, Any]]:
    body_minutes = max(body_duration_seconds / 60.0, 0.1)
    beats = episode_plan.get("beats", []) if isinstance(episode_plan, dict) else []
    beats = [beat for beat in beats if isinstance(beat, dict)]
    evidence_catalog = episode_plan.get("evidence", []) if isinstance(episode_plan, dict) else []
    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in evidence_catalog
        if isinstance(item, dict) and str(item.get("evidence_id", "")).strip()
    }
    selected_items = selected_news.get("items", []) if isinstance(selected_news, dict) else []

    opening_minutes = max(0.75, body_minutes * 0.12)
    synthesis_minutes = max(0.60, body_minutes * 0.10)
    if opening_minutes + synthesis_minutes > body_minutes * 0.45:
        opening_minutes = body_minutes * 0.25
        synthesis_minutes = body_minutes * 0.20
    remaining_minutes = max(0.1, body_minutes - opening_minutes - synthesis_minutes)
    beat_weights = [max(0.1, float(beat.get("estimated_minutes", 1.0) or 1.0)) for beat in beats]
    total_beat_weight = sum(beat_weights) or 1.0

    specs: list[dict[str, Any]] = [{
        "section_key": "opening",
        "kind": "opening",
        "title": "Apertura — tensión humana y pregunta central",
        "purpose": str(episode_plan.get("hook", "") or "Plantear la tensión central del ensayo."),
        "target_seconds": round(opening_minutes * 60),
        "argument_role": "hook",
        "source_evidence": "",
        "evidence_ids": [],
        "historical_mirror": str(episode_plan.get("historical_mirror", "") or ""),
    }]

    for index, beat in enumerate(beats):
        beat_id = str(beat.get("beat_id", "") or f"beat-{index + 1}")
        evidence_ids = [str(value) for value in beat.get("evidence_ids", [])]
        selected_indices: list[int] = []
        titles: list[str] = []
        for evidence_id in evidence_ids:
            evidence = evidence_by_id.get(evidence_id, {})
            try:
                selected_index = int(evidence.get("selected_news_index", 0) or 0)
            except (TypeError, ValueError):
                continue
            selected_indices.append(selected_index)
            if 1 <= selected_index <= len(selected_items):
                item = selected_items[selected_index - 1]
                if isinstance(item, dict):
                    title = str(item.get("title", "") or "").strip()
                    if title:
                        titles.append(title)
        minutes = remaining_minutes * beat_weights[index] / total_beat_weight
        purpose = str(beat.get("purpose", "") or "Desarrollar el argumento.")
        specs.append({
            "section_key": f"beat:{beat_id}",
            "beat_id": beat_id,
            "beat_kind": str(beat.get("kind", "") or "development"),
            "kind": "development",
            "title": _clean_heading(purpose, f"Desarrollo {index + 1}"),
            "purpose": purpose,
            "target_seconds": round(minutes * 60),
            "argument_role": str(beat.get("kind", "") or "development"),
            "source_evidence": "; ".join(titles),
            "evidence_ids": evidence_ids,
            "selected_news_indices": selected_indices,
        })

    specs.append({
        "section_key": "synthesis",
        "kind": "synthesis",
        "title": "Síntesis — qué cambia después de mirar la evidencia",
        "purpose": str(episode_plan.get("final_synthesis", "") or "Cerrar el argumento sin fingir más certeza de la que existe."),
        "target_seconds": round(synthesis_minutes * 60),
        "argument_role": "synthesis",
        "source_evidence": "",
        "evidence_ids": [],
        "closing_question": str(episode_plan.get("closing_question", "") or ""),
    })
    return specs


def allocate_narration(
    body_text: str,
    specs: list[dict[str, Any]],
    words_per_second: float,
) -> list[dict[str, Any]]:
    units = split_sentences(body_text)
    if not specs:
        return []

    total_words = sum(word_count(unit) for unit in units)
    target_total = sum(max(1, int(spec.get("target_seconds", 1))) for spec in specs)
    targets = [
        max(1, round(total_words * max(1, int(spec.get("target_seconds", 1))) / target_total))
        if total_words
        else 0
        for spec in specs
    ]

    sections: list[dict[str, Any]] = []
    cursor = 0
    cumulative_words = 0
    for section_index, spec in enumerate(specs):
        chosen: list[str] = []
        if units and cursor < len(units):
            if section_index == len(specs) - 1:
                chosen = units[cursor:]
                cursor = len(units)
            else:
                chosen_words = 0
                target_words = targets[section_index]
                remaining_sections = len(specs) - section_index - 1
                while cursor < len(units):
                    units_left_after = len(units) - (cursor + 1)
                    if chosen and units_left_after < remaining_sections:
                        break
                    unit = units[cursor]
                    chosen.append(unit)
                    chosen_words += word_count(unit)
                    cursor += 1
                    if chosen_words >= target_words:
                        break

        spoken_text = " ".join(chosen).strip()
        section_words = word_count(spoken_text)
        start_seconds = math.ceil(cumulative_words / words_per_second) if cumulative_words else 0
        cumulative_words += section_words
        end_seconds = math.ceil(cumulative_words / words_per_second) if cumulative_words else start_seconds
        sections.append(
            {
                **spec,
                "spoken_text": spoken_text,
                "word_count": section_words,
                "start_seconds": start_seconds,
                "end_seconds": max(start_seconds, end_seconds),
                "duration_seconds": max(0, end_seconds - start_seconds),
            }
        )
    return sections


def allocate_aligned_narration(
    body_text: str,
    specs: list[dict[str, Any]],
    alignment: dict[str, Any],
    words_per_second: float,
) -> list[dict[str, Any]]:
    aligned = alignment.get("sections", []) if isinstance(alignment, dict) else []
    if not aligned:
        raise ValueError("script_sections.json has no sections")
    spec_by_key = {str(spec.get("section_key", "")): spec for spec in specs}
    keys = [str(item.get("section_key", "")) for item in aligned if isinstance(item, dict)]
    if keys != list(spec_by_key):
        raise ValueError(f"script section keys do not match episode plan: {keys} != {list(spec_by_key)}")
    joined = " ".join(str(item.get("spoken_text", "") or "").strip() for item in aligned)
    norm = lambda value: re.sub(r"\s+", " ", value.strip())
    if norm(joined) != norm(body_text):
        raise ValueError("script_sections.json text does not match script.txt")

    sections: list[dict[str, Any]] = []
    cumulative_words = 0
    for item in aligned:
        key = str(item.get("section_key", ""))
        spoken_text = str(item.get("spoken_text", "") or "").strip()
        section_words = word_count(spoken_text)
        start_seconds = math.ceil(cumulative_words / words_per_second) if cumulative_words else 0
        cumulative_words += section_words
        end_seconds = math.ceil(cumulative_words / words_per_second) if cumulative_words else start_seconds
        sections.append(
            {
                **spec_by_key[key],
                "spoken_text": spoken_text,
                "word_count": section_words,
                "start_seconds": start_seconds,
                "end_seconds": max(start_seconds, end_seconds),
                "duration_seconds": max(0, end_seconds - start_seconds),
            }
        )
    return sections


def media_cues_for_section(
    media_segments: list[dict[str, Any]], start_seconds: int, end_seconds: int
) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    for segment in media_segments:
        if not isinstance(segment, dict) or segment.get("mode") != "media":
            continue
        try:
            start = float(segment.get("start_seconds", 0) or 0)
            end = float(segment.get("end_seconds", 0) or 0)
        except (TypeError, ValueError):
            continue
        if end <= start_seconds or start >= end_seconds:
            continue
        cues.append(
            {
                "start_seconds": start,
                "end_seconds": end,
                "visual_query": str(segment.get("visual_query", "") or ""),
                "on_screen_text": str(segment.get("on_screen_text", "") or ""),
                "reason": str(segment.get("reason", "") or ""),
            }
        )
    return cues


def build_production_payload(
    *,
    target_date: str,
    script: str,
    episode_plan: dict[str, Any],
    selected_news: dict[str, Any],
    media_plan: dict[str, Any],
    words_per_second: float,
    script_alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    closing_question = str(episode_plan.get("closing_question", "") or "")
    body_text, cta_text, cta_injected = extract_or_build_cta(script, closing_question)
    body_duration = estimate_seconds(body_text, words_per_second)
    specs = build_section_specs(episode_plan, selected_news, body_duration)
    if script_alignment and script_alignment.get("sections"):
        sections = allocate_aligned_narration(body_text, specs, script_alignment, words_per_second)
        alignment_mode = "writer_markers"
    else:
        sections = allocate_narration(body_text, specs, words_per_second)
        alignment_mode = "proportional_fallback"

    raw_segments = media_plan.get("segments", []) if isinstance(media_plan, dict) else []
    media_segments = [
        segment
        for segment in raw_segments
        if isinstance(segment, dict) and segment.get("mode") == "media"
    ]
    for section in sections:
        section["multimedia"] = media_cues_for_section(
            media_segments,
            int(section.get("start_seconds", 0)),
            int(section.get("end_seconds", 0)),
        )

    cta_start = int(sections[-1].get("end_seconds", 0)) if sections else 0
    cta_duration = estimate_seconds(cta_text, words_per_second)
    cta_section = {
        "kind": "cta",
        "title": "CTA — conversación y suscripción",
        "purpose": "Invitar a continuar la conversación sin romper el tono del ensayo.",
        "argument_role": "cta",
        "source_evidence": "",
        "spoken_text": cta_text,
        "word_count": word_count(cta_text),
        "start_seconds": cta_start,
        "end_seconds": cta_start + cta_duration,
        "duration_seconds": cta_duration,
        "multimedia": [],
        "visual_direction": "Presenter a cámara; cerrar con end card discreta y llamada a suscripción/comentarios.",
    }
    sections.append(cta_section)

    media_seconds = sum(
        max(
            0.0,
            float(segment.get("end_seconds", 0) or 0)
            - float(segment.get("start_seconds", 0) or 0),
        )
        for segment in media_segments
    )

    return {
        "schema_version": 1,
        "episode_date": target_date,
        "words_per_second": words_per_second,
        "original_script_word_count": word_count(script),
        "original_spoken_duration_seconds": estimate_seconds(script, words_per_second),
        "production_duration_seconds": cta_section["end_seconds"],
        "cta_injected": cta_injected,
        "cta_text": cta_text,
        "section_count": len(sections),
        "media_insert_count": len(media_segments),
        "planned_media_seconds": round(media_seconds, 1),
        "multimedia_plan_available": bool(raw_segments),
        "alignment_mode": alignment_mode,
        "sections": sections,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    sections = payload.get("sections", []) if isinstance(payload, dict) else []
    lines = [
        f"# Guion de producción — {payload.get('episode_date', '')}",
        "",
        "## Resumen de producción",
        "",
        f"- Duración narración original: {format_time(payload.get('original_spoken_duration_seconds', 0))}",
        f"- Duración estimada con CTA: {format_time(payload.get('production_duration_seconds', 0))}",
        f"- Bloques: {payload.get('section_count', 0)}",
        f"- Inserciones multimedia planificadas: {payload.get('media_insert_count', 0)}",
        f"- CTA: {'añadido por producción' if payload.get('cta_injected') else 'detectado en el guion'}",
        "",
        "## Capítulos / timecodes",
        "",
    ]

    for section in sections:
        lines.append(
            f"- {format_time(section.get('start_seconds', 0))} — {section.get('title', 'Sección')}"
        )

    for number, section in enumerate(sections, start=1):
        start = format_time(section.get("start_seconds", 0))
        end = format_time(section.get("end_seconds", 0))
        lines.extend(
            [
                "",
                f"## {number}. [{start}–{end}] {section.get('title', 'Sección')}",
                "",
                f"**Objetivo:** {section.get('purpose', '')}",
            ]
        )
        source_evidence = str(section.get("source_evidence", "") or "").strip()
        if source_evidence:
            lines.append(f"**Evidencia fuente:** {source_evidence}")
        human_stakes = str(section.get("human_stakes", "") or "").strip()
        if human_stakes:
            lines.append(f"**Consecuencia humana:** {human_stakes}")
        skepticism = str(section.get("skepticism_angle", "") or "").strip()
        if skepticism:
            lines.append(f"**Ángulo crítico:** {skepticism}")
        historical = str(section.get("historical_mirror", "") or "").strip()
        if historical:
            lines.append(f"**Espejo histórico:** {historical}")
        closing_question = str(section.get("closing_question", "") or "").strip()
        if closing_question:
            lines.append(f"**Pregunta de cierre:** {closing_question}")

        lines.extend(["", "### Narración", "", str(section.get("spoken_text", "") or "")])

        if section.get("kind") == "cta":
            lines.extend(
                [
                    "",
                    "### Dirección visual",
                    "",
                    str(section.get("visual_direction", "") or ""),
                ]
            )
            continue

        cues = section.get("multimedia", []) if isinstance(section, dict) else []
        lines.extend(["", "### Multimedia / B-roll", ""])
        if not cues:
            lines.append("- Presenter a cámara. Sin inserto multimedia específico en el plan actual.")
        else:
            for cue in cues:
                cue_start = format_time(cue.get("start_seconds", 0))
                cue_end = format_time(cue.get("end_seconds", 0))
                lines.append(f"- [{cue_start}–{cue_end}] MEDIA")
                on_screen = str(cue.get("on_screen_text", "") or "").strip()
                query = str(cue.get("visual_query", "") or "").strip()
                reason = str(cue.get("reason", "") or "").strip()
                if on_screen:
                    lines.append(f"  - Texto en pantalla: {on_screen}")
                if query:
                    lines.append(f"  - Búsqueda visual: `{query}`")
                if reason:
                    lines.append(f"  - Función: {reason}")

    lines.append("")
    return "\n".join(lines)


def create_production_script(
    *,
    target_date: str,
    scripts_root: Path,
    multimedia_root: Path,
    words_per_second: float | None = None,
) -> tuple[Path, Path] | None:
    episode_scripts = scripts_root / target_date
    script_path = episode_scripts / "script.txt"
    script = read_text(script_path)
    if not script:
        print(f"Production script skipped: no script at {script_path}")
        return None

    run_state = read_json(episode_scripts / "run_state.json", {})
    alignment = read_json(episode_scripts / "script_sections.json", {})
    approved = str(run_state.get("status", "") or "") == "approved"
    if approved and not (isinstance(alignment, dict) and alignment.get("sections")):
        raise RuntimeError("Approved episode is missing script_sections.json alignment")
    try:
        payload = build_production_payload(
            target_date=target_date,
            script=script,
            episode_plan=read_json(episode_scripts / "episode_plan.json", {}),
            selected_news=read_json(episode_scripts / "selected_news.json", {}),
            media_plan=read_json(multimedia_root / target_date / "plan.json", {}),
            words_per_second=words_per_second or CONFIG.words_per_second,
            script_alignment=alignment,
        )
    except ValueError as exc:
        if approved:
            raise RuntimeError(f"Approved episode has invalid script section alignment: {exc}") from exc
        payload = build_production_payload(
            target_date=target_date,
            script=script,
            episode_plan=read_json(episode_scripts / "episode_plan.json", {}),
            selected_news=read_json(episode_scripts / "selected_news.json", {}),
            media_plan=read_json(multimedia_root / target_date / "plan.json", {}),
            words_per_second=words_per_second or CONFIG.words_per_second,
            script_alignment=None,
        )
        payload["alignment_warning"] = str(exc)

    json_path = episode_scripts / "production_script.json"
    md_path = episode_scripts / "production_script.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(f"Production script created at {md_path}")
    return md_path, json_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create production_script.md/json from the final narration and media plan"
    )
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--multimedia-dir", default="multimedia")
    parser.add_argument("--words-per-second", type=float, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    create_production_script(
        target_date=args.target_date,
        scripts_root=Path(args.scripts_dir),
        multimedia_root=Path(args.multimedia_dir),
        words_per_second=args.words_per_second,
    )


if __name__ == "__main__":
    main()
