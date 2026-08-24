from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v10 import build_site as _build_site_v10, process_panel as _architecture_panel
from pipeline.run_journey import derive_run_journey


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "—"))


def _integer(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "—"


def _seconds(value: Any) -> str:
    try:
        return f"{float(value or 0):,.1f}s"
    except (TypeError, ValueError):
        return "—"


def _usd(value: Any) -> str:
    try:
        return f"${float(value or 0):,.4f}"
    except (TypeError, ValueError):
        return "—"


def _status_label(status: str) -> tuple[str, str]:
    labels = {
        "executed": ("EJECUTADO", "ok"),
        "inferred": ("EJECUTADO · INFERIDO", "ok"),
        "not_required": ("NO REQUERIDO", "neutral"),
        "not_reached": ("NO ALCANZADO", "neutral"),
        "not_observed": ("NO OBSERVADO", "neutral"),
        "terminal": ("TERMINAL", "bad"),
        "error": ("ERROR", "bad"),
        "current_view": ("VISTA ACTUAL", "ok"),
    }
    return labels.get(status, (status.upper() or "—", "neutral"))


def _summary(journey: dict[str, Any]) -> str:
    status = str(journey.get("status") or "unknown")
    publishable = bool(journey.get("publishable"))
    state_class = "ok" if publishable else "bad" if status not in {"unknown", ""} else "neutral"
    reason = str(journey.get("reason") or "Sin reason persistido")
    similarity = journey.get("nearest_similarity")
    if similarity is None:
        similarity_text = "—"
    else:
        try:
            similarity_text = f"{float(similarity):.3f}"
        except (TypeError, ValueError):
            similarity_text = "—"
    return (
        '<div class="run-journey-summary" data-search-item>'
        '<div><span class="eyebrow">Resultado autoritativo</span>'
        f'<h3><span class="badge {state_class}">{_esc(status)}</span></h3><p>{_esc(reason)}</p></div>'
        '<div class="run-journey-kpis">'
        f'<span><strong>{_integer(journey.get("selected_news_count"))}</strong><small>noticias seleccionadas</small></span>'
        f'<span><strong>{_integer(journey.get("novelty_attempts"))}</strong><small>intentos de novedad</small></span>'
        f'<span><strong>{_esc(similarity_text)}</strong><small>similitud final</small></span>'
        f'<span><strong>{_integer(journey.get("refinement_iterations"))}</strong><small>iteraciones juzgadas</small></span>'
        f'<span><strong>{_integer(journey.get("agent_call_attempts"))}</strong><small>attempts de agentes</small></span>'
        '</div></div>'
    )


def _compact_path(journey: dict[str, Any]) -> str:
    stages = journey.get("stages", []) if isinstance(journey, dict) else []
    visible = [
        stage for stage in stages
        if isinstance(stage, dict) and stage.get("status") in {"executed", "inferred", "terminal", "error", "current_view"}
    ]
    nodes = []
    for stage in visible:
        status = str(stage.get("status") or "")
        mark = "✓" if status in {"executed", "inferred", "current_view"} else "×"
        nodes.append(
            '<span class="run-path-node" data-search-item>'
            f'<b>{mark}</b><span>{_esc(stage.get("title"))}</span>'
            f'<small>{_integer(stage.get("attempts"))} calls · {_integer(stage.get("tokens"))} tok · {_usd(stage.get("estimated_cost_usd"))}</small>'
            '</span>'
        )
    return '<div class="run-path-chain">' + '<span class="run-path-arrow">→</span>'.join(nodes) + '</div>'


def _stage_details(journey: dict[str, Any]) -> str:
    cards = []
    for stage in journey.get("stages", []) if isinstance(journey, dict) else []:
        if not isinstance(stage, dict):
            continue
        status = str(stage.get("status") or "not_reached")
        label, klass = _status_label(status)
        cards.append(
            '<article class="run-stage-card" data-search-item>'
            f'<div class="run-stage-top"><span class="badge {klass}">{_esc(label)}</span><code>{_esc(stage.get("id"))}</code></div>'
            f'<h3>{_esc(stage.get("title"))}</h3>'
            '<div class="run-stage-metrics">'
            f'<span><strong>{_integer(stage.get("attempts"))}</strong><small>attempts</small></span>'
            f'<span><strong>{_integer(stage.get("errors"))}</strong><small>errores</small></span>'
            f'<span><strong>{_integer(stage.get("tokens"))}</strong><small>tokens</small></span>'
            f'<span><strong>{_seconds(stage.get("elapsed_seconds"))}</strong><small>tiempo</small></span>'
            f'<span><strong>{_usd(stage.get("estimated_cost_usd"))}</strong><small>costo</small></span>'
            '</div></article>'
        )
    return '<div class="run-stage-grid">' + ''.join(cards) + '</div>'


def _refiner_outcome(journey: dict[str, Any]) -> str:
    wanted = {"factual_refine", "voice_refine", "secondary_refine"}
    stages = [stage for stage in journey.get("stages", []) if isinstance(stage, dict) and stage.get("id") in wanted]
    cards = []
    for stage in stages:
        status = str(stage.get("status") or "not_reached")
        label, klass = _status_label(status)
        cards.append(
            '<article class="e2e-lane" data-search-item>'
            f'<span class="badge {klass}">{_esc(label)}</span><h3>{_esc(stage.get("title"))}</h3>'
            f'<p>{_integer(stage.get("attempts"))} attempts · {_integer(stage.get("tokens"))} tokens · {_seconds(stage.get("elapsed_seconds"))} · {_usd(stage.get("estimated_cost_usd"))}</p>'
            '</article>'
        )
    return '<div class="e2e-lanes">' + ''.join(cards) + '</div>'


def run_journey_section(journey: dict[str, Any]) -> str:
    return (
        '<section id="e2e-live-run" class="e2e-chapter run-journey" data-search-group>'
        '<span class="eyebrow">Run real · observabilidad</span><h2>Qué camino tomó este episodio</h2>'
        '<p class="e2e-intro">Esta sección no describe el pipeline teórico: se reconstruye desde <code>run_state.json</code>, <code>execution_trace.json</code>, <code>novelty_check.json</code>, <code>reviews.json</code> y el snapshot de costos del episodio que estás viendo.</p>'
        + _summary(journey)
        + '<h3 class="e2e-subheading">Camino observado</h3>' + _compact_path(journey)
        + '<h3 class="e2e-subheading">Qué refiners fueron realmente necesarios</h3>' + _refiner_outcome(journey)
        + '<h3 class="e2e-subheading">Detalle etapa por etapa</h3>' + _stage_details(journey)
        + '</section>'
    )


RUN_JOURNEY_CSS = r"""
/* v11: observed-run overlay on top of living architecture. */
.run-journey{border-top:1px solid var(--line);margin-top:10px;padding-top:34px}.run-journey-summary{display:grid;grid-template-columns:minmax(260px,.8fr) 1.4fr;gap:14px;border:1px solid var(--line);border-radius:16px;background:var(--panel);padding:17px}.run-journey-summary h3{margin:7px 0}.run-journey-summary p{margin:0;color:var(--muted);line-height:1.45}.run-journey-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px}.run-journey-kpis span,.run-stage-metrics span{display:grid;gap:3px;border:1px solid #29394d;border-radius:11px;padding:9px;background:#111a25}.run-journey-kpis strong,.run-stage-metrics strong{font-size:15px}.run-journey-kpis small,.run-stage-metrics small{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.05em}.run-path-chain{display:flex;align-items:stretch;gap:7px;overflow-x:auto;padding:6px 1px 14px}.run-path-node{display:grid;align-content:start;min-width:170px;max-width:210px;border:1px solid var(--line);border-radius:13px;background:#121b27;padding:11px}.run-path-node>b{font-size:17px}.run-path-node>span{font-weight:800;font-size:12px;margin:5px 0}.run-path-node>small{color:var(--muted);line-height:1.35}.run-path-arrow{display:grid;place-items:center;color:#55718d;font-size:18px}.run-stage-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.run-stage-card{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:13px}.run-stage-card h3{font-size:14px;margin:9px 0}.run-stage-top{display:flex;justify-content:space-between;gap:8px;align-items:center}.run-stage-top code{color:var(--muted);font-size:10px}.run-stage-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:5px}.run-stage-metrics span{padding:7px}.run-stage-metrics strong{font-size:12px}@media(max-width:900px){.run-journey-summary{grid-template-columns:1fr}.run-journey-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.run-stage-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:620px){.run-journey-kpis,.run-stage-grid{grid-template-columns:1fr}.run-stage-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""


def _inject_journey(panel: str, journey: dict[str, Any]) -> str:
    nav = '<nav class="e2e-toc"'
    at = panel.find(nav)
    if at < 0:
        raise RuntimeError("Review Hub v11 could not find E2E table of contents")
    enriched_nav = panel[:at] + run_journey_section(journey) + panel[at:]
    enriched_nav = enriched_nav.replace(
        '<nav class="e2e-toc" aria-label="Índice del proceso">',
        '<nav class="e2e-toc" aria-label="Índice del proceso"><a href="#e2e-live-run">Run real</a>',
        1,
    )
    return enriched_nav


def _replace_process_panel(document: str, panel: str) -> str:
    start = document.find('<div id="panel-process"')
    if start < 0:
        raise RuntimeError("Review Hub v11 could not find Process panel")
    opening_end = document.find('>', start)
    next_panel = document.find('<div id="panel-', opening_end + 1)
    if opening_end < 0 or next_panel < 0:
        raise RuntimeError("Review Hub v11 could not parse Process panel")
    opening = document[start:opening_end + 1]
    return document[:start] + opening + panel + '</div>\n' + document[next_panel:]


def build_site(*, episode_dir: Path, media_dir: Path, media_zip: Path, regression_path: Path, cases_path: Path, output_dir: Path, run_id: str, pricing_path: Path | None = None) -> Path:
    index_path = _build_site_v10(
        episode_dir=episode_dir,
        media_dir=media_dir,
        media_zip=media_zip,
        regression_path=regression_path,
        cases_path=cases_path,
        output_dir=output_dir,
        run_id=run_id,
        pricing_path=pricing_path,
    )
    snapshot_path = output_dir / 'downloads' / 'cost_snapshot.json'
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        snapshot = {}
    journey = derive_run_journey(episode_dir=episode_dir, media_dir=media_dir, cost_snapshot=snapshot)
    panel = _inject_journey(_architecture_panel(snapshot), journey)
    document = index_path.read_text(encoding='utf-8')
    document = document.replace('</style>', RUN_JOURNEY_CSS + '\n</style>', 1)
    document = _replace_process_panel(document, panel)
    index_path.write_text(document, encoding='utf-8')
    return index_path


def main() -> None:
    args = parse_args()
    result = build_site(
        episode_dir=Path(args.episode_dir),
        media_dir=Path(args.media_dir),
        media_zip=Path(args.media_zip),
        regression_path=Path(args.regression),
        cases_path=Path(args.cases),
        output_dir=Path(args.output_dir),
        run_id=str(args.run_id),
    )
    print(result)


if __name__ == '__main__':
    main()
