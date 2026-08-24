from __future__ import annotations

from typing import Any


ARCHITECTURE_VERSION = 1

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
        "summary": "Valida contratos, decide routing, limita loops, persiste estado, promueve artefactos y despliega.",
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
    {"name": "multimedia_editor_master", "module": "app.agent", "symbol": "multimedia_editor_agent", "role": "Multimedia", "responsibility": "Slots que realmente necesitan apoyo visual"},
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
    {"id": "ingest", "kind": "deterministic", "title": "Ingesta y ventana editorial", "summary": "Lee noticias estructuradas, tolera días faltantes y corta temprano si no hay fuentes.", "inputs": "news/YYYY-MM-DD.txt", "outputs": "NewsItem[] + fechas faltantes", "authority": "Python", "code": "pipeline/news.py · pipeline/run.py", "trace_steps": []},
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
    {"id": "media_plan", "kind": "agent", "title": "Plan multimedia", "summary": "Decide dónde el apoyo visual externo añade valor explicativo.", "inputs": "script + plan + timeline + cap", "outputs": "multimedia/plan.json", "authority": "Agente propone; Python normaliza", "code": "app/agent.py → multimedia_editor_master", "trace_steps": ["plan_multimedia"]},
    {"id": "media_materialize", "kind": "service", "title": "Materialización de medios", "summary": "Descarga proveedores con retries acotados y fallback local.", "inputs": "queries aprobadas", "outputs": "assets + manifest + credits", "authority": "Python", "code": "pipeline/media.py · pipeline/credits.py", "trace_steps": []},
    {"id": "report_promote", "kind": "deterministic", "title": "Estado, trazas, reporte y promoción", "summary": "Persiste evidencia del run y solo promueve si el estado es approved.", "inputs": "artefactos + gate final", "outputs": "run_state + execution_trace + run_report", "authority": "Python/GitHub Actions", "code": "pipeline/report.py · build-video-kit.yml", "trace_steps": []},
    {"id": "pages", "kind": "pages", "title": "Regression → Review Hub → GitHub Pages", "summary": "Construye la superficie de revisión, costos, catálogo histórico y Pages.", "inputs": "editorial-regression artifact + pricing + media", "outputs": "review-site + cost_snapshot + pages-site", "authority": "Workflows deterministas", "code": "editorial-regression.yml · editorial-review-hub.yml", "trace_steps": []},
]

REFINEMENT_PHASES = [
    {"id": "factual", "agent": "factual_script_refiner", "trace_step": "refine_factual", "condition": "Falla editorial_approved, editorial_score_ok o factuality_low", "context": "Fuentes + Claim Ledger; sin voz/SEO/atención"},
    {"id": "voice", "agent": "voice_script_refiner", "trace_step": "refine_voice", "condition": "Factualidad pasa y falla voice_approved, voice_score_ok o ai_smell_low", "context": "Voice review + plan + voice profile; sin corpus fuente"},
    {"id": "secondary", "agent": "secondary_script_refiner", "trace_step": "refine_secondary", "condition": "Factualidad y voz pasan; queda SEO/atención/pacing/duración", "context": "SEO/attention + plan; claims congelados"},
]

DECISION_FLOW = [
    "¿Hay fuentes? → no: no_source_news",
    "¿Hay historias relevantes? → no: no_relevant_news",
    "¿Hay ángulo suficientemente novedoso? → no: no_novel_essay_angle",
    "Write → 4 judges → deterministic gate",
    "¿Gate aprobado? → sí: multimedia → report → approved",
    "¿Gate falló factualidad? → factual repair → rejudge",
    "¿Factualidad pasó pero falló voz? → voice repair → rejudge",
    "¿Factualidad y voz pasaron pero queda otro gate? → secondary polish → rejudge",
    "¿Se agotó refinamiento? → script_not_approved",
]

DESIGN_DECISIONS = [
    ("Claim Ledger antes de la prosa", "Evita que marketing, inferencias o hipótesis se eleven silenciosamente a hechos."),
    ("Cuatro jueces en vez de uno", "Evita que un score promedio esconda factualidad débil, mala retención o voz artificial."),
    ("Tres refiners con contextos distintos", "Aísla responsabilidades y evita oscilaciones entre reparar hechos y estilo."),
    ("Sin LLM como controlador", "Python decide routing, retries, límites, estado y publicación."),
    ("Promoción fail-closed", "Solo approved puede tocar el episodio canónico."),
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
