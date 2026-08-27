from __future__ import annotations

from typing import Any


ARCHITECTURE_VERSION = 3

LAYERS = [
    {
        "id": "probabilistic",
        "title": "Capa probabilística",
        "kind": "agent",
        "summary": "Selecciona, estructura, escribe, juzga, repara una dimensión concreta y propone visuales.",
    },
    {
        "id": "deterministic",
        "title": "Capa de control",
        "kind": "deterministic",
        "summary": "Valida cobertura y contratos, decide routing, limita loops, persiste estado, promueve artefactos y despliega.",
    },
]

AGENTS = [
    {"name": "news_relevance_selector", "module": "app.agent", "symbol": "selector_agent", "role": "Selección", "responsibility": "Historias con valor editorial"},
    {"name": "editorial_director", "module": "app.agent", "symbol": "editorial_director_agent", "role": "Arquitectura", "responsibility": "Pregunta, tesis, evidencia, Claim Ledger y beats"},
    {"name": "essay_script_writer", "module": "app.agent", "symbol": "writer_agent", "role": "Generación", "responsibility": "Ensayo completo dentro de la frontera factual"},
    {"name": "script_critic", "module": "app.agent", "symbol": "reviewer_agent", "role": "Juez", "responsibility": "Factualidad y rigor intelectual"},
    {"name": "seo_master", "module": "app.agent", "symbol": "seo_master_agent", "role": "Juez", "responsibility": "Descubribilidad"},
    {"name": "youtube_attention_master", "module": "app.agent", "symbol": "youtube_attention_master_agent", "role": "Juez", "responsibility": "Atención, ritmo y progresión"},
    {"name": "voice_humanity_critic", "module": "app.agent", "symbol": "voice_humanity_critic_agent", "role": "Juez", "responsibility": "Voz, humanidad, profundidad y AI-smell"},
    {"name": "multimedia_editor_master", "module": "app.agent", "symbol": "multimedia_editor_agent", "role": "Multimedia", "responsibility": "Propone slots del paquete denso post-aprobación; producción conserva fallback determinista"},
    {"name": "factual_script_refiner", "module": "app.refiners", "symbol": "factual_refiner_agent", "role": "Refiner aislado", "responsibility": "Repara hechos y traceabilidad con acceso a fuentes"},
    {"name": "voice_script_refiner", "module": "app.refiners", "symbol": "voice_refiner_agent", "role": "Refiner aislado", "responsibility": "Repara voz sin acceso al corpus fuente"},
    {"name": "secondary_script_refiner", "module": "app.refiners", "symbol": "secondary_refiner_agent", "role": "Refiner aislado", "responsibility": "Repara SEO/atención al final, con claims congelados"},
]

CLAIM_LEDGER_FIELDS = [
    ("supported_facts", "Afirmaciones que la evidencia permite tratar como hechos."),
    ("allowed_interpretations", "Lecturas razonables que deben permanecer como interpretación."),
    ("hypotheses", "Explicaciones posibles que nunca deben presentarse como verificadas."),
    ("uncertainties", "Lo que sigue abierto con las fuentes disponibles."),
    ("prohibited_claims", "Saltos que writer y refiners no pueden introducir."),
    ("source_limitations", "Límites de cobertura, independencia o calidad de la fuente."),
]

STAGES: list[dict[str, Any]] = [
    {"id": "trigger", "kind": "deterministic", "title": "Disparo y contrato de ejecución", "summary": "Resuelve fecha, ventana, límites y flags de promoción.", "inputs": "schedule / workflow_dispatch + variables", "outputs": "target_date + opciones de runtime", "authority": "GitHub Actions", "code": ".github/workflows/build-video-kit.yml", "trace_steps": []},
    {"id": "workspace", "kind": "deterministic", "title": "Workspace aislado", "summary": "Cada intento vive fuera de las carpetas canónicas.", "inputs": "target_date + github.run_id", "outputs": ".pipeline-runs/<date>/<run-id>/", "authority": "Shell/Python", "code": ".github/workflows/build-video-kit.yml", "trace_steps": []},
    {"id": "source_coverage", "kind": "gate", "title": "Preflight de cobertura de fuentes", "summary": "Antes de gastar tokens exige por defecto >=75% de los días esperados y al menos una noticia estructurada. Si falla, termina como no_source_news.", "inputs": "ventana esperada + news/YYYY-MM-DD.txt", "outputs": "source_coverage.json + run_state temprano", "authority": "Python; ningún agente puede saltarlo", "code": "pipeline/source_coverage.py · build-video-kit.yml", "trace_steps": []},
    {"id": "ingest", "kind": "deterministic", "title": "Ingesta y ventana editorial", "summary": "Con cobertura suficiente, materializa el catálogo estructurado que alimentará el runtime.", "inputs": "news/YYYY-MM-DD.txt", "outputs": "NewsItem[] + fechas disponibles", "authority": "Python", "code": "pipeline/news.py · pipeline/run.py", "trace_steps": []},
    {"id": "memory", "kind": "deterministic", "title": "Memoria aprobada", "summary": "Solo episodios aprobados alimentan memoria de historias y ensayos.", "inputs": "scripts/ históricos aprobados", "outputs": "previous_selected_news + previous_essays", "authority": "Python", "code": "pipeline/run.py", "trace_steps": []},
    {"id": "selection", "kind": "agent", "title": "Selector editorial", "summary": "Reduce ruido y devuelve referencias a historias reales con valor humano/editorial.", "inputs": "noticias + historial", "outputs": "selected_news.json", "authority": "Agente propone; Python valida", "code": "app/agent.py → news_relevance_selector", "trace_steps": ["select_news"]},
    {"id": "planning", "kind": "agent", "title": "Director editorial + Claim Ledger", "summary": "Diseña pregunta, tesis, evidencia, Claim Ledger y beats antes de la prosa.", "inputs": "selected_news + perfiles + memoria", "outputs": "episode_plan.json", "authority": "Agente diseña; Pydantic/Python validan", "code": "app/agent.py → editorial_director", "trace_steps": ["plan_episode", "replan_episode_novelty"]},
    {"id": "novelty", "kind": "gate", "title": "Gate de novedad", "summary": "Compara el ángulo contra ensayos aprobados recientes y permite replans acotados.", "inputs": "episode_plan + previous_essays", "outputs": "novelty_check.json", "authority": "Python", "code": "pipeline/core.py · pipeline/run.py", "trace_steps": []},
    {"id": "writing", "kind": "agent", "title": "Writer con frontera factual", "summary": "Escribe usando fuentes, plan, perfiles y el Claim Ledger como frontera factual.", "inputs": "news_text + selected_news + episode_plan + perfiles", "outputs": "draft_script", "authority": "Agente redacta; parser valida", "code": "app/agent.py → essay_script_writer", "trace_steps": ["write_script"]},
    {"id": "judging", "kind": "judges", "title": "Cuatro jueces independientes", "summary": "Editorial/factualidad, SEO, atención y voz/humanidad evalúan dimensiones separadas.", "inputs": "script + evidencia + perfiles", "outputs": "4 reviews estructuradas", "authority": "Agentes juzgan; no publican", "code": "app/agent.py", "trace_steps": ["editorial_judge", "seo_judge", "attention_judge", "voice_judge"]},
    {"id": "quality_gate", "kind": "gate", "title": "Gate determinista de calidad", "summary": "Duración, scores, factualidad, AI-smell y aprobaciones se exigen como restricciones.", "inputs": "script + reviews", "outputs": "checks + approved/rejected", "authority": "Python", "code": "pipeline/core.py → evaluate_script_gate", "trace_steps": []},
    {"id": "refinement_router", "kind": "deterministic", "title": "Router de refinamiento", "summary": "Elige exactamente una fase en orden factual → voz → secundario.", "inputs": "gate del candidato", "outputs": "next_refinement_phase", "authority": "Python", "code": "pipeline/run.py → _select_refinement_phase", "trace_steps": []},
    {"id": "factual_refine", "kind": "agent", "title": "Factual repair", "summary": "Tiene fuentes y Claim Ledger; no recibe feedback de voz, SEO o atención.", "inputs": "script + factual review + fuentes + ledger", "outputs": "draft corregido factual", "authority": "factual_script_refiner", "code": "app/refiners.py", "trace_steps": ["refine_factual"]},
    {"id": "voice_refine", "kind": "agent", "title": "Voice repair", "summary": "Corre solo después de factualidad; no recibe corpus fuente y congela claims.", "inputs": "script + voice review + plan + voice_profile", "outputs": "draft corregido de voz", "authority": "voice_script_refiner", "code": "app/refiners.py", "trace_steps": ["refine_voice"]},
    {"id": "secondary_refine", "kind": "agent", "title": "Secondary polish", "summary": "Corrige SEO, atención, pacing o duración después de factualidad y voz.", "inputs": "script + SEO/attention review + plan", "outputs": "draft pulido", "authority": "secondary_script_refiner", "code": "app/refiners.py", "trace_steps": ["refine_secondary"]},
    {"id": "media_plan", "kind": "service", "title": "Paquete multimedia denso post-aprobación", "summary": "Producción omite el planner sparse del runtime y, solo tras aprobar el guion, ejecuta la política densa de hasta 54 assets. Puede usar el agente multimedia o fallback determinista si no hay cuota.", "inputs": "script aprobado + secciones + timeline + budget", "outputs": "multimedia/plan.json + paquete denso", "authority": "GitHub Actions/Python; el agente solo propone cuando está disponible", "code": "review_media_dense_hardened.py · review_media_density.py", "trace_steps": []},
    {"id": "media_materialize", "kind": "service", "title": "Materialización y gate multimedia", "summary": "Descarga proveedores con retries acotados, admite fallback local y exige >=45 assets y >=5 en los primeros 20 s con el budget productivo por defecto.", "inputs": "plan denso + queries", "outputs": "assets + manifest + credits + zip", "authority": "Python/GitHub Actions", "code": "pipeline/media.py · pipeline/review_media_offline_dense.py · build-video-kit.yml", "trace_steps": []},
    {"id": "footage_discovery", "kind": "service", "title": "Discovery de real footage en YouTube", "summary": "Tras aprobar el guion busca videos vinculados con la evidencia planificada, rankea candidatos con metadata y conserva enlaces para revisión editorial. Nunca descarga contenido audiovisual de YouTube ni declara fair use automáticamente.", "inputs": "selected_news + episode_plan + YOUTUBE_API_KEY", "outputs": "isolated run multimedia/footage_candidates.json (30-day ephemeral)", "authority": "Python/GitHub Actions para discovery; derechos y uso requieren revisión humana", "code": "pipeline/footage.py · build-video-kit.yml", "trace_steps": []},
    {"id": "report_promote", "kind": "deterministic", "title": "Estado, trazas, reporte y promoción", "summary": "Persiste evidencia del run y solo promueve si script, reporte y —cuando se pidió— multimedia densa terminaron correctamente.", "inputs": "artefactos + gate final + resultado multimedia", "outputs": "run_state + execution_trace + run_report + canon opcional", "authority": "Python/GitHub Actions", "code": "pipeline/report.py · build-video-kit.yml", "trace_steps": []},
    {"id": "pages", "kind": "pages", "title": "Artifact productivo → Review Hub → GitHub Pages", "summary": "Pages consume el ai-news-run real como fuente canónica. Editorial Regression queda como lane separada de QA; Review Hub reutiliza multimedia productiva válida y solo reconstruye artifacts legacy/sparse.", "inputs": "ai-news-run-* + pricing + historia de Review Hub", "outputs": "review-site + cost_snapshot + pages-site", "authority": "Workflows deterministas", "code": "editorial-review-hub.yml · editorial-regression.yml", "trace_steps": []},
]

REFINEMENT_PHASES = [
    {"id": "factual", "agent": "factual_script_refiner", "trace_step": "refine_factual", "condition": "Falla editorial_approved, editorial_score_ok o factuality_low", "context": "Fuentes + Claim Ledger; sin voz/SEO/atención"},
    {"id": "voice", "agent": "voice_script_refiner", "trace_step": "refine_voice", "condition": "Factualidad pasa y falla voice_approved, voice_score_ok o ai_smell_low", "context": "Voice review + plan + voice profile; sin corpus fuente"},
    {"id": "secondary", "agent": "secondary_script_refiner", "trace_step": "refine_secondary", "condition": "Factualidad y voz pasan; queda SEO/atención/pacing/duración", "context": "SEO/attention + plan; claims congelados"},
]

DECISION_FLOW = [
    "¿Cobertura de fuentes >= umbral y hay noticias estructuradas? → no: no_source_news sin llamadas de modelo",
    "¿Hay historias relevantes? → no: no_relevant_news",
    "¿Hay ángulo suficientemente novedoso? → no: no_novel_essay_angle",
    "Write → 4 judges → deterministic gate",
    "¿Gate falló factualidad? → factual repair → rejudge",
    "¿Factualidad pasó pero falló voz? → voice repair → rejudge",
    "¿Factualidad y voz pasaron pero queda otro gate? → secondary polish → rejudge",
    "¿Se agotó refinamiento? → script_not_approved",
    "¿Guion aprobado? → paquete multimedia denso + discovery de real footage en YouTube",
    "¿Multimedia solicitada no cumple su gate? → se preserva el run, no se promueve",
    "¿Script + report + media solicitada pasan? → approved/promoción → ai-news-run → Review Hub/Pages",
]

DESIGN_DECISIONS = [
    ("Cobertura antes de tokens", "Una ventana insuficiente falla antes de cualquier llamada de modelo; evita aprobar episodios construidos sobre evidencia temporal demasiado incompleta."),
    ("Claim Ledger antes de la prosa", "Evita que marketing, inferencias o hipótesis se eleven silenciosamente a hechos."),
    ("Cuatro jueces en vez de uno", "Evita que un score promedio esconda factualidad débil, mala retención o voz artificial."),
    ("Tres refiners con contextos distintos", "Aísla responsabilidades y evita oscilaciones entre reparar hechos y estilo."),
    ("Multimedia después del gate editorial", "No se gastan búsquedas/assets ni se deja que lo visual convierta un script rechazado en publicable."),
    ("Discovery separado de derechos", "YouTube se usa para encontrar y rankear candidatos; metadata, atribución o duración breve no se tratan como permiso de descarga, edición, publicación o fair use."),
    ("Producción es la fuente de verdad de Pages", "Review Hub observa el artifact que realmente salió de Build AI News Video Kit; Regression queda como QA independiente."),
    ("Sin LLM como controlador", "Python decide routing, retries, límites, estado y publicación."),
    ("Promoción fail-closed", "Solo una cadena completa de éxito puede tocar el episodio canónico."),
    ("Identidad editorial versionada", "Cambiar modelo o prompt no redefine silenciosamente la voz del canal."),
]


def manifest() -> dict[str, Any]:
    return {
        "version": ARCHITECTURE_VERSION,
        "layers": LAYERS,
        "agents": AGENTS,
        "claim_ledger_fields": CLAIM_LEDGER_FIELDS,
        "stages": STAGES,
        "refinement_phases": REFINEMENT_PHASES,
        "decision_flow": DECISION_FLOW,
        "design_decisions": DESIGN_DECISIONS,
    }
