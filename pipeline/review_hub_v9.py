from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v8 import (
    _artifact_map,
    _cost_section,
    _gate_block,
    _run_kpis,
    _state_machine,
    _workflow_lanes,
    build_site as _build_site_v8,
)


def _stage(number: int, kind: str, title: str, summary: str, inputs: str, outputs: str, authority: str, code: str) -> str:
    return (
        '<article class="e2e-stage" data-search-item>'
        '<div class="e2e-stage-rail"><span class="e2e-stage-number">'
        f'{number:02d}</span><span class="e2e-stage-line"></span></div>'
        '<div class="e2e-stage-body">'
        f'<div class="e2e-stage-head"><span class="e2e-kind {kind}">{kind}</span><h3>{title}</h3></div>'
        f'<p class="e2e-stage-summary">{summary}</p>'
        '<div class="e2e-stage-grid">'
        f'<div><span>Entrada</span><p>{inputs}</p></div>'
        f'<div><span>Salida</span><p>{outputs}</p></div>'
        f'<div><span>Quién manda</span><p>{authority}</p></div>'
        f'<div><span>Código principal</span><p><code>{code}</code></p></div>'
        '</div></div></article>'
    )


def _timeline() -> str:
    stages = [
        ("deterministic", "Disparo y contrato de ejecución", "GitHub Actions arranca en calendario o manualmente y resuelve fecha, ventana, límites y flags de promoción.", "schedule / workflow_dispatch + variables", "target_date + opciones de runtime", "GitHub Actions", ".github/workflows/build-video-kit.yml"),
        ("deterministic", "Workspace aislado", "Cada intento vive fuera de las carpetas canónicas para que un fallo parcial jamás pise un episodio bueno.", "target_date + github.run_id", ".pipeline-runs/<date>/<run-id>/", "Shell/Python", ".github/workflows/build-video-kit.yml"),
        ("deterministic", "Ingesta y ventana editorial", "Se leen noticias estructuradas, se toleran días faltantes y se corta temprano si no hay fuentes utilizables.", "news/YYYY-MM-DD.txt", "NewsItem[] + fechas faltantes", "Python", "pipeline/news.py · pipeline/run.py"),
        ("deterministic", "Memoria aprobada", "Solo episodios aprobados alimentan memoria de historias y ensayos previos; así se evita quemar contenido de runs fallidos.", "scripts/ históricos aprobados", "previous_selected_news + previous_essays", "Python", "pipeline/run.py"),
        ("agent", "Selector editorial", "Reduce ruido y devuelve referencias a historias reales con valor humano/editorial; no reescribe libremente el corpus.", "noticias + historial", "selected_news.json", "Agente propone; Python valida IDs, duplicados y máximo", "app/agent.py → news_relevance_selector"),
        ("agent", "Director editorial + Claim Ledger", "Diseña pregunta central, tesis, lente, evidencia y beats. Antes de existir prosa crea un Claim Ledger que separa hechos soportados, interpretaciones permitidas, hipótesis, incertidumbres, claims prohibidos y limitaciones de fuente.", "selected_news + perfiles + memoria", "episode_plan.json con evidence + claim_ledger + beats", "Agente diseña; Pydantic y Python validan cobertura 1:1 entre evidencia y ledger", "app/agent.py → editorial_director · pipeline/run.py"),
        ("gate", "Gate de novedad", "El plan se compara contra ensayos aprobados recientes. Si se parece demasiado, se replantea de forma acotada; si sigue duplicado, el run termina sin publicar.", "episode_plan + previous_essays", "novelty_check.json + plan aceptado o no_novel_essay_angle", "Python", "pipeline/core.py · pipeline/run.py"),
        ("agent", "Writer con frontera factual", "Escribe el ensayo usando evidencia, Claim Ledger, plan y perfiles editoriales. El ledger limita lo que puede elevarse a hecho sin respaldo.", "news_text + selected_news + episode_plan + perfiles", "draft_script + secciones alineadas", "Agente redacta; parser determinista valida estructura", "app/agent.py → essay_script_writer"),
        ("judges", "Cuatro jueces independientes", "Editorial/factualidad, SEO, atención y voz/humanidad evalúan el mismo candidato desde responsabilidades distintas.", "script + fuentes + Claim Ledger + perfiles", "4 revisiones estructuradas", "Agentes juzgan; ninguno puede publicar", "script_critic · seo_master · youtube_attention_master · voice_humanity_critic"),
        ("gate", "Gate determinista de calidad", "Duración, scores, factualidad, AI-smell y aprobaciones se combinan como restricciones. Un promedio alto no compensa fallar un requisito crítico.", "script + cuatro reviews", "checks + approved/rejected", "Python", "pipeline/core.py → evaluate_script_gate"),
        ("agent", "Routing de refinamiento aislado", "Si el gate falla, Python elige exactamente una fase: factual primero, voz después y SEO/atención al final. Cada refiner recibe un payload distinto para impedir que una reparación reabra otro problema.", "gate + candidato + feedback permitido para la fase", "nuevo candidato o fin del loop", "Python selecciona fase; el agente solo repara su dimensión", "pipeline/run.py → _select_refinement_phase · app/refiners.py"),
        ("agent", "Factual repair", "Se usa si falla aprobación editorial, score editorial o factuality_low. Tiene acceso a fuentes y Claim Ledger, pero no a feedback de voz/SEO/atención.", "script + factual review + selected_news + news_text + ledger", "draft corregido factual", "factual_script_refiner", "app/refiners.py → factual_script_refiner"),
        ("agent", "Voice repair", "Solo puede ejecutarse cuando factualidad ya pasó. No recibe corpus fuente ni review factual y trabaja con la semántica de claims congelada.", "script + voice review + episode_plan + voice_profile", "draft corregido de voz", "voice_script_refiner", "app/refiners.py → voice_script_refiner"),
        ("agent", "Secondary polish", "Solo aparece después de pasar factualidad y voz. Hace la mínima reparación restante de SEO, atención, pacing o duración sin cambiar claims.", "script + SEO/attention review + plan", "draft pulido", "secondary_script_refiner", "app/refiners.py → secondary_script_refiner"),
        ("agent", "Plan multimedia", "Una vez aprobado el guion, el editor decide qué slots necesitan apoyo visual externo y cuáles quedan como presentador.", "script final + plan + timeline + cap", "multimedia/plan.json", "Agente propone; Python normaliza, deduplica y limita", "app/agent.py → multimedia_editor_master"),
        ("service", "Materialización de medios", "Proveedores externos usan retries acotados; fallos pueden caer a tarjetas locales. Manifest y créditos preservan trazabilidad.", "queries aprobadas", "assets + manifest.json + credits", "Python", "pipeline/media.py · pipeline/credits.py"),
        ("deterministic", "Estado, trazas, reporte y promoción", "Se persisten estado, llamadas, iteraciones, hashes y métricas. Solo approved puede reemplazar scripts/ y multimedia/ canónicos.", "artefactos + gate final", "run_state.json + execution_trace.json + run_report.json", "Python/GitHub Actions", "pipeline/report.py · build-video-kit.yml"),
        ("pages", "Regression → Review Hub → GitHub Pages", "La regresión genera un artefacto aislado; el Review Hub reconcilia evidencia, crea media de revisión, calcula costos, arma catálogo multi-episodio y despliega Pages.", "editorial-regression artifact + pricing + media", "review-site + cost_snapshot.json + pages-site", "Workflows deterministas", "editorial-regression.yml · editorial-review-hub.yml"),
    ]
    return '<div class="e2e-timeline">' + ''.join(_stage(i, *stage) for i, stage in enumerate(stages, 1)) + '</div>'


def _agent_table() -> str:
    rows = [
        ("news_relevance_selector", "Selección", "Historias con valor editorial"),
        ("editorial_director", "Arquitectura", "Pregunta, tesis, evidencia, Claim Ledger y beats"),
        ("essay_script_writer", "Generación", "Ensayo completo dentro de la frontera factual"),
        ("script_critic", "Juez", "Factualidad y rigor intelectual"),
        ("seo_master", "Juez", "Descubribilidad"),
        ("youtube_attention_master", "Juez", "Atención, ritmo y progresión"),
        ("voice_humanity_critic", "Juez", "Voz, humanidad, profundidad y AI-smell"),
        ("multimedia_editor_master", "Multimedia", "Slots que realmente necesitan apoyo visual"),
        ("factual_script_refiner", "Refiner aislado", "Repara hechos/traceabilidad con acceso a fuentes"),
        ("voice_script_refiner", "Refiner aislado", "Repara voz sin acceso al corpus fuente"),
        ("secondary_script_refiner", "Refiner aislado", "Repara SEO/atención al final, con claims congelados"),
    ]
    body = ''.join(
        f'<tr data-search-item><td><code>{name}</code></td><td>{role}</td><td>{decision}</td></tr>'
        for name, role, decision in rows
    )
    return (
        '<div class="e2e-table-wrap"><table class="e2e-table"><thead><tr>'
        '<th>Agente</th><th>Rol</th><th>Responsabilidad</th></tr></thead><tbody>' + body + '</tbody></table></div>'
    )


def _claim_ledger() -> str:
    fields = [
        ("supported_facts", "Afirmaciones que la evidencia sí permite tratar como hechos."),
        ("allowed_interpretations", "Lecturas razonables que deben mantenerse como interpretación."),
        ("hypotheses", "Explicaciones posibles que nunca deben presentarse como verificadas."),
        ("uncertainties", "Lo que sigue abierto o no puede saberse con las fuentes disponibles."),
        ("prohibited_claims", "Saltos que el writer/refiner no puede introducir."),
        ("source_limitations", "Limitaciones de cobertura, independencia o calidad de la fuente."),
    ]
    cards = ''.join(
        f'<article class="e2e-check" data-search-item><span><code>{field}</code></span><p>{text}</p></article>'
        for field, text in fields
    )
    return '<div class="e2e-check-grid">' + cards + '</div>'


def _refinement_routing() -> str:
    return (
        '<div class="e2e-lanes">'
        '<article class="e2e-lane" data-search-item><span class="eyebrow">1 · Prioridad factual</span><h3>factual_script_refiner</h3><p>Se ejecuta primero cuando falla factualidad/editorial. Ve fuentes y Claim Ledger; no ve feedback de estilo.</p><div class="e2e-chain">factual fail → factual repair → rejudge</div></article>'
        '<article class="e2e-lane" data-search-item><span class="eyebrow">2 · Prioridad de voz</span><h3>voice_script_refiner</h3><p>Solo entra cuando factualidad ya pasó. No recibe el corpus fuente; la semántica factual queda congelada.</p><div class="e2e-chain">factual pass + voice fail → voice repair → rejudge</div></article>'
        '<article class="e2e-lane" data-search-item><span class="eyebrow">3 · Pulido secundario</span><h3>secondary_script_refiner</h3><p>Solo corrige SEO, atención, pacing o duración después de pasar factualidad y voz.</p><div class="e2e-chain">factual pass + voice pass + secondary fail → polish → rejudge</div></article>'
        '</div>'
    )


def _design_decisions() -> str:
    items = [
        ("Claim Ledger antes de la prosa", "Reduce la probabilidad de que marketing, inferencias o hipótesis se conviertan silenciosamente en hechos durante la redacción."),
        ("Cuatro jueces en vez de uno", "Hace visibles los trade-offs y evita que un score promedio esconda factualidad débil o una voz artificial."),
        ("Tres refiners con contextos distintos", "Separa físicamente responsabilidades: corregir hechos no debe optimizar estilo, y corregir voz no debe reabrir claims."),
        ("Sin LoopAgent como autoridad", "El modelo no controla el loop. Python decide fase, máximo de iteraciones, anti-repeat y cuándo parar."),
        ("Promoción fail-closed", "Un run incompleto puede preservar artefactos para diagnóstico, pero jamás reemplaza el episodio canónico salvo que termine approved."),
        ("Identidad editorial versionada", "Voice/discourse profiles sobreviven a cambios de modelo y prompt, haciendo que la identidad sea dato y no prompt glue."),
    ]
    return '<div class="e2e-note-grid">' + ''.join(
        f'<article data-search-item><h3>{title}</h3><p>{text}</p></article>' for title, text in items
    ) + '</div>'


def process_panel(snapshot: dict[str, Any]) -> str:
    return (
        '<section id="e2e-process" class="e2e-process-section" data-search-group aria-labelledby="e2e-title">'
        '<header class="e2e-hero"><span class="eyebrow">Arquitectura explicada de punta a punta</span>'
        '<h2 id="e2e-title">Cómo se fabrica un episodio, de una noticia a GitHub Pages</h2>'
        '<p><strong>Los agentes hacen trabajo probabilístico; Python y GitHub Actions conservan la autoridad.</strong> '
        'La arquitectura actual añade una frontera factual previa a la escritura y separa físicamente los tres tipos de refinamiento.</p></header>'
        + _run_kpis(snapshot)
        + '<nav class="e2e-toc" aria-label="Índice del proceso">'
        '<a href="#e2e-principle">Modelo mental</a><a href="#e2e-map">Pipeline</a><a href="#e2e-ledger">Claim Ledger</a>'
        '<a href="#e2e-agents">Agentes</a><a href="#e2e-refinement">Refinamiento</a><a href="#e2e-gates">Gates</a>'
        '<a href="#e2e-costs">Costos</a><a href="#e2e-artifacts">Artefactos</a><a href="#e2e-actions">Actions</a><a href="#e2e-why">Diseño</a></nav>'
        '<section id="e2e-principle" class="e2e-chapter"><span class="eyebrow">01 · Modelo mental</span><h2>Probabilidad dentro de control determinista</h2>'
        '<div class="e2e-two-layers"><article><span class="e2e-kind agent">agent</span><h3>Capa probabilística</h3><p>Selecciona, estructura, escribe, juzga, repara una dimensión concreta y propone visuales.</p></article>'
        '<article><span class="e2e-kind deterministic">deterministic</span><h3>Capa de control</h3><p>Valida, decide routing, limita loops, calcula gates, persiste estado, promueve archivos y despliega.</p></article></div>'
        '<p class="e2e-callout"><strong>Regla:</strong> ningún LLM decide si su propio resultado es publicable.</p></section>'
        '<section id="e2e-map" class="e2e-chapter"><span class="eyebrow">02 · Pipeline</span><h2>El recorrido completo actual</h2>' + _timeline() + '</section>'
        '<section id="e2e-ledger" class="e2e-chapter"><span class="eyebrow">03 · Claim Ledger</span><h2>La frontera factual existe antes de escribir</h2>'
        '<p class="e2e-intro">Cada evidencia planificada tiene exactamente una entrada del ledger con el mismo evidence_id y selected_news_index. El runtime falla cerrado si falta cobertura, hay IDs duplicados o no existen supported_facts.</p>' + _claim_ledger() + '</section>'
        '<section id="e2e-agents" class="e2e-chapter"><span class="eyebrow">04 · Agentes</span><h2>11 responsabilidades, ninguna autoridad de publicación</h2>' + _agent_table() + '</section>'
        '<section id="e2e-refinement" class="e2e-chapter"><span class="eyebrow">05 · Refinamiento</span><h2>Factual → voz → secundario</h2>'
        '<p class="e2e-intro">La fase no la elige otro agente: <code>pipeline.run._select_refinement_phase</code> decide determinísticamente qué reparación está permitida a continuación.</p>' + _refinement_routing() + '</section>'
        '<section id="e2e-gates" class="e2e-chapter"><span class="eyebrow">06 · Quality gates</span><h2>La aprobación es una conjunción de restricciones</h2>' + _gate_block() + '<h3 class="e2e-subheading">Estados finales posibles</h3>' + _state_machine() + '</section>'
        '<section id="e2e-costs" class="e2e-chapter"><span class="eyebrow">07 · FinOps</span><h2>Costos observados del episodio mostrado</h2>' + _cost_section(snapshot) + '</section>'
        '<section id="e2e-artifacts" class="e2e-chapter"><span class="eyebrow">08 · Artefactos</span><h2>La memoria auditable del run</h2>' + _artifact_map() + '</section>'
        '<section id="e2e-actions" class="e2e-chapter"><span class="eyebrow">09 · GitHub Actions</span><h2>Producción, evaluación y observabilidad separadas</h2>' + _workflow_lanes() + '</section>'
        '<section id="e2e-why" class="e2e-chapter"><span class="eyebrow">10 · Decisiones de diseño</span><h2>Por qué el sistema está construido así</h2>' + _design_decisions() + '</section>'
        '<div class="e2e-final"><span class="eyebrow">La idea que debes recordar</span><h2>Agentic no significa autónomo sin control</h2><p>La IA decide semántica dentro de contratos; el software tradicional decide estado, permisos, límites y publicación.</p></div>'
        '</section>'
    )


def apply_current_architecture(document: str, snapshot: dict[str, Any]) -> str:
    start = document.find('<div id="panel-process"')
    if start < 0:
        raise RuntimeError("Review Hub v9 could not find Process panel")
    opening_end = document.find('>', start)
    if opening_end < 0:
        raise RuntimeError("Review Hub v9 could not parse Process panel")
    next_panel = document.find('<div id="panel-', opening_end + 1)
    if next_panel < 0:
        raise RuntimeError("Review Hub v9 could not find the next panel")
    opening = document[start:opening_end + 1]
    return document[:start] + opening + process_panel(snapshot) + '</div>\n' + document[next_panel:]


def build_site(*, episode_dir: Path, media_dir: Path, media_zip: Path, regression_path: Path, cases_path: Path, output_dir: Path, run_id: str, pricing_path: Path | None = None) -> Path:
    index_path = _build_site_v8(
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
    document = apply_current_architecture(index_path.read_text(encoding='utf-8'), snapshot)
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
