from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v7 import build_site as _build_site_v7


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "—"))


def _integer(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "—"


def _usd(value: Any, *, precise: bool = False) -> str:
    try:
        if value is None or value == "":
            return "—"
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if precise or abs(number) < 0.01:
        return f"${number:,.4f}"
    return f"${number:,.2f}"


def _run_kpis(snapshot: dict[str, Any]) -> str:
    usage = snapshot.get("usage", {}) if isinstance(snapshot, dict) else {}
    totals = snapshot.get("totals", {}) if isinstance(snapshot, dict) else {}
    breakdown = snapshot.get("breakdown_by_step", []) if isinstance(snapshot, dict) else []
    attempts = snapshot.get("attempts", []) if isinstance(snapshot, dict) else []
    observed_calls = usage.get("attempts_with_observed_usage")
    if observed_calls is None:
        observed_calls = len(attempts) if isinstance(attempts, list) else 0
    steps = len(breakdown) if isinstance(breakdown, list) else 0
    cards = (
        ("Costo directo conocido", _usd(totals.get("known_direct_cost_usd")), "Del run mostrado en este Review Hub"),
        ("Tokens observados", _integer(usage.get("total_tokens")), "Input + output + reasoning persistido"),
        ("Llamadas con uso", _integer(observed_calls), "Intentos de modelo con telemetría disponible"),
        ("Steps medidos", _integer(steps), "Agregados visibles también en Budget"),
    )
    return '<div class="e2e-kpis">' + "".join(
        '<article class="e2e-kpi" data-search-item>'
        f'<span>{_esc(label)}</span><strong>{_esc(value)}</strong><small>{_esc(note)}</small>'
        '</article>'
        for label, value, note in cards
    ) + '</div>'


def _stage_card(
    number: int,
    *,
    kind: str,
    title: str,
    summary: str,
    inputs: str,
    outputs: str,
    authority: str,
    code: str,
) -> str:
    return (
        '<article class="e2e-stage" data-search-item>'
        '<div class="e2e-stage-rail"><span class="e2e-stage-number">'
        f'{number:02d}</span><span class="e2e-stage-line"></span></div>'
        '<div class="e2e-stage-body">'
        f'<div class="e2e-stage-head"><span class="e2e-kind {html.escape(kind, quote=True)}">{_esc(kind)}</span>'
        f'<h3>{_esc(title)}</h3></div><p class="e2e-stage-summary">{_esc(summary)}</p>'
        '<div class="e2e-stage-grid">'
        f'<div><span>Entrada</span><p>{_esc(inputs)}</p></div>'
        f'<div><span>Salida</span><p>{_esc(outputs)}</p></div>'
        f'<div><span>Quién manda</span><p>{_esc(authority)}</p></div>'
        f'<div><span>Código principal</span><p><code>{_esc(code)}</code></p></div>'
        '</div></div></article>'
    )


def _timeline() -> str:
    stages = [
        dict(kind="deterministic", title="Disparo y contrato de ejecución", summary="GitHub Actions arranca de forma programada martes/viernes o manualmente, resuelve fecha, ventana de noticias, límites y opciones de promoción.", inputs="schedule / workflow_dispatch + variables del repositorio", outputs="target_date, source_mode, lookback, flags y configuración", authority="GitHub Actions; ningún agente decide cuándo correr ni qué run se publica", code=".github/workflows/build-video-kit.yml"),
        dict(kind="deterministic", title="Workspace aislado", summary="Cada intento se construye fuera de las carpetas canónicas. Esto evita que un fallo parcial sobreescriba un episodio bueno.", inputs="target_date + github.run_id", outputs=".pipeline-runs/<date>/<run-id>/scripts y multimedia", authority="Shell/Python determinista", code=".github/workflows/build-video-kit.yml"),
        dict(kind="deterministic", title="Ingesta y ventana editorial", summary="Se leen archivos diarios, se toleran días faltantes y se materializa un catálogo estructurado de noticias. Si toda la ventana está vacía, el episodio termina sin llamar a los agentes de escritura.", inputs="news/YYYY-MM-DD.txt dentro de la ventana editorial", outputs="news_text + catálogo de NewsItem + fechas faltantes", authority="Python valida formato y disponibilidad", code="pipeline/news.py · pipeline/run.py"),
        dict(kind="deterministic", title="Memoria aprobada y contexto", summary="El sistema recupera historias y ensayos previos aprobados para no repetir noticias ni volver a escribir el mismo ensayo con titulares distintos.", inputs="scripts/ históricos aprobados", outputs="previous_selected_news + previous_essays", authority="Python decide qué historial es válido; runs no aprobados no cuentan", code="pipeline/run.py"),
        dict(kind="agent", title="Selector editorial", summary="El primer agente reduce ruido: escoge desarrollos de IA con valor humano/editorial y devuelve referencias a noticias reales, no copias libres del texto fuente.", inputs="noticias actuales + historial de selección", outputs="selected_news.json (máx. 8 historias)", authority="Agente propone; Pydantic + Python validan IDs, duplicados y límites", code="app/agent.py → news_relevance_selector"),
        dict(kind="agent", title="Director editorial", summary="Convierte noticias seleccionadas en un ensayo: pregunta central, tesis, lente narrativo, evidencia, beats, tensión, consecuencias humanas y duración objetivo.", inputs="selected_news + perfiles de voz/discurso + memoria de ensayos", outputs="episode_plan.json", authority="Agente diseña; Python valida referencias y estructura", code="app/agent.py → editorial_director"),
        dict(kind="gate", title="Gate de novedad", summary="El plan se compara contra ensayos aprobados recientes. Si se parece demasiado, el director recibe feedback y replantea de forma acotada; si no encuentra un ángulo nuevo, el run termina como no publicable.", inputs="episode_plan + previous_essays", outputs="novelty_check.json + plan aceptado o no_novel_essay_angle", authority="La similitud, el umbral y el número máximo de replans son deterministas", code="pipeline/core.py · pipeline/run.py"),
        dict(kind="agent", title="Writer", summary="Escribe el ensayo completo en español usando exclusivamente el catálogo, el plan y la identidad editorial versionada. La dramaturgia sirve de estructura interna, no de checklist visible.", inputs="news_text + selected_news + episode_plan + perfiles editoriales", outputs="draft_script + secciones alineadas al plan", authority="Agente redacta; parser determinista exige marcadores y alineación", code="app/agent.py → essay_script_writer"),
        dict(kind="judges", title="Cuatro jueces independientes", summary="Cada candidato pasa por crítica editorial/factual, SEO, atención de YouTube y voz/humanidad. Separar jueces evita que una sola puntuación esconda una debilidad importante.", inputs="script + evidencia + plan + perfiles", outputs="4 revisiones estructuradas con scores, riesgos y feedback", authority="Agentes juzgan dimensiones distintas; no publican", code="script_critic · seo_master · youtube_attention_master · voice_humanity_critic"),
        dict(kind="gate", title="Gate determinista de calidad", summary="Python combina duración, aprobaciones, scores, factualidad y AI-smell. Un promedio alto no compensa fallar un requisito crítico.", inputs="script + cuatro resultados de jueces", outputs="gate aprobado/reprobado + checks exactos", authority="Python es autoridad final", code="pipeline/core.py → evaluate_script_gate"),
        dict(kind="agent", title="Refinamiento acotado", summary="Si el gate falla, un refiner intenta corregir el candidato con el feedback disponible. El controlador evita loops infinitos, hashes repetidos y conserva el mejor candidato observado.", inputs="script + plan + feedback de jueces", outputs="nuevo candidato de script", authority="Agente revisa; Python controla iteraciones, ranking y parada", code="app/agent.py → script_refiner · pipeline/run.py"),
        dict(kind="agent", title="Plan multimedia", summary="Solo después de aprobar el guion, un editor multimedia decide en qué slots una imagen o video realmente agrega contexto o explicación. Lo omitido queda como presentador.", inputs="script final + episode_plan + timeline slots + cap de medios", outputs="multimedia/plan.json", authority="Agente propone slots; Python normaliza, deduplica y aplica el cap", code="app/agent.py → multimedia_editor_master"),
        dict(kind="service", title="Búsqueda y materialización de medios", summary="El pipeline intenta proveedores externos con retries HTTP acotados y puede usar tarjetas locales como fallback. Los créditos y el manifest quedan persistidos.", inputs="queries multimedia aprobadas", outputs="assets + manifest.json + credits", authority="Python controla retries, relevancia, archivos y fallbacks", code="pipeline/media.py · pipeline/credits.py"),
        dict(kind="deterministic", title="Estado, trazas, reporte y promoción", summary="Se escribe el estado autoritativo, la traza de llamadas y un reporte durable. Solo un run approved puede reemplazar scripts/ y multimedia/ canónicos.", inputs="todos los artefactos y resultado del gate", outputs="run_state.json + execution_trace.json + run_report.json + promoción opcional", authority="Python/GitHub Actions; los agentes nunca promueven", code="pipeline/report.py · .github/workflows/build-video-kit.yml"),
        dict(kind="pages", title="Regression → Review Hub → GitHub Pages", summary="Un workflow de regresión ejecuta los agentes sobre una ventana congelada; el Review Hub descarga ese artefacto, reconcilia evidencia, crea multimedia de revisión, calcula costos, arma el catálogo multi-episodio y despliega Pages.", inputs="editorial-regression artifact + episodio + media + pricing snapshot", outputs="review-site + cost_snapshot.json + pages-site + despliegue", authority="Workflows deterministas; la IA puede ayudar a planear media pero el deploy y los smoke tests son código", code="editorial-regression.yml · editorial-review-hub.yml"),
    ]
    return '<div class="e2e-timeline">' + "".join(
        _stage_card(index, **stage) for index, stage in enumerate(stages, start=1)
    ) + '</div>'


def _agent_table() -> str:
    rows = [
        ("news_relevance_selector", "Selección", "Qué historias valen el episodio", "selected_news.json"),
        ("editorial_director", "Arquitectura", "Pregunta, tesis, evidencia, beats y duración", "episode_plan.json"),
        ("essay_script_writer", "Generación", "Redacción del ensayo", "draft_script"),
        ("script_critic", "Juez", "Factualidad, rigor conceptual y calidad editorial", "review"),
        ("seo_master", "Juez", "Descubribilidad sin degradar el contenido", "seo_review"),
        ("youtube_attention_master", "Juez", "Atención ganada, ritmo y progresión", "attention_review"),
        ("voice_humanity_critic", "Juez", "Voz, profundidad, humanidad, analogías y AI-smell", "voice_review"),
        ("script_refiner", "Refinamiento", "Repara el candidato sin saltarse el plan", "nuevo draft_script"),
        ("multimedia_editor_master", "Multimedia", "Dónde conviene usar apoyo visual externo", "multimedia_plan"),
    ]
    body = "".join(
        '<tr data-search-item>'
        f'<td><code>{_esc(name)}</code></td><td>{_esc(role)}</td><td>{_esc(decision)}</td><td>{_esc(output)}</td></tr>'
        for name, role, decision, output in rows
    )
    return (
        '<div class="e2e-table-wrap"><table class="e2e-table"><thead><tr>'
        '<th>Agente</th><th>Rol</th><th>Decisión probabilística</th><th>Salida</th>'
        '</tr></thead><tbody>' + body + '</tbody></table></div>'
    )


def _gate_block() -> str:
    checks = [
        ("Duración", "420–1200 s por defecto", "Evita videos demasiado cortos o inflados artificialmente"),
        ("Editorial", ">= 8.7", "Calidad editorial + factualidad de bajo riesgo"),
        ("SEO", ">= 8.5", "Descubribilidad mínima sin mandar sobre el contenido"),
        ("Atención", ">= 8.5", "Ritmo, revelación progresiva y retención"),
        ("Voz/Humanidad", ">= 8.7", "Voz, profundidad y relevancia humana"),
        ("AI smell", "low", "Evita prosa mecánica o manifiestamente sintética"),
        ("Aprobación", "todos los jueces", "No existe compensación por promedio"),
    ]
    cards = "".join(
        '<article class="e2e-check" data-search-item>'
        f'<span>{_esc(name)}</span><strong>{_esc(value)}</strong><p>{_esc(reason)}</p></article>'
        for name, value, reason in checks
    )
    return '<div class="e2e-check-grid">' + cards + '</div>'


def _state_machine() -> str:
    states = [
        ("approved", "Sí", "Todos los gates pasaron; puede promoverse y usarse como historial aprobado."),
        ("no_source_news", "No", "No hubo noticias utilizables en la ventana."),
        ("no_relevant_news", "No", "El selector no encontró historias publicables."),
        ("no_novel_essay_angle", "No", "El plan siguió demasiado parecido a ensayos recientes."),
        ("script_not_approved", "No", "Se agotó el refinamiento sin pasar todos los gates."),
        ("failure", "No", "Fallo técnico o validación no recuperable."),
        ("missing_openai_secret", "No", "No existe OPENAI_API_KEY para un run que necesita modelo."),
    ]
    return '<div class="e2e-state-grid">' + "".join(
        '<article class="e2e-state" data-search-item>'
        f'<code>{_esc(state)}</code><span class="e2e-publishable">Publicable: {_esc(publishable)}</span><p>{_esc(note)}</p></article>'
        for state, publishable, note in states
    ) + '</div>'


def _cost_section(snapshot: dict[str, Any]) -> str:
    totals = snapshot.get("totals", {}) if isinstance(snapshot, dict) else {}
    usage = snapshot.get("usage", {}) if isinstance(snapshot, dict) else {}
    pricing = snapshot.get("pricing_snapshot", {}) if isinstance(snapshot, dict) else {}
    rate = pricing.get("production_rate", {}) if isinstance(pricing.get("production_rate"), dict) else {}
    services = [
        ("OpenAI API", totals.get("known_openai_cost_usd"), "Variable. Se calcula con tokens persistidos y tarifas versionadas."),
        ("Pexels API", totals.get("pexels_known_cost_usd"), "Actualmente se trata como $0 por request según el snapshot de política; no se persiste el conteo exacto de requests."),
        ("Wikimedia Commons", totals.get("wikimedia_known_cost_usd"), "Community API usada por el pipeline; no se imputa cargo por request."),
        ("Fallback local", totals.get("generated_fallback_known_cost_usd"), "Tarjetas locales generadas sin API externa."),
        ("GitHub Actions compute", totals.get("github_actions_compute_known_cost_usd"), "Para repo público + runner estándar se registra sin cargo de compute según la política modelada."),
        ("Artifact storage", totals.get("artifact_storage_gross_exposure_usd"), "Se muestra como exposición bruta potencial, no como costo directo confirmado."),
    ]
    service_cards = "".join(
        '<article class="e2e-cost-card" data-search-item>'
        f'<span>{_esc(name)}</span><strong>{_esc(_usd(value, precise=True))}</strong><p>{_esc(note)}</p></article>'
        for name, value, note in services
    )
    formula = (
        f"Modelo del snapshot: {_esc(pricing.get('production_model'))}. "
        f"Input: {_usd(rate.get('input_per_million'), precise=True)}/1M · "
        f"Output: {_usd(rate.get('output_per_million'), precise=True)}/1M. "
        f"Tokens observados: {_integer(usage.get('prompt_tokens'))} input + "
        f"{_integer(usage.get('output_tokens'))} output + {_integer(usage.get('reasoning_tokens'))} reasoning."
    )
    return (
        '<p class="e2e-callout"><strong>Regla de lectura:</strong> el costo del hub es un costo conocido reconstruible, no una promesa de factura. '
        'Si una dimensión no está persistida o no tiene una tarifa confiable, se marca como cobertura incompleta en lugar de inventar un cero.</p>'
        f'<p class="e2e-formula">{formula}</p>'
        '<div class="e2e-cost-grid">' + service_cards + '</div>'
        '<p class="e2e-footnote">La pestaña <strong>Budget</strong> contiene el desglose vivo por step y por intento; esta sección explica la lógica del costeo.</p>'
    )


def _artifact_map() -> str:
    rows = [
        ("selected_news.json", "Qué noticias sobrevivieron la selección y por qué", "Selección"),
        ("episode_plan.json", "Pregunta, tesis, evidencia, beats, lente y duración objetivo", "Dirección editorial"),
        ("novelty_check.json", "Comparación contra ensayos recientes y replans", "Novedad"),
        ("script.txt", "Mejor guion candidato finalmente elegido", "Contenido"),
        ("script_sections.json", "Alineación del guion con la arquitectura del episodio", "Trazabilidad"),
        ("reviews.json", "Resultados de jueces, gate, iteraciones y mejor candidato", "Calidad"),
        ("run_state.json", "Estado autoritativo y publishable", "Control"),
        ("execution_trace.json", "Cada intento de agente, tiempo, error/retry y usage disponible", "Observabilidad"),
        ("run_report.json", "Resumen durable, métricas, hashes y configuración", "Auditoría"),
        ("multimedia/plan.json", "Timeline completo: media vs presenter", "Producción"),
        ("multimedia/manifest.json", "Assets realmente materializados y proveedor", "Producción"),
        ("downloads/cost_snapshot.json", "Costos, tarifas, cobertura y desglose por llamada", "FinOps"),
    ]
    return '<div class="e2e-artifacts">' + "".join(
        '<article class="e2e-artifact" data-search-item>'
        f'<code>{_esc(name)}</code><span>{_esc(layer)}</span><p>{_esc(note)}</p></article>'
        for name, note, layer in rows
    ) + '</div>'


def _workflow_lanes() -> str:
    return (
        '<div class="e2e-lanes">'
        '<article class="e2e-lane" data-search-item><span class="eyebrow">Lane A · Producción</span><h3>Build AI News Video Kit</h3>'
        '<p>Corre martes y viernes a las 09:00 de Ciudad de México o manualmente. Valida contratos, construye en aislamiento, crea reporte y solo promueve si <code>run_state=approved</code>.</p>'
        '<div class="e2e-chain">schedule/manual → tests → isolated build → report → approved? → canonical promotion → artifact</div></article>'
        '<article class="e2e-lane" data-search-item><span class="eyebrow">Lane B · Evaluación</span><h3>Editorial Regression</h3>'
        '<p>Ejecuta el runtime sobre una ventana congelada, sin multimedia de producción, y genera un artefacto comparable para revisar cambios editoriales sin mezclar el resultado con publicación.</p>'
        '<div class="e2e-chain">frozen window → agents → structural regression → editorial-regression artifact</div></article>'
        '<article class="e2e-lane" data-search-item><span class="eyebrow">Lane C · Observabilidad</span><h3>Editorial Review Hub / Pages</h3>'
        '<p>Toma el artifact de Regression, reconcilia evidencia, genera medios de revisión, construye el sitio estático, conserva episodios históricos, despliega Pages y ejecuta smoke tests sobre el sitio publicado.</p>'
        '<div class="e2e-chain">regression artifact → reconcile → review media → static hub → catalog → deploy-pages → smoke test</div></article>'
        '</div>'
    )


def process_panel(snapshot: dict[str, Any]) -> str:
    return (
        '<section id="e2e-process" class="e2e-process-section" data-search-group aria-labelledby="e2e-title">'
        '<header class="e2e-hero"><span class="eyebrow">Arquitectura explicada de punta a punta</span>'
        '<h2 id="e2e-title">Cómo se fabrica un episodio, de una noticia a GitHub Pages</h2>'
        '<p>Esta vista separa con claridad lo que hace la IA de lo que decide el software. La regla central del repositorio es simple: '
        '<strong>los agentes proponen, escriben, juzgan y refinan; Python y GitHub Actions controlan estado, límites, retries, publicación y efectos secundarios.</strong></p></header>'
        + _run_kpis(snapshot)
        + '<nav class="e2e-toc" aria-label="Índice del proceso">'
        '<a href="#e2e-principle">Modelo mental</a><a href="#e2e-map">Pipeline</a><a href="#e2e-agents">Agentes</a>'
        '<a href="#e2e-gates">Gates</a><a href="#e2e-costs">Costos</a><a href="#e2e-artifacts">Artefactos</a>'
        '<a href="#e2e-actions">Actions</a><a href="#e2e-reliability">Confiabilidad</a></nav>'
        '<section id="e2e-principle" class="e2e-chapter"><span class="eyebrow">01 · Modelo mental</span><h2>Dos capas que nunca deben confundirse</h2>'
        '<div class="e2e-two-layers"><article><span class="e2e-kind agent">agent</span><h3>Capa probabilística</h3>'
        '<p>Selecciona, interpreta, estructura, redacta, critica, refina y propone visuales. Es buena para decisiones semánticas donde hay múltiples respuestas razonables.</p>'
        '<ul><li>No escribe archivos por autoridad propia.</li><li>No decide si un run es publicable.</li><li>No controla retries ni loops.</li><li>No promueve contenido a carpetas canónicas.</li></ul></article>'
        '<article><span class="e2e-kind deterministic">deterministic</span><h3>Capa de control</h3>'
        '<p>Valida esquemas, limita iteraciones, calcula duración, compara novedad, aplica gates, descarga assets, persiste trazas, mueve archivos y despliega Pages.</p>'
        '<ul><li>Es reproducible y testeable.</li><li>Falla de forma explícita.</li><li>Conserva evidencia de cada decisión.</li><li>Es la autoridad final.</li></ul></article></div>'
        '<p class="e2e-callout"><strong>Por qué importa:</strong> si un LLM fuera también el controlador, podría “aprobarse a sí mismo”, repetir indefinidamente o dejar efectos parciales. Aquí la creatividad vive dentro de una jaula determinista.</p></section>'
        '<section id="e2e-map" class="e2e-chapter"><span class="eyebrow">02 · Pipeline</span><h2>El recorrido completo</h2>'
        '<p class="e2e-intro">De arriba hacia abajo: cada bloque indica qué entra, qué sale, qué parte es probabilística y qué componente conserva la autoridad.</p>'
        + _timeline() + '</section>'
        '<section id="e2e-agents" class="e2e-chapter"><span class="eyebrow">03 · Agentes</span><h2>Dónde se usa IA y para qué</h2>'
        '<p class="e2e-intro">El repositorio mantiene agentes ADK independientes. No hay un “superagente” con permiso para hacer todo; cada uno tiene un contrato acotado y una salida estructurada.</p>'
        + _agent_table()
        + '<div class="e2e-note-grid"><article><h3>¿Por qué jueces separados?</h3><p>Porque factualidad, SEO, atención y voz no son la misma cosa. Separarlos hace visibles los trade-offs y permite que el gate exija mínimos por dimensión.</p></article>'
        '<article><h3>¿Por qué perfiles editoriales versionados?</h3><p><code>editorial/voice_profile.md</code> y <code>editorial/discourse_profile.md</code> son datos versionados. Así cambiar prompts o modelo no redefine silenciosamente la identidad del canal.</p></article>'
        '<article><h3>¿Por qué ADK sin tools con side effects?</h3><p>Las llamadas de agentes son seguras de reintentar porque no tienen herramientas de escritura externa. Un retry no debería publicar, borrar o mutar el mundo.</p></article></div></section>'
        '<section id="e2e-gates" class="e2e-chapter"><span class="eyebrow">04 · Quality gates</span><h2>Cómo decide el sistema que un guion merece avanzar</h2>'
        '<p class="e2e-intro">La aprobación no es una opinión agregada. Es una conjunción de restricciones. Si una falla, el candidato no pasa aunque el promedio se vea bonito.</p>'
        + _gate_block()
        + '<h3 class="e2e-subheading">Estados finales posibles</h3>' + _state_machine() + '</section>'
        '<section id="e2e-costs" class="e2e-chapter"><span class="eyebrow">05 · FinOps</span><h2>Qué cuesta, cómo se calcula y qué no debe fingirse</h2>'
        + _cost_section(snapshot) + '</section>'
        '<section id="e2e-artifacts" class="e2e-chapter"><span class="eyebrow">06 · Artefactos</span><h2>La memoria auditable del run</h2>'
        '<p class="e2e-intro">El objetivo no es solo producir un guion. El objetivo es poder reconstruir por qué existió ese guion, qué se evaluó, cuánto costó y por qué fue —o no fue— aprobado.</p>'
        + _artifact_map() + '</section>'
        '<section id="e2e-actions" class="e2e-chapter"><span class="eyebrow">07 · GitHub Actions</span><h2>Tres lanes complementarias</h2>'
        + _workflow_lanes() + '</section>'
        '<section id="e2e-reliability" class="e2e-chapter"><span class="eyebrow">08 · Confiabilidad y seguridad</span><h2>Cómo se evita que un sistema agéntico se vuelva frágil</h2>'
        '<div class="e2e-note-grid"><article><h3>Retries acotados</h3><p>Solo errores probablemente transitorios usan backoff exponencial. Auth inválida, contratos rotos o inputs inválidos no se reintentan indefinidamente.</p></article>'
        '<article><h3>Input no confiable</h3><p>Las noticias se consideran datos no confiables. Los prompts deben ignorar instrucciones embebidas en fuentes y los agentes lectores no reciben herramientas capaces de ejecutar efectos externos.</p></article>'
        '<article><h3>Validación doble</h3><p>Pydantic valida la forma de las respuestas; Python valida reglas de dominio: IDs válidos, máximo de noticias, duración, slots, caps, scores y riesgos.</p></article>'
        '<article><h3>Aislamiento</h3><p>Un intento vive primero en <code>.pipeline-runs/</code>. Solo una cadena completa de éxito puede reemplazar el episodio canónico.</p></article>'
        '<article><h3>Anti-loop</h3><p>El refinamiento tiene máximo de iteraciones y hash de guion. Si un refiner produce un candidato ya juzgado, el loop se corta.</p></article>'
        '<article><h3>Fail closed</h3><p>Ante incertidumbre de estado, el sistema prefiere no publicar. <code>approved</code> es la única condición promotable.</p></article></div>'
        '<div class="e2e-final"><span class="eyebrow">La idea que debes recordar</span><h2>Agentic no significa autónomo sin control</h2>'
        '<p>Este repositorio usa IA donde la semántica importa y software tradicional donde la certeza importa. La calidad aparece de la combinación: '
        '<strong>agentes especializados + contratos estructurados + gates deterministas + observabilidad + costos medibles + despliegue reproducible.</strong></p></div></section>'
        '</section>'
    )


E2E_CSS = r"""
/* v8: long-form E2E teaching workspace. */
.e2e-process-section{padding:22px 0 28px}.e2e-hero{padding:4px 0 18px;max-width:920px}.e2e-hero h2{font-size:clamp(30px,4.4vw,52px);line-height:1.04;margin:7px 0 12px;letter-spacing:-.035em}.e2e-hero p{color:#b6c5d4;font-size:16px;line-height:1.65;margin:0}.e2e-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:8px 0 16px}.e2e-kpi{border:1px solid var(--line);border-radius:15px;background:var(--panel);padding:14px}.e2e-kpi span{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.07em}.e2e-kpi strong{display:block;font-size:24px;margin:7px 0 4px}.e2e-kpi small{color:#9fb0c2;line-height:1.35}.e2e-toc{display:flex;flex-wrap:wrap;gap:7px;position:sticky;top:8px;z-index:5;padding:8px;border:1px solid var(--line);border-radius:13px;background:rgba(14,20,29,.94);backdrop-filter:blur(12px);margin:14px 0 28px}.e2e-toc a{color:#b9d8ed;text-decoration:none;padding:7px 10px;border-radius:8px;background:#172331;font-size:11px;font-weight:750}.e2e-toc a:hover{background:#213247}.e2e-chapter{scroll-margin-top:72px;padding:36px 0 10px;border-top:1px solid var(--line)}.e2e-chapter>h2{font-size:clamp(25px,3vw,36px);margin:6px 0 9px;letter-spacing:-.02em}.e2e-intro{color:var(--muted);max-width:840px;line-height:1.6;margin:0 0 18px}.e2e-two-layers{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:18px 0}.e2e-two-layers article,.e2e-note-grid article{border:1px solid var(--line);border-radius:16px;background:var(--panel);padding:18px}.e2e-two-layers h3,.e2e-note-grid h3{margin:10px 0 6px}.e2e-two-layers p,.e2e-two-layers li,.e2e-note-grid p{color:#aebdcd;line-height:1.55}.e2e-two-layers ul{padding-left:19px;margin-bottom:0}.e2e-callout{padding:14px 16px;border:1px solid #31506b;border-left:4px solid #5ea4d2;border-radius:12px;background:#101b28;color:#bfd0de;line-height:1.6}.e2e-timeline{margin-top:22px}.e2e-stage{display:grid;grid-template-columns:56px 1fr;gap:10px}.e2e-stage-rail{display:flex;flex-direction:column;align-items:center}.e2e-stage-number{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;border:1px solid #38516b;background:#162231;font:800 11px/1 ui-monospace,monospace;color:#c7e4f5}.e2e-stage-line{width:1px;flex:1;background:linear-gradient(#38516b,#1d2938);min-height:22px}.e2e-stage:last-child .e2e-stage-line{display:none}.e2e-stage-body{border:1px solid var(--line);border-radius:16px;background:var(--panel);padding:16px 17px;margin-bottom:13px}.e2e-stage-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.e2e-stage-head h3{margin:0;font-size:17px}.e2e-kind{display:inline-flex;padding:4px 7px;border-radius:999px;font-size:9px;text-transform:uppercase;letter-spacing:.07em;font-weight:850;background:#213043;color:#c3d3e3}.e2e-kind.agent{background:#17324a;color:#bce6ff}.e2e-kind.judges{background:#2f2544;color:#dcc8ff}.e2e-kind.gate{background:#3a2b17;color:#f0d3a5}.e2e-kind.service{background:#17352d;color:#b9e8d8}.e2e-kind.pages{background:#2f2338;color:#efc8f8}.e2e-kind.deterministic{background:#202b38;color:#d1dbe7}.e2e-stage-summary{color:#b5c4d3;line-height:1.58;margin:9px 0 13px}.e2e-stage-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.e2e-stage-grid>div{border-top:1px solid #263447;padding-top:8px}.e2e-stage-grid span{display:block;color:#7f94aa;font-size:9px;text-transform:uppercase;letter-spacing:.07em}.e2e-stage-grid p{margin:4px 0 0;color:#aebdcd;font-size:12px;line-height:1.45}.e2e-stage-grid code{white-space:normal}.e2e-table-wrap{overflow:auto;border:1px solid var(--line);border-radius:15px;background:#101722}.e2e-table{width:100%;border-collapse:collapse;min-width:780px;font-size:12px}.e2e-table th{background:#161f2c;color:#91a5ba;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;padding:10px 12px}.e2e-table td{padding:11px 12px;border-top:1px solid #243143;vertical-align:top;color:#bdcad7}.e2e-note-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:13px}.e2e-note-grid article{padding:15px}.e2e-note-grid h3{font-size:14px;margin:0 0 6px}.e2e-note-grid p{font-size:12px;margin:0}.e2e-check-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}.e2e-check{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:14px}.e2e-check span{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em}.e2e-check strong{display:block;margin:7px 0 5px;font-size:20px}.e2e-check p{margin:0;color:#9fb0c2;font-size:11px;line-height:1.45}.e2e-subheading{margin:28px 0 10px}.e2e-state-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.e2e-state{border:1px solid var(--line);border-radius:13px;background:var(--panel);padding:12px}.e2e-state code{font-weight:800}.e2e-publishable{float:right;color:#8fa3b8;font-size:10px}.e2e-state p{clear:both;margin:7px 0 0;color:#aab9c8;font-size:12px;line-height:1.45}.e2e-formula{padding:11px 13px;border-radius:11px;background:#0e151f;border:1px solid var(--line);font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;color:#b8cbdb}.e2e-cost-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.e2e-cost-card{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:14px}.e2e-cost-card span{color:var(--muted);font-size:11px}.e2e-cost-card strong{display:block;font-size:22px;margin:7px 0 5px}.e2e-cost-card p{margin:0;color:#9fb0c2;font-size:11px;line-height:1.45}.e2e-footnote{color:var(--muted);font-size:11px}.e2e-artifacts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.e2e-artifact{border:1px solid var(--line);border-radius:13px;background:var(--panel);padding:12px}.e2e-artifact code{font-size:12px;font-weight:800}.e2e-artifact>span{float:right;color:#8ea3b8;font-size:9px;text-transform:uppercase;letter-spacing:.06em}.e2e-artifact p{clear:both;margin:6px 0 0;color:#aab9c8;font-size:12px;line-height:1.45}.e2e-lanes{display:grid;gap:10px}.e2e-lane{border:1px solid var(--line);border-radius:15px;background:var(--panel);padding:16px}.e2e-lane h3{margin:4px 0 7px}.e2e-lane p{color:#aebdcd;line-height:1.55;margin:0}.e2e-chain{margin-top:11px;padding:9px 11px;border-radius:9px;background:#0f1722;color:#9fc6df;font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;overflow:auto}.e2e-final{margin-top:24px;padding:24px;border:1px solid #31506b;border-radius:18px;background:linear-gradient(145deg,#101a25,#132536)}.e2e-final h2{font-size:clamp(24px,3vw,34px);margin:6px 0}.e2e-final p{margin:0;color:#bed0df;line-height:1.65;max-width:900px}
@media(max-width:980px){.e2e-kpis,.e2e-check-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.e2e-note-grid,.e2e-cost-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:680px){.e2e-toc{position:static}.e2e-kpis,.e2e-two-layers,.e2e-stage-grid,.e2e-state-grid,.e2e-cost-grid,.e2e-artifacts,.e2e-note-grid,.e2e-check-grid{grid-template-columns:1fr}.e2e-stage{grid-template-columns:42px 1fr}.e2e-stage-number{width:32px;height:32px}.e2e-stage-body{padding:13px}.e2e-hero h2{font-size:32px}.e2e-publishable,.e2e-artifact>span{float:none;display:block;margin-top:5px}}
"""


def apply_e2e_workspace(document: str, snapshot: dict[str, Any]) -> str:
    document = document.replace("</style>", E2E_CSS + "\n</style>", 1)

    budget_tab = '<button id="tab-budget"'
    tab_at = document.find(budget_tab)
    if tab_at < 0:
        raise RuntimeError("Review Hub v8 could not find Budget tab")
    tab = (
        '<button id="tab-process" class="hub-tab" type="button" role="tab" aria-selected="false" '
        'aria-controls="panel-process" data-tab="process">Proceso E2E</button>\n'
    )
    document = document[:tab_at] + tab + document[tab_at:]

    budget_panel = '<div id="panel-budget"'
    panel_at = document.find(budget_panel)
    if panel_at < 0:
        raise RuntimeError("Review Hub v8 could not find Budget panel")
    panel = (
        '<div id="panel-process" class="hub-panel" role="tabpanel" aria-labelledby="tab-process" data-panel="process" hidden>'
        + process_panel(snapshot)
        + '</div>\n'
    )
    document = document[:panel_at] + panel + document[panel_at:]
    return document


def build_site(
    *,
    episode_dir: Path,
    media_dir: Path,
    media_zip: Path,
    regression_path: Path,
    cases_path: Path,
    output_dir: Path,
    run_id: str,
    pricing_path: Path | None = None,
) -> Path:
    index_path = _build_site_v7(
        episode_dir=episode_dir,
        media_dir=media_dir,
        media_zip=media_zip,
        regression_path=regression_path,
        cases_path=cases_path,
        output_dir=output_dir,
        run_id=run_id,
        pricing_path=pricing_path,
    )
    snapshot_path = output_dir / "downloads" / "cost_snapshot.json"
    snapshot: dict[str, Any] = {}
    if snapshot_path.exists():
        try:
            loaded = json.loads(snapshot_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                snapshot = loaded
        except (OSError, json.JSONDecodeError):
            snapshot = {}
    document = apply_e2e_workspace(index_path.read_text(encoding="utf-8"), snapshot)
    index_path.write_text(document, encoding="utf-8")
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


if __name__ == "__main__":
    main()
