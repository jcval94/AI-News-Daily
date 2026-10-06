# Notebook Story Flow · epopeya abierta + viaje del héroe

Adaptación del notebook `Creador_de_Guiones_con_ChatGPT.ipynb` de JC. Todo el
código, contratos, pruebas, guiones y resultados vive aquí; el único enlace externo
es `.github/workflows/notebook-story-flow.yml`. No altera el pipeline, sus contratos,
la identidad editorial ni los paquetes de grabación de producción.

## Hipótesis y control

Una historia documentada, interrumpida justo antes de su desenlace, puede ganar
curiosidad y hacer que el regreso final tenga más significado. Puede también
demorar demasiado la primera evidencia actual. Ese costo se mide explícitamente.

El grid search anterior favoreció historia breve como giro intermedio. Este
experimento ensaya deliberadamente otra estructura; no afirma haber superado ese
resultado ni cambia el tratamiento ganador en producción.

Si recibe un episodio, usa su snapshot de noticias, pregunta central y Claim Ledger
congelados. No toma el último episodio como sustituto silencioso del próximo:
`workflow_run` descarga **el intento exacto** que acaba de crear producción, incluso
si el guion no fue aprobado. Si no hay fuentes/guion utilizable, registra bloqueo
sin usar modelos. El replay inicial usa explícitamente el último episodio aprobado.

## Qué se recupera del notebook

| Notebook | Adaptación |
| --- | --- |
| Celda 20: `PromptFactoryEpic` y `PromptFactoryHero` | Ideas núcleo, motivo, ranking de epicidad/conexión, conflicto, tres pilares y pregunta central |
| Celdas 20/22: `step9_epica` | Historia de **350–400 palabras**, terminada antes del desenlace |
| `step10_reconexion` | Puente histórico → problema actual, sin spoiler |
| `hook_problema`, `hook_cita` | Problema humano y reflexión; cita solo si existe texto verificable |
| `idea_A`, `dato_1`, `idea_B_explica`, `idea_B_desafio`, `dato_2`, `idea_C` | Desarrollo continuo con datos atribuidos, límites y microexperimento |
| Celda 6: voz, puentes, humor, timing y CTA | Perfil editorial del repo, 150 palabras/minuto, suscripción natural; ningún link inventado |
| `cierre` | Regreso documentado a la historia y síntesis evolucionada; nuevo bloque explícito `story_payoff` |
| `seo_snippet` | Metadatos separados del texto hablado |
| Celdas 8/9: fragmentos de 8 segundos y varias consultas | `media_queries.json`, hasta tres consultas por fragmento, sin descargas ni atribuciones ficticias |
| JSON de bloques `template`/`response` | `flow.json` compatible conceptualmente con el flujo original, ordenado y editable |

No se copia el notebook completo: contiene credenciales, salidas antiguas y
dependencias externas de Colab/Drive/Flask no incluidas en el adjunto. Su SHA-256
se conserva para identificar la fuente. Se elimina la introducción duplicada;
la epopeya ya abre el guion. Se agrupan los bloques en una escritura coherente,
conservando respuestas separadas, en lugar de llamadas independientes sin contexto.

## Contrato y buenas prácticas

1. Cobertura parseable de fuentes con el resolver de producción; 75% como mínimo
   para ventanas nuevas. Un replay canónico aprobado usa su snapshot aprobado.
2. Narrative Memory validada, retrieval acotado y cooldown del historial aprobado.
   Se excluyen paralelos abstractos con menos de tres hechos documentados; cada
   candidato tiene un catálogo con índices históricos explícitos desde 1.
   El experimento nunca escribe uso aprobado en la memoria.
3. Plan Pydantic: historia recuperada, ledger sobre noticias reales, tres pilares;
   referencias históricas numeradas desde 1. Setup y desenlace deben ser disjuntos.
   Para replay, Python vincula la pregunta y el ledger originales: el modelo no
   puede reescribirlos. El contexto de preparación omite el antiguo tratamiento
   de apertura/memoria para evitar anclar la nueva historia al paralelo anterior.
4. El desenlace se reserva para `story_payoff`; se rechaza su uso en otros bloques.
   Los IDs no prueban veracidad: el auditor revisa también la prosa.
5. Orden y longitudes por bloque, referencias, final literal de apertura, primera
   evidencia actual, CTA y duración se validan con Python. Un solo intento de
   reparación estructural; nunca truncar ni rellenar mecánicamente el texto.
6. Auditor factual separado. Una reparación exclusivamente factual y un recheck,
   si hacen falta; voz/SEO/atención se evalúan solo después del pase factual.
7. Runtime ADK del repo: mismo modelo configurado, reintentos transitorios y reparación
   de schema acotados, cero reintentos por cuota permanente, traza y uso parcial.
   Máximo ocho llamadas lógicas, tres intentos por llamada, 10,000 tokens de salida
   por intento; se detienen nuevas llamadas cuando el uso emitido llega a 180,000
   tokens. Es un presupuesto operativo, no una garantía de costo monetario exacto.
8. `ready_for_review` requiere revisión factual low, historia >=8.7,
   editorial/voz >=8.7, atención/SEO >=8.5, AI smell low, apertura inconclusa en
   el clímax, puente logrado y payoff sin spoilers anticipados.
9. Toda salida sigue con `publishable: false`. No sobrescribe `scripts/`,
   `multimedia/`, historial, estados de producción ni contratos de recording ingest.

Si un registro histórico no contiene suficiente material para un conflicto y un
desenlace, el modelo no debe completarlo con ficción. La auditoría rechaza el
guion. La mayor libertad contractual es narrativa, no factual.

## Ejecución

Desde la raíz del repositorio, con las dependencias de `requirements.lock`:

```bash
# Inspeccionar próximo episodio, sin costo de modelos.
python -m experiments.notebook_story_flow.run --target-date 2026-10-06 --dry-run

# Replay con la misma pregunta, evidencia y fuentes de un episodio existente.
python -m experiments.notebook_story_flow.run --episode-dir scripts/2026-09-25

# Reproducir el intento exacto descargado desde Actions.
python -m experiments.notebook_story_flow.run --production-artifact /tmp/production-attempt

# Fecha manual fuera de martes/viernes.
python -m experiments.notebook_story_flow.run --target-date 2026-10-05 --source-mode recent_window

python -m unittest discover -s experiments/notebook_story_flow -p 'test_*.py' -v
```

Autenticación: `OPENAI_API_KEY` del entorno/Actions; nunca la clave del notebook.
Modelo: `OPENAI_MODEL` del repo, con su default de producción. No requiere Colab,
ngrok, navegador, Drive ni instalación adicional de proveedores multimedia.

## Ejecución junto al siguiente episodio

`Notebook Story Flow Experiment` escucha la finalización de `Build AI News Video
Kit` en `main`, únicamente en este repositorio y para `schedule`/`workflow_dispatch`.
Descarga el artifact `ai-news-run-<fecha>-<id>` y crea el guion experimental después
del intento de producción, en su propio workflow. No bloquea su promoción ni Pages.
El próximo episodio programado tras esta implementación es **2026-10-06, 09:00
America/Mexico_City**; GitHub puede demorar el comienzo del cron.

El primer push del código a `main` ejecuta un replay E2E del último aprobado.
Los pushes de resultados están excluidos del trigger para evitar ciclos y gastos.
Las PR solo ejecutan pruebas deterministas, sin secretos ni modelos. El workflow
tiene también ejecución manual y `dry_run`. No crea otro scheduler de episodios.

## Salidas y evaluación

`results/<episode-date>/<run-id>/` contiene snapshot de entradas y hashes, prompt de
preparación, `story_plan.json`, borradores, `flow.json`, `script.txt`, guion de cámara
con tiempos, secciones, consultas multimedia, gate determinista, revisión factual,
revisión narrativa, comparación pareada si hay control, traza y `run_report.json`.
Actions guarda artifact por 90 días y resultados en esta carpeta del repositorio.

Estados: `dry_run`, `blocked_inputs`, `missing_openai_secret`, `rejected_structure`,
`rejected_factual`, `rejected_narrative`, `ready_for_review`, `failure`.
Rechazo/falla conserva evidencia y marca el workflow experimental como fallido;
un bloqueo de fuentes es un skip explícito, nunca aprobación. La producción sigue
con su propio estado. Una comparación no disponible no cambia el gate del guion.

Los scores de jueces y la preferencia pareada son **proxies**, no retención medida.
El reporte permite revisar segundos de historia, primera evidencia y payoff.
Antes de integrar este formato en producción, contrastar varios episodios y revisar
personalmente veracidad, naturalidad y el desenlace. Este trabajo no incluye
transcripción, alignment, render final ni descargas: reutilizar las capas existentes
en una promoción posterior expresa, evitando producir multimedia de un guion rechazado.
