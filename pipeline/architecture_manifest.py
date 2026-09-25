from __future__ import annotations

from typing import Any


ARCHITECTURE_VERSION = 16

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
    {"id": "narrative_memory", "kind": "deterministic", "title": "Narrative Memory verificada", "summary": "Valida la biblioteca externa, deriva uso desde episodios aprobados y recupera un contexto pequeño con cooldown/diversidad; el Director debe elegir 1–2 y uno debe abrir el ensayo.", "inputs": "editorial/narrative_memory.jsonl + selected_news + historial aprobado", "outputs": "narrative_memory_candidates.json + narrative_memory_selection.json", "authority": "Python valida/recupera; la tarea programada solo investiga y agrega conocimiento", "code": "pipeline/narrative_memory.py · docs/narrative_memory_contract.md", "trace_steps": []},
    {"id": "planning", "kind": "agent", "title": "Director editorial + Claim Ledger", "summary": "Diseña pregunta, tesis, evidencia, Claim Ledger y beats antes de la prosa.", "inputs": "selected_news + perfiles + memoria", "outputs": "episode_plan.json", "authority": "Agente diseña; Pydantic/Python validan", "code": "app/agent.py → editorial_director", "trace_steps": ["plan_episode", "replan_episode_novelty"]},
    {"id": "novelty", "kind": "gate", "title": "Gate de novedad", "summary": "Compara el ángulo contra ensayos aprobados recientes y permite replans acotados.", "inputs": "episode_plan + previous_essays", "outputs": "novelty_check.json", "authority": "Python", "code": "pipeline/core.py · pipeline/run.py", "trace_steps": []},
    {"id": "writing", "kind": "agent", "title": "Writer con frontera factual", "summary": "Escribe usando fuentes, plan, perfiles y el Claim Ledger como frontera factual; la Narrative Memory seleccionada abre el ensayo como micro-historia verificada.", "inputs": "news_text + selected_news + episode_plan + perfiles", "outputs": "draft_script", "authority": "Agente redacta; parser valida", "code": "app/agent.py → essay_script_writer", "trace_steps": ["write_script"]},
    {"id": "judging", "kind": "judges", "title": "Cuatro jueces independientes", "summary": "Editorial/factualidad, SEO, atención y voz/humanidad evalúan dimensiones separadas.", "inputs": "script + evidencia + perfiles", "outputs": "4 reviews estructuradas", "authority": "Agentes juzgan; no publican", "code": "app/agent.py", "trace_steps": ["editorial_judge", "seo_judge", "attention_judge", "voice_judge"]},
    {"id": "quality_gate", "kind": "gate", "title": "Gate determinista de calidad", "summary": "Duración, scores, factualidad, AI-smell y aprobaciones se exigen como restricciones.", "inputs": "script + reviews", "outputs": "checks + approved/rejected", "authority": "Python", "code": "pipeline/core.py → evaluate_script_gate", "trace_steps": []},
    {"id": "refinement_router", "kind": "deterministic", "title": "Router de refinamiento", "summary": "Elige exactamente una fase en orden factual → voz → secundario.", "inputs": "gate del candidato", "outputs": "next_refinement_phase", "authority": "Python", "code": "pipeline/run.py → _select_refinement_phase", "trace_steps": []},
    {"id": "factual_refine", "kind": "agent", "title": "Factual repair", "summary": "Tiene fuentes y Claim Ledger; no recibe feedback de voz, SEO o atención.", "inputs": "script + factual review + fuentes + ledger", "outputs": "draft corregido factual", "authority": "factual_script_refiner", "code": "app/refiners.py", "trace_steps": ["refine_factual"]},
    {"id": "voice_refine", "kind": "agent", "title": "Voice repair", "summary": "Corre solo después de factualidad; no recibe corpus fuente y congela claims.", "inputs": "script + voice review + plan + voice_profile", "outputs": "draft corregido de voz", "authority": "voice_script_refiner", "code": "app/refiners.py", "trace_steps": ["refine_voice"]},
    {"id": "secondary_refine", "kind": "agent", "title": "Secondary polish", "summary": "Corrige SEO, atención, pacing o duración después de factualidad y voz.", "inputs": "script + SEO/attention review + plan", "outputs": "draft pulido", "authority": "secondary_script_refiner", "code": "app/refiners.py", "trace_steps": ["refine_secondary"]},
    {"id": "media_plan", "kind": "service", "title": "Paquete multimedia denso post-aprobación", "summary": "Producción omite el planner sparse del runtime y, solo tras aprobar el guion, ejecuta la política densa de hasta 54 assets. Puede usar el agente multimedia o fallback determinista si no hay cuota.", "inputs": "script aprobado + secciones + timeline + budget", "outputs": "multimedia/plan.json + paquete denso", "authority": "GitHub Actions/Python; el agente solo propone cuando está disponible", "code": "review_media_dense_hardened.py · review_media_density.py", "trace_steps": []},
    {"id": "media_materialize", "kind": "service", "title": "Materialización y gate multimedia", "summary": "Descarga proveedores con retries acotados, admite fallback local y exige >=45 assets y >=5 en los primeros 20 s con el budget productivo por defecto.", "inputs": "plan denso + queries", "outputs": "assets + manifest + credits + zip", "authority": "Python/GitHub Actions", "code": "pipeline/media.py · pipeline/review_media_offline_dense.py · build-video-kit.yml", "trace_steps": []},
    {"id": "footage_discovery", "kind": "service", "title": "Discovery de real footage en YouTube", "summary": "Tras aprobar el guion busca videos vinculados con la evidencia planificada, rankea candidatos con metadata y conserva enlaces para revisión editorial. Nunca descarga contenido audiovisual de YouTube ni declara fair use automáticamente.", "inputs": "selected_news + episode_plan + YOUTUBE_API_KEY", "outputs": "isolated run multimedia/footage_candidates.json (30-day ephemeral)", "authority": "Python/GitHub Actions para discovery; derechos y uso requieren revisión humana", "code": "pipeline/footage.py · build-video-kit.yml", "trace_steps": []},
    {"id": "editing_style", "kind": "deterministic", "title": "Gramática audiovisual versionada", "summary": "Aplica defaults por rol visual y lint de ritmo/transiciones/presencia en cámara. Empieza en modo observe para aprender de retención real antes de convertir preferencias estéticas en gates.", "inputs": "config/editing_style.yaml + timeline propuesto", "outputs": "editing_style fingerprint + style_warnings dentro de edit_manifest.json", "authority": "Python; política audiovisual, nunca autoridad factual", "code": "pipeline/editing_style.py · config/editing_style.yaml · docs/editing_style.md", "trace_steps": []},
    {"id": "edit_manifest", "kind": "deterministic", "title": "Contrato de edición pre-recording", "summary": "Convierte guion, secciones y multimedia en un timeline presenter-first con cues de director separados de la narración. Declara readiness explícito y nunca finge frame accuracy antes de grabar.", "inputs": "script.txt + script_sections.json + multimedia plan/manifest", "outputs": "multimedia/<date>/edit_manifest.json", "authority": "Python; señales de dirección son sugerencias y no pueden cambiar hechos ni narración", "code": "pipeline/edit_manifest.py · config/edit_manifest.schema.json", "trace_steps": []},
    {"id": "recording_pack", "kind": "deterministic", "title": "Recording Pack + teleprompter", "summary": "Parte el ensayo aprobado en takes grabables de ~20–60 s sin alterar la narración, añade claquetas estables y contexto de edición, y genera un teleprompter HTML autónomo.", "inputs": "script aprobado + script_sections + production_script + edit_manifest opcional", "outputs": "recording_pack.json + camera_script.md + teleprompter.html (standalone offline)", "authority": "Python; script.txt permanece autoridad editorial", "code": "pipeline/recording_pack.py · config/recording_pack.schema.json · build-video-kit.yml", "trace_steps": []},
    {"id": "recording_ingest", "kind": "deterministic", "title": "Recording Ingest Contract", "summary": "Genera la convención de nombres y el contrato local para cámara/audio. Cuando existen grabaciones, escanea retakes sin mover ni borrar crudos, valida media y selecciona sólo un candidato técnico provisional por take.", "inputs": "recording_pack.json; grabaciones locales opcionales", "outputs": "recording_ingest_contract.json + recording_ingest_instructions.md; recording_ingest_manifest.json sólo tras escaneo local", "authority": "Python + FFmpeg/ffprobe; take_id es join key y la selección no juzga actuación ni fidelidad al guion", "code": "pipeline/recording_ingest.py · config/recording_ingest_contract.schema.json · config/recording_ingest_manifest.schema.json", "trace_steps": []},
    {"id": "recording_alignment", "kind": "deterministic", "title": "Recording Alignment + retake selection", "summary": "Define el contrato de transcripción/alineación, compara cada retake con el spoken_text mediante WER/cobertura, prioriza fidelidad sobre score técnico y calcula trims con timestamps por palabra. WhisperX también emite SRT sidecars opcionales para el flujo de transcripción de Resolve; casos ambiguos fallan a revisión humana.", "inputs": "recording_pack.json + recording_ingest_manifest.json + transcript bundle local", "outputs": "recording_alignment_contract.json antes de grabar; recording_alignment.json después de transcribir", "authority": "Python determinista; WhisperX es adapter local opcional y no decide la edición por sí solo", "code": "pipeline/recording_alignment.py · pipeline/whisperx_adapter.py · config/recording_alignment.yaml", "trace_steps": []},
    {"id": "resolve_alignment", "kind": "local_bridge", "title": "Resolve Alignment Bridge", "summary": "Importa cámara/lav seleccionados en DaVinci Resolve, usa el scratch audio de cámara para sincronizar el lav por waveform con enums vivos de la API y exige read-back verificable antes de avanzar. La transcripción nativa de Resolve queda sólo como diagnóstico opcional.", "inputs": "recording_alignment.json + recordings locales", "outputs": "resolve_alignment_plan.json + resolve_alignment_execution.json local", "authority": "DaVinciResolveScript local; AutoSyncAudio waveform; nunca confía sólo en el bool de retorno", "code": "pipeline/resolve_alignment_bridge.py · config/resolve_alignment_plan.schema.json", "trace_steps": []},
    {"id": "local_harness", "kind": "local_control", "title": "Windows Local Editing Harness", "summary": "Frontera segura entre contratos canónicos y la workstation Windows 11: doctor/capabilities, roots lógicos, jobs allowlisted, receipts idempotentes, Resolve discovery/OTIO smoke y ejecución sin shell arbitrario.", "inputs": "config/local + .local/local_config.json + jobs declarativos", "outputs": "local_environment + local_capabilities + local_job/local_receipt + .local/preflight.latest.json + efectos verificados en Resolve", "authority": "Python/PowerShell deterministas; nunca expone shell arbitrario y nunca sube raw media", "code": "pipeline/local/* · config/local/* · scripts/local/* · docs/local/README.md", "trace_steps": []},
    {"id": "virtual_timeline", "kind": "deterministic", "title": "Virtual A-roll + timeline abstracto", "summary": "Materializa V1/A1 como placeholders reemplazables por take_id y superpone V2 con assets o placeholders explícitos. Permite revisar el montaje antes de grabar sin fingir timecode real.", "inputs": "recording_pack.json + edit_manifest.json", "outputs": "virtual_timeline.json + timeline_preview.html", "authority": "Python; timeline estimado, NLE-neutral y not frame-accurate", "code": "pipeline/virtual_timeline.py · config/virtual_timeline.schema.json · build-video-kit.yml", "trace_steps": []},
    {"id": "placeholder_media", "kind": "deterministic", "title": "Placeholder media físico", "summary": "Genera slates PNG ligeros para cada take V1 y cada cue V2 no resuelto. Nunca sustituye assets reales y marca los placeholders como no publicables.", "inputs": "virtual_timeline.json", "outputs": "placeholder_media/*.png + placeholder_manifest.json", "authority": "Python/Pillow; identidad por take_id/cue_id", "code": "pipeline/placeholder_media.py · config/placeholder_media.schema.json", "trace_steps": []},
    {"id": "otio_export", "kind": "deterministic", "title": "OpenTimelineIO nativo", "summary": "Serializa el timeline abstracto a OTIO 0.18.1 con tracks, gaps, markers, MissingReference/ExternalReference y metadata de reemplazo; ejecuta round-trip read-back y valida duración, orden, clips y markers antes de promover.", "inputs": "virtual_timeline.json", "outputs": "timeline.otio + timeline_otio_validation.json", "authority": "OpenTimelineIO otio_json + Python; intercambio lossless del contrato usado, todavía pre-recording", "code": "pipeline/otio_export.py · docs/otio_export.md · build-video-kit.yml", "trace_steps": []},
    {"id": "resolve_bridge", "kind": "deterministic", "title": "DaVinci Resolve Bridge v0", "summary": "Valida bins, tracks, placements por frame y markers, materializa resolve_timeline.otio con referencias físicas V1/V2 y usa el importador OTIO nativo como vía primaria de ejecución local. Nunca sobrescribe un timeline existente.", "inputs": "virtual_timeline.json + timeline.otio + placeholder_manifest.json + multimedia resuelta", "outputs": "resolve_bridge_plan.json + resolve_timeline.otio + resolve_otio_validation.json; execution JSON solo local con --execute", "authority": "Plan/materialización: Python + OTIO; ejecución: DaVinciResolveScript local vía ImportTimelineFromFile", "code": "pipeline/resolve_bridge.py · config/resolve_bridge_plan.schema.json · docs/resolve_bridge.md", "trace_steps": []},
    {"id": "pre_recording_preview", "kind": "deterministic", "title": "Pre-recording Preview Render", "summary": "Aplana V2 sobre V1, renderiza un MP4 ligero con timing estimado, watermark permanente y audio silencioso. Si FFmpeg no puede decodificar un B-roll, sustituye solo ese tramo por un slate diagnóstico y registra la degradación.", "inputs": "resolve_bridge_plan.json + assets físicos", "outputs": "pre_recording_preview_plan.json + pre_recording_preview_validation.json canónicos; pre_recording_preview.mp4 solo en el artifact aislado del run", "authority": "Python + FFmpeg/ffprobe; preview no publicable y no frame-accurate", "code": "pipeline/preview_render.py · config/pre_recording_preview.schema.json · build-video-kit.yml", "trace_steps": []},
    {"id": "asset_readiness", "kind": "gate", "title": "Asset Readiness Gate", "summary": "Mide cobertura por cues y segundos, separa faltantes de degradación técnica/visual y bloquea grabación si falta evidencia crítica, hay media rota o la cobertura cae bajo el umbral. Low-res puede seguir como fallback visible.", "inputs": "virtual_timeline.json + resolve_bridge_plan.json + preview validation + assets físicos + config/asset_readiness.yaml", "outputs": "asset_readiness.json + asset_readiness.html", "authority": "Python + Pillow + FFmpeg/ffprobe; gate fail-closed para ready_to_record", "code": "pipeline/asset_readiness.py · config/asset_readiness.yaml · config/asset_readiness.schema.json", "trace_steps": []},
    {"id": "report_promote", "kind": "deterministic", "title": "Estado, trazas, reporte y promoción", "summary": "Persiste evidencia del run y solo promueve si script, Production Script, Recording Pack, Virtual Timeline, Placeholder Media, OTIO, Resolve Bridge, Pre-recording Preview, reporte y multimedia densa terminaron correctamente.", "inputs": "artefactos + gate final + resultado multimedia + recording/edit handoff", "outputs": "run_state + execution_trace + run_report + canon opcional", "authority": "Python/GitHub Actions", "code": "pipeline/report.py · build-video-kit.yml", "trace_steps": []},
    {"id": "narrative_memory_observability", "kind": "deterministic", "title": "Observabilidad de Narrative Memory", "summary": "Pages cruza biblioteca verificada con episodios aprobados para mostrar cobertura, calidad, uso real, disponibilidad y cooldown sin nuevas llamadas de modelo.", "inputs": "editorial/narrative_memory.jsonl + scripts/ aprobados", "outputs": "pages-site/memory/index.html + narrative-memory.json", "authority": "Python determinista", "code": "pipeline/narrative_memory_dashboard.py · editorial-review-hub.yml", "trace_steps": []},
    {"id": "pages", "kind": "pages", "title": "Artifact productivo → Review Hub → GitHub Pages", "summary": "Pages prefiere el ai-news-run real como fuente canónica y cae a scripts/multimedia canónicos si el artifact expiró o quedó fuera de la ventana. Editorial Regression queda como lane separada de QA.", "inputs": "ai-news-run-* + pricing + historia de Review Hub", "outputs": "review-site + cost_snapshot + pages-site + health + Narrative Memory", "authority": "Workflows deterministas", "code": "editorial-review-hub.yml · editorial-regression.yml", "trace_steps": []},
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
    "Guion + multimedia → editing_style versionado → edit_manifest pre-recording + style_warnings",
    "Production Script → Recording Pack + camera script + teleprompter autónomo",
    "Recording Pack → Recording Ingest Contract; grabaciones futuras se unen por take_id/retake",
    "Recording Pack + Ingest Contract → Recording Alignment Contract",
    "Grabaciones → Ingest Manifest → WhisperX word timestamps → Recording Alignment",
    "Cámara + lav seleccionados → Resolve Alignment Bridge → waveform sync verificado",
    "Repo canónico → Local Harness → doctor/capabilities → jobs allowlisted → receipts → Resolve",
    "Recording Pack + edit_manifest → Virtual A-roll + timeline_preview",
    "Virtual Timeline → placeholder media físico",
    "Virtual Timeline → timeline.otio → read-back/round-trip validation",
    "timeline.otio + placeholders/assets → resolve_timeline.otio → Resolve Bridge v0 plan",
    "Resolve Bridge plan → flatten V2>V1 → pre-recording preview MP4 + validation",
    "Preview + assets físicos → Asset Readiness Gate → radiografía + acciones P0/P1/P2",
    "¿Falla multimedia, Recording Pack, Virtual Timeline, Placeholder Media, OTIO, Resolve Bridge, Preview o Asset Readiness? → se preserva el run, no se promueve",
    "¿Script + Production Script + Recording Pack + Virtual Timeline + Placeholder Media + OTIO + Resolve Bridge + Preview + Asset Readiness + report + media pasan? → approved/promoción → ai-news-run → Review Hub/Pages",
]

DESIGN_DECISIONS = [
    ("Cobertura antes de tokens", "Una ventana insuficiente falla antes de cualquier llamada de modelo; evita aprobar episodios construidos sobre evidencia temporal demasiado incompleta."),
    ("Claim Ledger antes de la prosa", "Evita que marketing, inferencias o hipótesis se eleven silenciosamente a hechos."),
    ("Narrative Memory fuera del hot path", "La investigación costosa se amortiza como biblioteca versionada; producción valida, recupera pocos candidatos y exige que al menos uno se convierta en el gancho narrativo del episodio."),
    ("Cuatro jueces en vez de uno", "Evita que un score promedio esconda factualidad débil, mala retención o voz artificial."),
    ("Tres refiners con contextos distintos", "Aísla responsabilidades y evita oscilaciones entre reparar hechos y estilo."),
    ("Multimedia después del gate editorial", "No se gastan búsquedas/assets ni se deja que lo visual convierta un script rechazado en publicable."),
    ("Narración separada de dirección", "script.txt permanece limpio; edit_manifest y Recording Pack pueden orientar cámara/corte sin contaminar ni reescribir el ensayo aprobado."),
    ("Estilo observable antes de gatearlo", "La gramática audiovisual empieza como defaults + lint. Sus umbrales numéricos solo deberían endurecerse después de comparar varios episodios publicados con retención real."),
    ("Takes estables antes de alinear", "La grabación se divide determinísticamente en bloques cortos con IDs/claquetas reutilizables para que el ingest identifique retakes sin depender de un agente."),
    ("Ingest no equivale a selección artística", "El scanner conserva todos los retakes y sólo marca un technical_preferred provisional. Video y audio deben ser técnicamente utilizables y suficientemente largos; transcripción/alignment puede elegir otra toma. Los crudos nunca se borran ni se commitean."),
    ("Resolve ejecuta; el contrato neutral decide", "WhisperX aporta timestamps por palabra y Python decide fidelidad/retake. Resolve sincroniza cámara+lav por waveform y ejecuta postproducción local. Ningún transcript propietario de Resolve es requisito del pipeline."),
    ("Scratch audio conserva el reloj del video", "Aunque exista lavalier, la cámara debe conservar audio scratch para obtener timestamps relativos al video y permitir AutoSyncAudio por waveform sin inferir offsets."),
    ("Jobs locales sin shell arbitrario", "La interacción local se expresa como operaciones allowlisted con root_id + relative_path. MCP futuro podrá crear jobs y leer receipts, pero no ejecutar command/cwd/env arbitrarios."),
    ("A-roll virtual antes de A-roll real", "Cada take existe primero como placeholder reemplazable en V1/A1; los cues de B-roll se superponen sin borrar esa continuidad. La grabación real reemplaza y retemporiza, no redefine la arquitectura."),
    ("OTIO como frontera de intercambio", "virtual_timeline.json conserva semántica de producto; timeline.otio traduce a un modelo editorial estándar y round-trip validado."),
    ("Resolve desacoplado de CI", "CI valida un resolve_bridge_plan determinista y ejecutable. Solo la máquina local con DaVinciResolveScript crea el proyecto real; GitHub Actions nunca finge tener Resolve."),
    ("Preview efímero, contrato canónico", "El MP4 pre-recording vive en el artifact aislado para no inflar Git; su plan y validación sí se promueven. Lleva watermark, timing estimado y nunca cuenta como material final."),
    ("Readiness separa faltante de degradado", "Un fallback low-res sigue contando como media resuelta con warning; cero cues, evidencia crítica faltante, archivo roto o cobertura insuficiente bloquean ready_to_record y producen acciones priorizadas."),
    ("Discovery separado de derechos", "YouTube se usa para encontrar y rankear candidatos; metadata, atribución o duración breve no se tratan como permiso de descarga, edición, publicación o fair use."),
    ("Producción es la fuente de verdad de Pages", "Review Hub observa el artifact que realmente salió de Build AI News Video Kit; Regression queda como QA independiente."),
    ("Sin LLM como controlador", "Python decide routing, retries, límites, estado y publicación."),
    ("Promoción fail-closed", "Solo una cadena completa de éxito puede tocar el episodio canónico."),
    ("Schemas ejecutables antes de persistir", "edit_manifest, recording_pack, virtual_timeline, placeholder_manifest, resolve_bridge_plan, pre_recording_preview_plan y asset_readiness se validan contra JSON Schema antes de escribirse; documentación y runtime comparten el mismo contrato."),
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
