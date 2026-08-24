from __future__ import annotations

import html
import json
from importlib import import_module
from pathlib import Path
from typing import Any

from pipeline.architecture_manifest import manifest
from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v8 import (
    _artifact_map,
    _cost_section,
    _gate_block,
    _run_kpis,
    _state_machine,
    _workflow_lanes,
)
from pipeline.review_hub_v9 import build_site as _build_site_v9


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "—"))


def validate_manifest_runtime(data: dict[str, Any] | None = None) -> list[str]:
    data = data or manifest()
    errors: list[str] = []
    seen_names: set[str] = set()
    for agent in data.get("agents", []):
        name = str(agent.get("name") or "")
        module_name = str(agent.get("module") or "")
        symbol = str(agent.get("symbol") or "")
        if not name or name in seen_names:
            errors.append(f"invalid or duplicate agent name: {name!r}")
        seen_names.add(name)
        try:
            module = import_module(module_name)
        except Exception as exc:
            errors.append(f"could not import {module_name}: {type(exc).__name__}: {exc}")
            continue
        if not hasattr(module, symbol):
            errors.append(f"{module_name}.{symbol} does not exist for architecture agent {name}")

    stage_ids = [str(item.get("id") or "") for item in data.get("stages", [])]
    if not stage_ids or len(stage_ids) != len(set(stage_ids)):
        errors.append("stage ids must be non-empty and unique")

    known_steps = {
        step
        for item in data.get("stages", [])
        for step in item.get("trace_steps", [])
        if isinstance(step, str) and step
    }
    for phase in data.get("refinement_phases", []):
        step = str(phase.get("trace_step") or "")
        if step not in known_steps:
            errors.append(f"refinement trace step {step!r} is not mapped to any stage")
    return errors


def _stage_card(number: int, stage: dict[str, Any]) -> str:
    kind = _esc(stage.get("kind"))
    trace_steps = stage.get("trace_steps", [])
    trace_note = " · ".join(str(value) for value in trace_steps) if trace_steps else "—"
    return (
        '<article class="e2e-stage" data-search-item>'
        f'<div class="e2e-stage-rail"><span class="e2e-stage-number">{number:02d}</span><span class="e2e-stage-line"></span></div>'
        '<div class="e2e-stage-body">'
        f'<div class="e2e-stage-head"><span class="e2e-kind {kind}">{kind}</span><h3>{_esc(stage.get("title"))}</h3></div>'
        f'<p class="e2e-stage-summary">{_esc(stage.get("summary"))}</p>'
        '<div class="e2e-stage-grid">'
        f'<div><span>Entrada</span><p>{_esc(stage.get("inputs"))}</p></div>'
        f'<div><span>Salida</span><p>{_esc(stage.get("outputs"))}</p></div>'
        f'<div><span>Quién manda</span><p>{_esc(stage.get("authority"))}</p></div>'
        f'<div><span>Trace steps</span><p><code>{_esc(trace_note)}</code></p></div>'
        f'<div><span>Código principal</span><p><code>{_esc(stage.get("code"))}</code></p></div>'
        '</div></div></article>'
    )


def _timeline(data: dict[str, Any]) -> str:
    return '<div class="e2e-timeline">' + ''.join(
        _stage_card(index, stage) for index, stage in enumerate(data.get("stages", []), 1)
    ) + '</div>'


def _agent_table(data: dict[str, Any]) -> str:
    body = ''.join(
        '<tr data-search-item>'
        f'<td><code>{_esc(agent.get("name"))}</code></td>'
        f'<td>{_esc(agent.get("role"))}</td>'
        f'<td>{_esc(agent.get("responsibility"))}</td>'
        f'<td><code>{_esc(agent.get("module"))}.{_esc(agent.get("symbol"))}</code></td>'
        '</tr>'
        for agent in data.get("agents", [])
    )
    return (
        '<div class="e2e-table-wrap"><table class="e2e-table"><thead><tr>'
        '<th>Agente</th><th>Rol</th><th>Responsabilidad</th><th>Runtime symbol</th>'
        '</tr></thead><tbody>' + body + '</tbody></table></div>'
    )


def _claim_ledger(data: dict[str, Any]) -> str:
    return '<div class="e2e-check-grid">' + ''.join(
        f'<article class="e2e-check" data-search-item><span><code>{_esc(field)}</code></span><p>{_esc(description)}</p></article>'
        for field, description in data.get("claim_ledger_fields", [])
    ) + '</div>'


def _refinement(data: dict[str, Any]) -> str:
    return '<div class="e2e-lanes">' + ''.join(
        '<article class="e2e-lane" data-search-item>'
        f'<span class="eyebrow">Fase {_esc(phase.get("id"))}</span>'
        f'<h3>{_esc(phase.get("agent"))}</h3>'
        f'<p><strong>Cuándo:</strong> {_esc(phase.get("condition"))}</p>'
        f'<p><strong>Contexto:</strong> {_esc(phase.get("context"))}</p>'
        f'<div class="e2e-chain">trace: {_esc(phase.get("trace_step"))} → rejudge</div>'
        '</article>'
        for phase in data.get("refinement_phases", [])
    ) + '</div>'


def _decision_flow(data: dict[str, Any]) -> str:
    return '<div class="e2e-note-grid">' + ''.join(
        f'<article data-search-item><h3>{index:02d}</h3><p>{_esc(item)}</p></article>'
        for index, item in enumerate(data.get("decision_flow", []), 1)
    ) + '</div>'


def _design_decisions(data: dict[str, Any]) -> str:
    return '<div class="e2e-note-grid">' + ''.join(
        f'<article data-search-item><h3>{_esc(title)}</h3><p>{_esc(description)}</p></article>'
        for title, description in data.get("design_decisions", [])
    ) + '</div>'


def process_panel(snapshot: dict[str, Any], data: dict[str, Any] | None = None) -> str:
    data = data or manifest()
    errors = validate_manifest_runtime(data)
    if errors:
        raise RuntimeError("Architecture manifest drift: " + "; ".join(errors))
    version = data.get("version", "—")
    return (
        '<section id="e2e-process" class="e2e-process-section" data-search-group aria-labelledby="e2e-title">'
        '<header class="e2e-hero"><span class="eyebrow">Living architecture · source-backed</span>'
        '<h2 id="e2e-title">Cómo se fabrica un episodio, de una noticia a GitHub Pages</h2>'
        f'<p>Esta vista se renderiza desde <code>pipeline/architecture_manifest.py</code> (schema v{_esc(version)}). '
        '<strong>Si un agente o etapa deja de existir en runtime, CI debe fallar antes de que Pages publique documentación falsa.</strong></p></header>'
        + _run_kpis(snapshot)
        + '<nav class="e2e-toc" aria-label="Índice del proceso">'
        '<a href="#e2e-map">Pipeline</a><a href="#e2e-ledger">Claim Ledger</a><a href="#e2e-agents">Agentes</a>'
        '<a href="#e2e-decisions">Decisiones</a><a href="#e2e-refinement">Refinamiento</a><a href="#e2e-gates">Gates</a>'
        '<a href="#e2e-costs">Costos</a><a href="#e2e-artifacts">Artefactos</a><a href="#e2e-actions">Actions</a><a href="#e2e-why">Diseño</a></nav>'
        '<section id="e2e-map" class="e2e-chapter"><span class="eyebrow">01 · Pipeline</span><h2>Arquitectura declarada y verificable</h2>' + _timeline(data) + '</section>'
        '<section id="e2e-ledger" class="e2e-chapter"><span class="eyebrow">02 · Claim Ledger</span><h2>La frontera factual antes de la prosa</h2>' + _claim_ledger(data) + '</section>'
        '<section id="e2e-agents" class="e2e-chapter"><span class="eyebrow">03 · Agentes</span><h2>Inventario conectado al runtime</h2>' + _agent_table(data) + '</section>'
        '<section id="e2e-decisions" class="e2e-chapter"><span class="eyebrow">04 · Mapa de decisiones</span><h2>El sistema no es una línea; es un árbol fail-closed</h2>'
        '<p class="e2e-intro">Estos son los puntos donde el controlador puede terminar, reparar o continuar. Los estados no publicables son resultados válidos del sistema, no excepciones a ocultar.</p>' + _decision_flow(data) + '</section>'
        '<section id="e2e-refinement" class="e2e-chapter"><span class="eyebrow">05 · Refinamiento</span><h2>Routing factual → voz → secundario</h2>' + _refinement(data) + '</section>'
        '<section id="e2e-gates" class="e2e-chapter"><span class="eyebrow">06 · Quality gates</span><h2>Aprobación por restricciones</h2>' + _gate_block() + '<h3 class="e2e-subheading">Estados finales</h3>' + _state_machine() + '</section>'
        '<section id="e2e-costs" class="e2e-chapter"><span class="eyebrow">07 · FinOps</span><h2>Costos del episodio mostrado</h2>' + _cost_section(snapshot) + '</section>'
        '<section id="e2e-artifacts" class="e2e-chapter"><span class="eyebrow">08 · Artefactos</span><h2>Memoria auditable</h2>' + _artifact_map() + '</section>'
        '<section id="e2e-actions" class="e2e-chapter"><span class="eyebrow">09 · GitHub Actions</span><h2>Producción, evaluación y observabilidad separadas</h2>' + _workflow_lanes() + '</section>'
        '<section id="e2e-why" class="e2e-chapter"><span class="eyebrow">10 · Decisiones de diseño</span><h2>Por qué está construido así</h2>' + _design_decisions(data) + '</section>'
        '<div class="e2e-final"><span class="eyebrow">Contrato</span><h2>La documentación también debe pasar un gate</h2><p>El manifest conecta nombres humanos, símbolos de runtime y trace steps. Si divergen, CI debe impedir que la explicación quede obsoleta.</p></div>'
        '</section>'
    )


def _replace_process_panel(document: str, panel: str) -> str:
    start = document.find('<div id="panel-process"')
    if start < 0:
        raise RuntimeError("Review Hub v10 could not find Process panel")
    opening_end = document.find('>', start)
    next_panel = document.find('<div id="panel-', opening_end + 1)
    if opening_end < 0 or next_panel < 0:
        raise RuntimeError("Review Hub v10 could not parse Process panel")
    opening = document[start:opening_end + 1]
    return document[:start] + opening + panel + '</div>\n' + document[next_panel:]


def build_site(*, episode_dir: Path, media_dir: Path, media_zip: Path, regression_path: Path, cases_path: Path, output_dir: Path, run_id: str, pricing_path: Path | None = None) -> Path:
    index_path = _build_site_v9(
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
    document = _replace_process_panel(index_path.read_text(encoding='utf-8'), process_panel(snapshot))
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
