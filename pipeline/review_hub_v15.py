from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v14 import build_script_structure_payload
from pipeline.review_hub_v14 import build_site as _build_site_v14

VOICE_CSS = r"""
/* v15: TTS observability is colocated with Script; audio is always demand-loaded. */
.voice-panel{max-width:850px;margin:0 auto 12px;border:1px solid #2b4156;border-radius:15px;background:#0d1620;padding:12px 13px;color:#dce9f5}
.voice-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.voice-head h3{margin:0;font-size:13px}.voice-head p{margin:3px 0 0;color:var(--muted);font-size:10px;line-height:1.45}.voice-state{font-size:9px;font-weight:800;border:1px solid #35506a;border-radius:999px;padding:4px 7px;white-space:nowrap}.voice-state.ready{border-color:#357257;color:#a8efc7}.voice-state.off{color:#9fb0c1}
.voice-meta{display:flex;gap:6px;flex-wrap:wrap;margin:9px 0}.voice-chip{font-size:9px;border:1px solid #2c4054;border-radius:999px;padding:4px 7px;color:#b9cad9}.voice-master{margin:9px 0}.voice-master audio,.voice-section audio{width:100%;height:32px}.voice-sections{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:7px}.voice-section{border:1px solid #263a4d;border-radius:10px;background:#101b26;padding:8px}.voice-section strong{font-size:10px}.voice-section small{display:block;color:#8fa2b6;font-size:9px;margin:3px 0 6px}.voice-empty{font-size:10px;color:#91a4b5;padding:7px 0}.voice-qa{font-size:9px;color:#93a8b9;margin-top:8px}
.voice-benchmark{max-width:850px;margin:0 auto 12px;border:1px solid #293d50;border-radius:15px;background:#0b141d;padding:12px 13px;color:#dce9f5}
.voice-benchmark h3{margin:0;font-size:12px}.voice-benchmark p{margin:3px 0 8px;color:var(--muted);font-size:10px;line-height:1.45}
.voice-benchmark details{border:1px solid #26394b;border-radius:9px;padding:7px 8px;margin:7px 0}.voice-benchmark summary{cursor:pointer;font-size:9px;color:#b9cad9}
.voice-benchmark-text{white-space:pre-wrap;font-size:9px;color:#9eb0c0;line-height:1.5;margin-top:7px}
.voice-benchmark-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:7px}.voice-candidate{border:1px solid #263a4d;border-radius:10px;background:#101b26;padding:8px}
.voice-candidate strong{font-size:10px}.voice-candidate small{display:block;color:#8fa2b6;font-size:9px;margin:3px 0 6px}.voice-candidate audio{width:100%;height:32px}
"""


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _duration(value: Any) -> str:
    try:
        seconds = max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"


def _voice_markup(episode_dir: Path) -> str:
    web = _read_json(episode_dir / "tts" / "narration_web.json")
    structure = build_script_structure_payload(episode_dir) or {}
    labels = {
        str(x.get("section_key")): str(x.get("label") or x.get("section_key"))
        for x in structure.get("sections", []) if isinstance(x, dict)
    }
    if not web:
        return (
            '<section class="voice-panel" data-tts-panel="v1" data-tts-status="unavailable">'
            '<div class="voice-head"><div><h3>Voice · TTS</h3><p>Narración local-first por sección semántica. Los audios pesados no viven en Git.</p></div>'
            '<span class="voice-state off">No disponible</span></div>'
            '<div class="voice-empty">Este episodio todavía no tiene un contrato web de narración publicado. El pipeline editorial no queda bloqueado por ello.</div>'
            '<div class="voice-qa">QA y Voice Bake-off aparecerán aquí cuando exista una ejecución local publicada.</div></section>'
        )
    available = bool(web.get("available") and web.get("master_preview_url"))
    state = '<span class="voice-state ready">TTS disponible</span>' if available else '<span class="voice-state off">Sin audio publicado</span>'
    chips = [
        f'<span class="voice-chip">{html.escape(str(web.get("engine") or "—"))}</span>',
        f'<span class="voice-chip">{html.escape(str(web.get("voice") or "—"))}</span>',
        f'<span class="voice-chip">{_duration(web.get("duration_seconds"))}</span>',
        f'<span class="voice-chip">{int(web.get("section_count") or 0)} secciones</span>',
        f'<span class="voice-chip">QA {html.escape(str(web.get("qa_status") or "—"))}</span>',
    ]
    master = ""
    if available:
        master = f'<div class="voice-master"><audio controls preload="none" src="{html.escape(str(web["master_preview_url"]), quote=True)}"></audio></div>'
    cards = []
    for item in web.get("sections", []) if isinstance(web.get("sections"), list) else []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "section")
        label = labels.get(sid, sid)
        player = ""
        if item.get("preview_url"):
            player = f'<audio controls preload="none" src="{html.escape(str(item["preview_url"]), quote=True)}"></audio>'
        cards.append(
            f'<div class="voice-section"><strong>{int(item.get("order") or 0)+1}. {html.escape(label)}</strong>'
            f'<small>{_duration(item.get("duration_seconds"))} · {html.escape(str(item.get("kind") or ""))}</small>{player}</div>'
        )
    warnings = web.get("warnings") if isinstance(web.get("warnings"), list) else []
    warning_copy = " · ".join(str(x) for x in warnings[:3]) if warnings else "Sin warnings técnicos publicados."
    return (
        '<section class="voice-panel" data-tts-panel="v1" data-tts-status="available">'
        '<div class="voice-head"><div><h3>Voice · TTS</h3><p>Narración por sección; audio bajo demanda con preload=none.</p></div>' + state + '</div>'
        '<div class="voice-meta">' + ''.join(chips) + '</div>' + master +
        ('<div class="voice-sections">' + ''.join(cards) + '</div>' if cards else '<div class="voice-empty">No hay previews de secciones publicados.</div>') +
        f'<div class="voice-qa">{html.escape(warning_copy)} · Bake-off perceptual: evaluación manual, no score automático.</div></section>'
    )



def _benchmark_markup(episode_dir: Path) -> str:
    web = _read_json(episode_dir / "tts" / "benchmark_web.json")
    if not web:
        return ""
    candidates = web.get("candidates") if isinstance(web.get("candidates"), list) else []
    cards: list[str] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        engine = html.escape(str(item.get("engine") or "—"))
        voice = html.escape(str(item.get("voice") or "—"))
        status = str(item.get("status") or "error")
        duration = _duration(item.get("duration_seconds"))
        rtf_value = item.get("real_time_factor")
        try:
            rtf = f"{float(rtf_value):.2f}× RTF" if rtf_value is not None else "RTF —"
        except (TypeError, ValueError):
            rtf = "RTF —"
        player = ""
        if item.get("preview_url"):
            player = f'<audio controls preload="none" src="{html.escape(str(item["preview_url"]), quote=True)}"></audio>'
        perceptual = item.get("perceptual") if isinstance(item.get("perceptual"), dict) else {}
        manual_values = [
            perceptual.get(key)
            for key in ("naturalness", "pronunciation", "prosody", "energy", "clarity", "pace", "stability")
        ]
        manual = "evaluación manual pendiente" if all(value is None for value in manual_values) else "evaluación manual registrada"
        error = f'<div class="voice-qa">{html.escape(str(item.get("error")))}</div>' if status != "ok" and item.get("error") else ""
        cards.append(
            f'<div class="voice-candidate"><strong>{engine} · {voice}</strong>'
            f'<small>{html.escape(status)} · {duration} · {html.escape(rtf)} · {manual}</small>{player}{error}</div>'
        )
    common_text = html.escape(str(web.get("common_text") or ""))
    fixture = html.escape(str(web.get("fixture") or ""))
    return (
        '<section class="voice-benchmark" data-tts-benchmark="v1">'
        '<h3>Voice Bake-off</h3>'
        '<p>Mismo texto, métricas técnicas medidas y evaluación perceptual separada. Ningún score automático decide naturalidad.</p>'
        f'<details><summary>Texto común · {fixture}</summary><div class="voice-benchmark-text">{common_text}</div></details>'
        + ('<div class="voice-benchmark-grid">' + ''.join(cards) + '</div>' if cards else '<div class="voice-empty">Sin candidatos publicados.</div>')
        + '</section>'
    )

def apply_voice_panel(document: str, *, episode_dir: Path) -> str:
    if 'data-tts-panel="v1"' in document:
        return document
    script_node = '<div id="scriptText" class="script" data-search-script>'
    if script_node not in document:
        raise RuntimeError("Review Hub v15 could not find Script node")
    document = document.replace(
        script_node,
        _voice_markup(episode_dir) + _benchmark_markup(episode_dir) + script_node,
        1,
    )
    return document.replace('</style>', VOICE_CSS + '\n</style>', 1)


def build_site(
    *, episode_dir: Path, media_dir: Path, media_zip: Path, regression_path: Path,
    cases_path: Path, output_dir: Path, run_id: str, pricing_path: Path | None = None
) -> Path:
    index_path = _build_site_v14(
        episode_dir=episode_dir, media_dir=media_dir, media_zip=media_zip,
        regression_path=regression_path, cases_path=cases_path,
        output_dir=output_dir, run_id=run_id, pricing_path=pricing_path,
    )
    document = index_path.read_text(encoding="utf-8")
    document = apply_voice_panel(document, episode_dir=episode_dir)
    index_path.write_text(document, encoding="utf-8")
    return index_path


def main() -> None:
    args = parse_args()
    result = build_site(
        episode_dir=Path(args.episode_dir), media_dir=Path(args.media_dir),
        media_zip=Path(args.media_zip), regression_path=Path(args.regression),
        cases_path=Path(args.cases), output_dir=Path(args.output_dir), run_id=str(args.run_id)
    )
    print(result)


if __name__ == "__main__":
    main()
