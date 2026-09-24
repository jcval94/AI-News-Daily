from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
from pathlib import Path
from typing import Any

from pipeline.production_script import split_sentences, word_count

SCHEMA_VERSION = 1


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _slug(value: Any, *, fallback: str = "block", limit: int = 40) -> str:
    text = str(value or "").strip().lower()
    text = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
        .replace("ñ", "n")
    )
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return (text or fallback)[:limit].rstrip("_")


def _script_sha256(script: str) -> str:
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def _validate_script_alignment(script: str, script_sections: dict[str, Any]) -> None:
    sections = script_sections.get("sections", []) if isinstance(script_sections, dict) else []
    if not sections:
        raise ValueError("script_sections.json is required to build the recording pack")
    joined = " ".join(
        str(item.get("spoken_text", "") or "").strip()
        for item in sections
        if isinstance(item, dict)
    )
    if _normalize_text(joined) != _normalize_text(script):
        raise ValueError(
            "script_sections.json narration does not match script.txt; refusing to build a stale recording pack"
        )


def _split_long_sentence(sentence: str, max_words: int) -> list[str]:
    if word_count(sentence) <= max_words:
        return [sentence.strip()]
    clauses = [
        item.strip()
        for item in re.split(r"(?<=[,;:])\s+|\s+(?=[—–-]\s)", sentence.strip())
        if item.strip()
    ]
    if len(clauses) > 1 and all(word_count(item) <= max_words for item in clauses):
        result: list[str] = []
        current: list[str] = []
        current_words = 0
        for clause in clauses:
            count = word_count(clause)
            if current and current_words + count > max_words:
                result.append(" ".join(current).strip())
                current = []
                current_words = 0
            current.append(clause)
            current_words += count
        if current:
            result.append(" ".join(current).strip())
        return result

    words = sentence.split()
    return [
        " ".join(words[index : index + max_words]).strip()
        for index in range(0, len(words), max_words)
        if words[index : index + max_words]
    ]


def split_recording_takes(
    text: str,
    *,
    words_per_second: float,
    min_seconds: float = 20.0,
    target_seconds: float = 35.0,
    max_seconds: float = 60.0,
) -> list[str]:
    if not text.strip():
        return []
    wps = max(0.1, float(words_per_second))
    min_words = max(1, round(min_seconds * wps))
    target_words = max(min_words, round(target_seconds * wps))
    max_words = max(target_words, round(max_seconds * wps))

    units: list[str] = []
    for sentence in split_sentences(text):
        units.extend(_split_long_sentence(sentence, max_words))
    if not units:
        units = _split_long_sentence(text, max_words)

    chunks: list[list[str]] = []
    current: list[str] = []
    current_words = 0
    for unit in units:
        count = max(1, word_count(unit))
        if current and current_words >= min_words and current_words + count > max_words:
            chunks.append(current)
            current = []
            current_words = 0
        current.append(unit)
        current_words += count
        if current_words >= target_words:
            chunks.append(current)
            current = []
            current_words = 0
    if current:
        chunks.append(current)

    # Avoid tiny tails. Merge when possible; otherwise rebalance whole sentence/clause
    # units from the previous take without crossing min/max bounds.
    for index in range(len(chunks) - 1, 0, -1):
        current_words = sum(word_count(item) for item in chunks[index])
        if current_words >= min_words:
            continue
        previous_words = sum(word_count(item) for item in chunks[index - 1])
        if previous_words + current_words <= max_words:
            chunks[index - 1].extend(chunks[index])
            chunks.pop(index)
            continue
        while current_words < min_words and len(chunks[index - 1]) > 1:
            candidate = chunks[index - 1][-1]
            candidate_words = word_count(candidate)
            if previous_words - candidate_words < min_words:
                break
            if current_words + candidate_words > max_words:
                break
            chunks[index - 1].pop()
            chunks[index].insert(0, candidate)
            previous_words -= candidate_words
            current_words += candidate_words

    result = [" ".join(chunk).strip() for chunk in chunks if chunk]
    if _normalize_text(" ".join(result)) != _normalize_text(text):
        raise ValueError("Recording take splitter changed the approved narration")
    return result


def _section_label(section: dict[str, Any], position: int) -> str:
    key = str(section.get("section_key", "") or "")
    if key == "opening":
        return "Apertura"
    if key == "synthesis":
        return "Síntesis"
    if str(section.get("kind", "") or "") == "cta":
        return "CTA"
    beat_id = str(section.get("beat_id", "") or "")
    return f"Bloque {position + 1}" + (f" · {beat_id}" if beat_id else "")


def _take_prefix(section: dict[str, Any], position: int) -> str:
    key = str(section.get("section_key", "") or "")
    if key == "opening":
        return "opening"
    if key == "synthesis":
        return "synthesis"
    if str(section.get("kind", "") or "") == "cta":
        return "cta"
    beat_id = _slug(section.get("beat_id") or key, fallback=f"beat_{position + 1}")
    return f"b{position:02d}_{beat_id}"


def _delivery_profile(section: dict[str, Any]) -> dict[str, Any]:
    kind = str(section.get("kind", "") or "").lower()
    beat_kind = str(section.get("beat_kind", "") or "").lower()
    if kind == "opening":
        return {
            "energy": "high",
            "pace": "deliberate_fast",
            "note": "Abrir con intención y contacto directo a lente. No correr: energía alta no significa hablar deprisa.",
        }
    if kind == "cta":
        return {
            "energy": "warm",
            "pace": "conversational",
            "note": "Bajar la sensación de guion y hablar como cierre directo a una persona.",
        }
    if kind == "synthesis":
        return {
            "energy": "calm",
            "pace": "deliberate",
            "note": "Dejar respirar la conclusión. Priorizar claridad sobre velocidad.",
        }
    if beat_kind in {"human_stakes", "reflection"}:
        return {
            "energy": "warm",
            "pace": "calm",
            "note": "Mantener naturalidad y espacio entre ideas; evitar dramatizar de más.",
        }
    if beat_kind in {"evidence", "reveal"}:
        return {
            "energy": "grounded",
            "pace": "precise",
            "note": "Dar énfasis a datos y relaciones causales sin sonar como lectura de una lista.",
        }
    if beat_kind in {"turn", "complication"}:
        return {
            "energy": "focused",
            "pace": "deliberate",
            "note": "Marcar verbalmente el giro de la idea y hacer una micro-pausa antes de la consecuencia.",
        }
    return {
        "energy": "natural",
        "pace": "conversational",
        "note": "Hablar a cámara como explicación, no como lectura. Mantener el significado exacto.",
    }


def _edit_cues_for_take(
    edit_manifest: dict[str, Any],
    start_seconds: float,
    end_seconds: float,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in edit_manifest.get("timeline", []) if isinstance(edit_manifest, dict) else []:
        if not isinstance(item, dict) or item.get("mode") != "media":
            continue
        start = float(item.get("start_seconds", 0) or 0)
        end = float(item.get("end_seconds", start) or start)
        if end <= start_seconds or start >= end_seconds:
            continue
        director = item.get("director", {}) if isinstance(item.get("director"), dict) else {}
        media = item.get("media", {}) if isinstance(item.get("media"), dict) else {}
        result.append(
            {
                "cue_id": item.get("cue_id"),
                "start_seconds": start,
                "end_seconds": end,
                "visual_role": str(director.get("visual_role", "") or ""),
                "intent": str(director.get("intent", "") or ""),
                "director_note": str(director.get("note", "") or ""),
                "preferred_asset_type": str(media.get("preferred_asset_type", "") or ""),
                "visual_query": str(media.get("visual_query", "") or ""),
                "on_screen_text": str(media.get("on_screen_text", "") or ""),
            }
        )
    return result


def _cta_section(production_script: dict[str, Any]) -> dict[str, Any] | None:
    # An existing CTA already belongs to the approved script and therefore to
    # script_sections.json. Append only a production-injected CTA; never duplicate narration.
    if isinstance(production_script, dict) and production_script.get("cta_injected") is False:
        return None
    sections = production_script.get("sections", []) if isinstance(production_script, dict) else []
    for section in reversed(sections):
        if isinstance(section, dict) and str(section.get("kind", "") or "") == "cta":
            spoken = str(section.get("spoken_text", "") or "").strip()
            if spoken:
                return {
                    "section_key": "cta",
                    "kind": "cta",
                    "beat_id": None,
                    "beat_kind": None,
                    "evidence_ids": [],
                    "spoken_text": spoken,
                    "word_count": word_count(spoken),
                    "title": str(section.get("title", "") or "CTA"),
                }
    return None


def build_recording_pack(
    *,
    episode_date: str,
    script: str,
    script_sections: dict[str, Any],
    edit_manifest: dict[str, Any] | None,
    production_script: dict[str, Any] | None,
    words_per_second: float,
    min_take_seconds: float = 20.0,
    target_take_seconds: float = 35.0,
    max_take_seconds: float = 60.0,
) -> dict[str, Any]:
    _validate_script_alignment(script, script_sections)
    if not (0 < min_take_seconds <= target_take_seconds <= max_take_seconds):
        raise ValueError("Take duration policy must satisfy 0 < min <= target <= max")

    sections = [
        dict(item)
        for item in script_sections.get("sections", [])
        if isinstance(item, dict)
    ]
    cta = _cta_section(production_script or {})
    if cta:
        sections.append(cta)

    takes: list[dict[str, Any]] = []
    cumulative_words = 0
    source_script_words = word_count(script)
    for section_position, section in enumerate(sections):
        spoken = str(section.get("spoken_text", "") or "").strip()
        if not spoken:
            continue
        take_texts = split_recording_takes(
            spoken,
            words_per_second=words_per_second,
            min_seconds=min_take_seconds,
            target_seconds=target_take_seconds,
            max_seconds=max_take_seconds,
        )
        prefix = _take_prefix(section, section_position)
        delivery = _delivery_profile(section)
        for take_index, take_text in enumerate(take_texts, start=1):
            words = word_count(take_text)
            start_seconds = cumulative_words / words_per_second
            cumulative_words += words
            end_seconds = cumulative_words / words_per_second
            take_id = f"{prefix}_t{take_index:02d}"
            cues = _edit_cues_for_take(
                edit_manifest or {},
                start_seconds,
                end_seconds,
            )
            takes.append(
                {
                    "take_id": take_id,
                    "take_number_in_section": take_index,
                    "section_position": section_position,
                    "section_key": str(section.get("section_key", "") or ""),
                    "section_kind": str(section.get("kind", "") or ""),
                    "beat_id": section.get("beat_id"),
                    "beat_kind": section.get("beat_kind"),
                    "evidence_ids": [
                        str(value) for value in section.get("evidence_ids", []) if str(value)
                    ],
                    "section_label": _section_label(section, section_position),
                    "spoken_slate": f"TAKE {take_id}",
                    "spoken_text": take_text,
                    "word_count": words,
                    "estimated_start_seconds": round(start_seconds, 3),
                    "estimated_end_seconds": round(end_seconds, 3),
                    "estimated_duration_seconds": round(end_seconds - start_seconds, 3),
                    "delivery": dict(delivery),
                    "recording_cues": {
                        "look_at_lens": True,
                        "pre_roll_seconds": 2.0,
                        "post_roll_seconds": 2.0,
                        "pause_before_first_word_seconds": 1.0,
                        "slate_recommended": True,
                    },
                    "edit_cues": cues,
                }
            )

    joined_original = " ".join(
        take["spoken_text"]
        for take in takes
        if take.get("section_kind") != "cta"
    )
    if _normalize_text(joined_original) != _normalize_text(script):
        raise ValueError("Recording pack takes do not reconstruct the approved script")

    cta_words = max(0, cumulative_words - source_script_words)
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_date": str(episode_date),
        "status": "pre_recording",
        "sources": {
            "script": f"scripts/{episode_date}/script.txt",
            "script_sections": f"scripts/{episode_date}/script_sections.json",
            "production_script": f"scripts/{episode_date}/production_script.json",
            "edit_manifest": f"multimedia/{episode_date}/edit_manifest.json",
            "script_sha256": _script_sha256(script),
        },
        "editing_style": (
            dict(edit_manifest.get("editing_style", {}))
            if isinstance(edit_manifest, dict)
            and isinstance(edit_manifest.get("editing_style"), dict)
            else {"applied": False}
        ),
        "take_policy": {
            "min_seconds": float(min_take_seconds),
            "target_seconds": float(target_take_seconds),
            "max_seconds": float(max_take_seconds),
            "words_per_second": float(words_per_second),
            "split_basis": "sentence_boundaries_then_clause_fallback",
            "approved_script_is_immutable": True,
        },
        "capture_recommendation": {
            "orientation": "landscape",
            "aspect_ratio": "16:9",
            "resolution": "3840x2160",
            "frame_rate_fps": 30,
            "audio_sample_rate_hz": 48000,
            "camera": {
                "eye_level": True,
                "lock_focus": True,
                "lock_exposure": True,
                "lock_white_balance": True,
            },
            "note": "Recommendations only. The recording contract does not depend on a specific camera or editor.",
        },
        "recording_protocol": {
            "strategy": "record_by_take",
            "slate_format": "TAKE <take_id>",
            "slate_required": False,
            "slate_recommended_for_future_alignment": True,
            "pre_roll_seconds": 2.0,
            "post_roll_seconds": 2.0,
            "retake_rule": (
                "If a take fails, stop, reset, repeat the same spoken slate, and record the full take again. "
                "Do not splice a sentence while recording; selection happens during ingest."
            ),
        },
        "teleprompter_defaults": {
            "font_size_px": 64,
            "line_height": 1.35,
            "scroll_speed_px_per_second": 42,
            "countdown_seconds": 3,
            "show_director_notes": False,
            "mirror": False,
        },
        "readiness": {
            "recording_contract_valid": True,
            "ready_to_record": bool(takes),
            "requires_recorded_media": True,
            "ready_for_alignment": False,
            "blockers_after_recording": ["recorded_media_required"],
        },
        "summary": {
            "take_count": len(takes),
            "section_count": len(sections),
            "script_word_count": source_script_words,
            "cta_word_count": cta_words,
            "recording_word_count": cumulative_words,
            "estimated_recording_script_seconds": round(cumulative_words / words_per_second, 3),
            "takes_with_edit_cues": sum(1 for take in takes if take.get("edit_cues")),
        },
        "takes": takes,
    }


def render_camera_script(pack: dict[str, Any]) -> str:
    lines = [
        f"# Camera script — {pack.get('episode_date', '')}",
        "",
        "> El texto hablado es el guion aprobado. Las notas de cámara/dirección no forman parte de la narración.",
        "",
        "## Protocolo",
        "",
        "- Graba por take completo.",
        "- Opcional pero recomendado: di la claqueta indicada, deja ~1 s y comienza.",
        "- Deja ~2 s de aire antes/después de cada toma.",
        "- Si fallas, repite la toma completa con el mismo ID.",
        "",
    ]
    for take in pack.get("takes", []):
        duration = float(take.get("estimated_duration_seconds", 0) or 0)
        delivery = take.get("delivery", {}) if isinstance(take.get("delivery"), dict) else {}
        lines.extend(
            [
                f"## {take.get('take_id')} — {take.get('section_label', '')}",
                "",
                f"**Duración estimada:** {duration:.1f} s  ",
                f"**Claqueta recomendada:** `{take.get('spoken_slate', '')}`  ",
                f"**Entrega:** {delivery.get('energy', '')} · {delivery.get('pace', '')}",
                "",
                f"> {delivery.get('note', '')}",
                "",
                "### Narración",
                "",
                str(take.get("spoken_text", "") or ""),
                "",
            ]
        )
        cues = take.get("edit_cues", []) if isinstance(take.get("edit_cues"), list) else []
        if cues:
            lines.extend(["### Notas de edición previstas", ""])
            for cue in cues:
                lines.append(
                    f"- `{cue.get('cue_id', '')}` · {cue.get('visual_role', '')}: "
                    f"{cue.get('director_note', '') or cue.get('intent', '')}"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _teleprompter_payload(pack: dict[str, Any]) -> str:
    payload = json.dumps(pack, ensure_ascii=False)
    return payload.replace("</", "<\/")


def render_teleprompter(pack: dict[str, Any]) -> str:
    payload = _teleprompter_payload(pack)
    title = html.escape(f"Teleprompter — {pack.get('episode_date', '')}")
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root {{ --font-size: 64px; --line-height: 1.35; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: #090909; color: #f5f5f5; font-family: Arial, Helvetica, sans-serif; }}
body {{ min-height: 100vh; overflow: hidden; }}
#app {{ height: 100vh; display: grid; grid-template-rows: auto 1fr auto; }}
header, footer {{ background: #111; border-color: #292929; padding: 10px 16px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
header {{ border-bottom: 1px solid #292929; }}
footer {{ border-top: 1px solid #292929; }}
button, select, input {{ font: inherit; }}
button {{ background: #202020; color: #fff; border: 1px solid #3a3a3a; border-radius: 9px; padding: 8px 12px; cursor: pointer; }}
button:hover {{ background: #2b2b2b; }}
button.primary {{ background: #f5f5f5; color: #111; }}
.meta {{ color: #a9a9a9; font-size: 14px; margin-left: auto; }}
#viewport {{ overflow-y: auto; scroll-behavior: auto; padding: 28vh 10vw 55vh; }}
#viewport.mirror {{ transform: scaleX(-1); }}
#slate {{ font-size: 20px; letter-spacing: .08em; color: #a9a9a9; text-transform: uppercase; margin-bottom: 36px; }}
#text {{ font-size: var(--font-size); line-height: var(--line-height); font-weight: 650; max-width: 1200px; margin: 0 auto; white-space: pre-wrap; }}
#notes {{ max-width: 1200px; margin: 60px auto 0; padding: 18px 20px; border: 1px solid #333; border-radius: 12px; color: #c7c7c7; font-size: 18px; line-height: 1.5; display: none; }}
#notes.visible {{ display: block; }}
#countdown {{ position: fixed; inset: 0; display: none; align-items: center; justify-content: center; background: rgba(0,0,0,.88); z-index: 20; font-size: 22vw; font-weight: 800; }}
#countdown.visible {{ display: flex; }}
.range {{ display: inline-flex; gap: 6px; align-items: center; color: #bbb; font-size: 13px; }}
input[type=range] {{ width: 110px; }}
kbd {{ border: 1px solid #555; padding: 2px 5px; border-radius: 5px; color: #bbb; }}
@media (max-width: 800px) {{
  #viewport {{ padding-left: 7vw; padding-right: 7vw; }}
  header .secondary {{ display: none; }}
  .meta {{ width: 100%; margin-left: 0; }}
}}
</style>
</head>
<body>
<div id="app">
  <header>
    <button id="prev">← Take</button>
    <button id="next">Take →</button>
    <button id="start" class="primary">▶ Iniciar</button>
    <button id="reset">↺ Inicio</button>
    <button id="mirror">Espejo</button>
    <button id="notesBtn">Notas</button>
    <button id="fullscreen">Pantalla completa</button>
    <span class="range">Texto <input id="fontSize" type="range" min="36" max="100" step="2"></span>
    <span class="range">Velocidad <input id="speed" type="range" min="10" max="120" step="2"></span>
    <div class="meta" id="meta"></div>
  </header>
  <main id="viewport">
    <div id="slate"></div>
    <article id="text"></article>
    <aside id="notes"></aside>
  </main>
  <footer>
    <span><kbd>Space</kbd> iniciar/pausar · <kbd>←</kbd>/<kbd>→</kbd> take · <kbd>M</kbd> espejo · <kbd>N</kbd> notas · <kbd>F</kbd> fullscreen</span>
  </footer>
</div>
<div id="countdown"></div>
<script>
const PACK = {payload};
const takes = PACK.takes || [];
const defaults = PACK.teleprompter_defaults || {{}};
let index = 0;
let running = false;
let raf = null;
let lastTs = null;
let countdownActive = false;
let countdownTimer = null;

const viewport = document.getElementById('viewport');
const text = document.getElementById('text');
const slate = document.getElementById('slate');
const notes = document.getElementById('notes');
const meta = document.getElementById('meta');
const countdown = document.getElementById('countdown');
const fontSize = document.getElementById('fontSize');
const speed = document.getElementById('speed');

fontSize.value = localStorage.getItem('teleprompter.fontSize') || defaults.font_size_px || 64;
speed.value = localStorage.getItem('teleprompter.speed') || defaults.scroll_speed_px_per_second || 42;
document.documentElement.style.setProperty('--font-size', fontSize.value + 'px');
document.documentElement.style.setProperty('--line-height', defaults.line_height || 1.35);
if ((localStorage.getItem('teleprompter.mirror') || 'false') === 'true') viewport.classList.add('mirror');

function escapeHtml(value) {{
  return String(value || '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[c]));
}}

function renderTake() {{
  stop();
  const take = takes[index];
  if (!take) {{
    slate.textContent = 'Sin takes';
    text.textContent = '';
    meta.textContent = '';
    return;
  }}
  viewport.scrollTop = 0;
  slate.textContent = 'DI: ' + (take.spoken_slate || take.take_id);
  text.textContent = take.spoken_text || '';
  const delivery = take.delivery || {{}};
  const cues = take.edit_cues || [];
  notes.innerHTML =
    '<strong>' + escapeHtml(take.section_label) + '</strong><br>' +
    escapeHtml(delivery.note || '') +
    (cues.length ? '<hr>' + cues.map(c =>
      '<div><strong>' + escapeHtml(c.visual_role || 'visual') + '</strong>: ' +
      escapeHtml(c.director_note || c.intent || '') + '</div>'
    ).join('') : '');
  meta.textContent =
    (index + 1) + '/' + takes.length + ' · ' + take.take_id +
    ' · ~' + Number(take.estimated_duration_seconds || 0).toFixed(0) + ' s' +
    ' · ' + (delivery.energy || '') + '/' + (delivery.pace || '');
  document.getElementById('start').textContent = '▶ Iniciar';
}}

function tick(ts) {{
  if (!running) return;
  if (lastTs === null) lastTs = ts;
  const dt = (ts - lastTs) / 1000;
  lastTs = ts;
  viewport.scrollTop += Number(speed.value) * dt;
  if (viewport.scrollTop + viewport.clientHeight >= viewport.scrollHeight - 2) {{
    stop();
    return;
  }}
  raf = requestAnimationFrame(tick);
}}

function stop() {{
  running = false;
  lastTs = null;
  if (raf) cancelAnimationFrame(raf);
  raf = null;
  if (countdownTimer) clearInterval(countdownTimer);
  countdownTimer = null;
  countdownActive = false;
  countdown.classList.remove('visible');
  document.getElementById('start').textContent = '▶ Iniciar';
}}

function play() {{
  if (countdownActive || running) {{ stop(); return; }}
  const seconds = Number(defaults.countdown_seconds || 3);
  countdownActive = true;
  let value = seconds;
  countdown.textContent = value;
  countdown.classList.add('visible');
  countdownTimer = setInterval(() => {{
    value -= 1;
    if (value <= 0) {{
      clearInterval(countdownTimer);
      countdownTimer = null;
      countdown.classList.remove('visible');
      countdownActive = false;
      running = true;
      lastTs = null;
      document.getElementById('start').textContent = '❚❚ Pausar';
      raf = requestAnimationFrame(tick);
    }} else {{
      countdown.textContent = value;
    }}
  }}, 1000);
}}

document.getElementById('start').addEventListener('click', play);
document.getElementById('reset').addEventListener('click', () => {{ stop(); viewport.scrollTop = 0; }});
document.getElementById('prev').addEventListener('click', () => {{ if (index > 0) {{ index--; renderTake(); }} }});
document.getElementById('next').addEventListener('click', () => {{ if (index < takes.length - 1) {{ index++; renderTake(); }} }});
document.getElementById('mirror').addEventListener('click', () => {{
  viewport.classList.toggle('mirror');
  localStorage.setItem('teleprompter.mirror', viewport.classList.contains('mirror'));
}});
document.getElementById('notesBtn').addEventListener('click', () => notes.classList.toggle('visible'));
document.getElementById('fullscreen').addEventListener('click', async () => {{
  if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
  else await document.exitFullscreen();
}});
fontSize.addEventListener('input', () => {{
  document.documentElement.style.setProperty('--font-size', fontSize.value + 'px');
  localStorage.setItem('teleprompter.fontSize', fontSize.value);
}});
speed.addEventListener('input', () => localStorage.setItem('teleprompter.speed', speed.value));
document.addEventListener('keydown', (event) => {{
  if (event.code === 'Space') {{ event.preventDefault(); play(); }}
  else if (event.key === 'ArrowLeft' && index > 0) {{ index--; renderTake(); }}
  else if (event.key === 'ArrowRight' && index < takes.length - 1) {{ index++; renderTake(); }}
  else if (event.key.toLowerCase() === 'm') document.getElementById('mirror').click();
  else if (event.key.toLowerCase() === 'n') document.getElementById('notesBtn').click();
  else if (event.key.toLowerCase() === 'f') document.getElementById('fullscreen').click();
}});
renderTake();
</script>
</body>
</html>
"""


def write_recording_pack(
    *,
    episode_dir: Path,
    media_dir: Path,
    words_per_second: float,
    min_take_seconds: float = 20.0,
    target_take_seconds: float = 35.0,
    max_take_seconds: float = 60.0,
) -> tuple[Path, Path, Path]:
    script = _read_text(episode_dir / "script.txt")
    if not script:
        raise FileNotFoundError(f"Missing or empty script: {episode_dir / 'script.txt'}")
    script_sections = _read_json(episode_dir / "script_sections.json", {})
    production_script = _read_json(episode_dir / "production_script.json", {})
    edit_manifest = _read_json(media_dir / "edit_manifest.json", {})
    state = _read_json(episode_dir / "run_state.json", {})
    episode_date = str(state.get("episode_date", "") or episode_dir.name)

    pack = build_recording_pack(
        episode_date=episode_date,
        script=script,
        script_sections=script_sections,
        edit_manifest=edit_manifest,
        production_script=production_script,
        words_per_second=words_per_second,
        min_take_seconds=min_take_seconds,
        target_take_seconds=target_take_seconds,
        max_take_seconds=max_take_seconds,
    )

    json_path = episode_dir / "recording_pack.json"
    camera_path = episode_dir / "camera_script.md"
    teleprompter_path = episode_dir / "teleprompter.html"
    json_path.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    camera_path.write_text(render_camera_script(pack), encoding="utf-8")
    teleprompter_path.write_text(render_teleprompter(pack), encoding="utf-8")
    return json_path, camera_path, teleprompter_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the presenter recording pack and standalone teleprompter"
    )
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--multimedia-dir", default="multimedia")
    parser.add_argument("--words-per-second", type=float, default=2.5)
    parser.add_argument("--min-take-seconds", type=float, default=20.0)
    parser.add_argument("--target-take-seconds", type=float, default=35.0)
    parser.add_argument("--max-take-seconds", type=float, default=60.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    episode_dir = Path(args.scripts_dir) / args.target_date
    media_dir = Path(args.multimedia_dir) / args.target_date
    paths = write_recording_pack(
        episode_dir=episode_dir,
        media_dir=media_dir,
        words_per_second=args.words_per_second,
        min_take_seconds=args.min_take_seconds,
        target_take_seconds=args.target_take_seconds,
        max_take_seconds=args.max_take_seconds,
    )
    print(
        json.dumps(
            {
                "recording_pack": str(paths[0]),
                "camera_script": str(paths[1]),
                "teleprompter": str(paths[2]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
