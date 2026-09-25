# Plan de integración revisado — biblioteca multimedia para edición

**Estado: propuesta; integración no activada.** Revisión del 25-09-2026 UTC
(24-09 en Ciudad de México), contra `main` en
[`e28f85400c60de5db0bfe152619e881b3e23e319`](https://github.com/jcval94/AI-News-Daily/commit/e28f85400c60de5db0bfe152619e881b3e23e319).
Sustituye el plan basado en `e5ba65f…`. El experimento sigue en
`experiment/youtube-artifacts`, PR #46 en borrador. Esta actualización cambia
solamente este documento; no mezcla ramas ni modifica producción.

## 1. Qué cambió y qué implica

| Ya existe en el snapshot revisado | Consecuencia para esta integración |
|---|---|
| `media_dedup.py`, usado por los builders normal y offline | Conservar la variante de mayor resolución; resolver identidad antes de asignar planos. La política del experimento de aceptar primero y descartar duplicados posteriores no basta. |
| `editing_style.yaml`, defaults y lint en `edit_manifest` | La cantidad descargada es una biblioteca de opciones; no obliga a aumentar cortes ni a ocupar planos de presentador. El estilo está en modo `observe`. |
| Recording Pack y teleprompter | Mantener `take_id`, anclas del guion y coherencia del estilo. Un cambio multimedia exige regenerar los derivados que lo consumen. |
| Timeline virtual y exportación OTIO | Conservar V1/A1 y colocar multimedia en V2; propagar identidad y procedencia mediante contratos explícitos. |
| Placeholder media y Resolve Bridge v0 | Los archivos faltantes producen slates no publicables. El puente materializa `resolve_timeline.otio` y usa importación OTIO nativa; no debemos construir un segundo puente. |
| `preview_render.py` y `asset_readiness.py` | Validar los medios reales y el resultado de la cadena completa, además de contar descargas. Ambos pasos intervienen en la promoción. |
| Preview ligero en Review Hub y edición local del script | Reutilizar la carga diferida de videos. Un borrador de navegador no es un nuevo guion aprobado que autorice regeneración automática. |

Resolve Bridge, placeholders, preview renderizado y Asset Readiness **sí están en
main en este snapshot**. No son fases pendientes de construir en este proyecto.
La ejecución real de DaVinci Resolve continúa siendo local: Actions prepara y
valida el handoff, no demuestra que una instalación particular de Resolve lo abra.

## 2. Punto de conexión actualizado

Mantener la adquisición cerca de Pexels, pero introducir una **biblioteca por
necesidad editorial** antes del bucle de materialización por slot.

El workflow llama `pipeline.review_media_dense_hardened`; este instala el runtime
endurecido y delega en el builder denso. En
`pipeline/review_media.py::build_review_media`, la inserción propuesta queda:

1. después de `normalize_multimedia_plan`, `enforce_opening_dense_media`,
   `enforce_synthesis_media` y `select_spread_media_budget`;
2. antes del bucle `for segment in normalized` que descarga los activos;
3. antes de la deduplicación final, créditos, `plan.json`, `manifest.json`,
   `write_edit_manifest` y ZIP.

La ruta `review_media_offline_dense` también existe y usa
`build_offline_review_media`. Debe consumir un pool previamente validado si está
disponible, sin depender del modelo ni repetir llamadas tras un fallo de cuota.
El workflow actual borra/reconstruye el directorio multimedia al pasar a la ruta
offline: el pool de trabajo debe vivir fuera de ese directorio reemplazable,
siempre dentro de `.pipeline-runs/<fecha>/<run-id>/`.

Buscar material preciso para personas, eventos y paralelos históricos ya elegidos
por el Director. Pexels sigue disponible para B-roll conceptual. La biblioteca
no elige nuevas historias, no cambia el Claim Ledger y no fuerza la utilización
de hechos de Narrative Memory que el guion aprobado no seleccionó.

## 3. Recorrido completo que hay que conservar

El orden de dependencia actual es:

1. Guion aprobado → plan multimedia → adquisición, asignación y deduplicación.
2. `plan.json`, `manifest.json`, créditos y `edit_manifest.json` con estilo.
3. Production Script → Recording Pack / teleprompter → `virtual_timeline.json`.
4. Desde la timeline virtual: placeholders físicos y `timeline.otio`.
5. Resolve Bridge consume ambos y materializa `resolve_timeline.otio`.
6. Preview de pregrabación → Asset Readiness con `--enforce` → informe del run.
7. Promoción únicamente si cumplen los resultados de los pasos requeridos.

`pipeline.footage` sigue siendo descubrimiento de candidatos YouTube, separado de
los archivos realmente descargados. Compartir IDs/procedencia cuando sea posible,
pero no contar sus enlaces como medios resueltos ni persistir metadatos efímeros
que el workflow actual retira al promover.

Cualquier sustitución de un archivo ya seleccionado debe regenerar los contratos
y derivados afectados en un nuevo run aislado. No editar solo `manifest.json`
dejando una timeline, ZIP, preview o fingerprint de estilo anterior. Mantener
`requires_recording_retime=true`; un preview técnicamente correcto no convierte
los tiempos estimados en timecodes de cámara ni resuelve la falta de A-roll real.

## 4. Bloqueos concretos detectados antes de integrar

### Identidad y deduplicación

La función actual `deduplicate_materialized_media` elimina los archivos perdedores
**y sus segmentos**. Por tanto, retiro la sugerencia anterior de reutilizar sin
más un activo en múltiples slots: esa repetición chocaría con el comportamiento
actual. Primera integración: activos distintos por slot y alternativas en el pool.
Reutilización editorial intencional requeriría después un contrato explícito de
instancias y una modificación coordinada del deduplicador.

También comprobé un riesgo al añadir fuentes: `_normalized_source_url` elimina
toda la query. Así `youtube.com/watch?v=AAA` y `...?v=BBB` se vuelven iguales;
lo mismo sucede con páginas Commons `index.php?curid=1` y `...?curid=2`.
Los grupos se unen por cualquiera de sus claves, por lo que añadir
`provider_asset_id` no neutraliza por sí solo una URL colisionada. **Corregir y
probar la normalización por proveedor antes de habilitar estas fuentes**:
conservar parámetros de identidad, retirar solo los de seguimiento y no unir
IDs incompatibles mediante una URL genérica.

La regla de mayor resolución se aplica entre variantes del mismo contenido
admisible. Comparar dimensiones decodificadas del archivo materializado, no las
cifras del original remoto si se descargó un proxy 360p. No sustituir un activo
válido por otro corrupto o no elegible. El hash perceptual ayuda a proponer grupos,
pero un recorte diferente con contenido editorial distinto requiere revisión.

Tras deduplicar, rellenar slots perdidos con candidatos distintos y recalcular
los gates. Conservar el registro de necesidades/slots antes de deduplicar: no
hacer desaparecer una necesidad crítica para que suba artificialmente la cobertura.
Si no se cubre, debe seguir visible como falta, o cambiar explícitamente el plan
por el flujo editorial autorizado. Una eliminación silenciosa no es una solución.

### Propagación de significado

`edit_manifest.py::_asset_payload` copia una lista cerrada de campos.
Hoy no transporta automáticamente `relation`, `quality`, hash del archivo,
identidad del pool ni el rango de origen del experimento. Añadirlos solo a
`manifest.json` perdería información al llegar a timeline/OTIO/Resolve.

Definir primero una extensión versionada y validada en los esquemas/consumidores
correspondientes. La revisión de pertinencia se realiza antes de asignar el slot:
el gate técnico Asset Readiness no determina si un rostro o acontecimiento es el
solicitado. Una foto de un memorial no resuelve por sí misma evidencia del desastre.

### Tiempo y rutas

El exportador OTIO actual crea `source_range` empezando en cero. La primera
integración debe materializar los fragmentos elegidos como archivos que comienzan
en cero, conservando aparte el offset respecto al original. No escribir un offset
nuevo en el JSON y asumir que OTIO, Resolve y preview ya lo interpretan.
Un futuro soporte de rangos requiere cambios coordinados y pruebas en los tres.

`manifest.file` es relativo al directorio multimedia del episodio. Timeline y
Resolve trabajan con rutas lógicas como `multimedia/<fecha>/...`, bajo el root del
run/repo. Traducirlas mediante el adaptador; no propagar rutas absolutas del runner,
URLs de artefactos temporales o enlaces simbólicos fuera del paquete. Comprobar el
handoff después de extraerlo en otro directorio.

## 5. Contrato propuesto para pool y asignación

Los siguientes campos/archivos son **propuestos**, no APIs ya implementadas.
Mantener un `asset_pool.json` versionado para candidatos y un manifiesto canónico
solo para seleccionados. Conservar fuera del ZIP principal las alternativas
pesadas o no elegibles; ofrecerlas como artefacto de revisión separado.

| Información | Mapeo / autoridad propuesta |
|---|---|
| Identidad del contenido | `source_asset_id` por proveedor/ID canónico; separar de `rendition_id` o SHA-256 de cada variante. El `asset_id` experimental está basado en bytes y cambia al mejorar resolución: conservarlo como procedencia, no como identidad semántica única. |
| Archivo y nombre | Conservar título original y nombre descriptivo en el pool. Al seleccionar, usar la asociación existente `media_filename(segment)` con beat/slot y extensión real. IDs de cue/take no dependen del nombre visible. |
| Proveedor y fuente | `provider`, `provider_asset_id`, `source_url`, autor, URL original y evidencia literal de catálogo. Identidad de federación/instancia cuando corresponda. |
| Resolución | Dimensiones reales decodificadas para ranking; dimensiones del original remoto en un campo distinto. Nunca ampliar para aparentar un original de mayor calidad. |
| Pertinencia | `exact/context` y limitación editorial persistidas hasta `virtual_timeline` y metadatos `ai_news_daily` de OTIO. Contexto no satisface un requisito de coincidencia exacta. |
| Derechos | Pasar por `pipeline/licenses.py::assess_license`; escribir `license_valid`, `requires_attribution` y créditos solo a partir de esa evaluación. |
| Video | Duración física, fragmento y offset original, rango utilizable y decisión de audio. Mantener separados el tiempo fuente y el tiempo en la timeline. |
| Asignación | `shot_number`, `slot_number`, `cue_id`, `beat_id`, `evidence_ids`, rol visual y anclas del guion aprobado; no renumerar silenciosamente al reemplazar una variante. |
| Reproducibilidad | SHA de guion/plan/estilo, versión de contrato/proveedor, queries, intentos, fallos, tokens disponibles y motivo de descarte. Cache de red acotada por run. |

El resolver de licencias actual rechaza `Fair use`, NC/ND, etiquetas ausentes o
no reconocidas. Esto excluye del montaje automático el retrato de Yamaguchi y
la imagen NC-ND de la prueba anterior, aunque sirvan como referencia. `No
restrictions` tampoco se convierte automáticamente en dominio público.
Normalizar códigos de cada API con evidencia verificable; nunca cambiar el
proveedor a `pexels` para obtener una aprobación. El éxito experimental de 22
medios descargados no es una medición de elegibilidad de producción.

## 6. Cantidad, estilo y calidad: reglas distintas

Preservar el presupuesto de producción, no copiar los defaults 20+4 del pack a
cada slot. Hay un presupuesto global del episodio: medios, bytes, tiempo,
consultas y llamadas de modelo. Agrupar por sujeto, periodo, geografía y función
editorial; incluir el requisito de exactitud y el estado de licencia en la clave.
No ejecutar el pack completo repetidamente para 54 slots.

Los límites actuales deben seguir leyendo sus configuraciones autoritativas:

| Política actual | Tratamiento en la integración |
|---|---|
| Default `MAX_MEDIA_DOWNLOADS=54`; piso 45 si presupuesto >=45; cinco medios en los primeros 20 s | Calcular después de asignar/deduplicar. Las alternativas del pool no cuentan. Mantener la reserva de presentador temprano y de síntesis que aplican los helpers actuales. |
| Estilo: presentador como base, defaults por rol, lint en `observe` | Buscar muchas opciones no obliga a utilizarlas todas. Mantener el estilo como observación, sin convertirlo aquí en un nuevo gate duro. |
| Asset Readiness: >=80% de cues y >=80% de segundos visuales resueltos; <=3 faltantes no críticos | Medir sobre las necesidades realmente planificadas. No reducir el denominador ocultando faltas. |
| Cero faltantes críticos (`evidence`, `historical_mirror`) y cero fallos técnicos | Contexto, placeholders o cards no prueban la identidad/evento requerido. Evaluar pertinencia antes de declarar el cue resuelto. |
| Lado corto inferior a 720 px: degradado, sin bloqueo por defecto | Admitir material pequeño pertinente y elegible; registrar tratamiento sin ampliación. `standard` del experimento (200/600 px) no equivale a calidad limpia en producción. |
| Video fuente inferior al 75% del tiempo previsto: advertencia por defecto | Preferir duración suficiente y conservar el aviso; no ocultar insuficiencia mediante repeticiones o congelados. Preview y NLE deben representar la misma decisión. |

El gate de licencia anterior a Asset Readiness permanece obligatorio aunque su
opción `missing_license_label_blocks` esté desactivada. `resolved_degraded` cuenta
como resuelto técnicamente, no como evidencia semántica verificada ni edición final.

Los PNG de `placeholder_media` son slates de planificación no publicables. No son
imágenes generadas para sustituir el sujeto buscado. El fallback gráfico existente
`generated_fallback` tampoco se debe presentar como archivo fotográfico del evento.
Este plan no activa generación de imágenes, ASR ni transcripción. Los datos Most
Replayed siguen siendo opcionales y exclusivos de las fuentes que los publiquen.

## 7. Entregas pequeñas y verificables

| Fase | Trabajo propuesto | Criterio de salida |
|---|---|---|
| A — Contrato y comparación aislada | Partir de main actualizado en una rama de integración nueva. Definir esquema del pool y compararlo con el flujo actual en un episodio aprobado. Modo propuesto `MEDIA_RETRIEVAL_MODE=shadow`, desactivado por defecto. | Sin modificar canónicos; medir exactitud, licencia, variedad, resolución, cobertura, bytes, tiempo y coste. Diferenciar descargado, elegible y asignado. |
| B — Identidad, calidad y adaptador | Corregir colisiones de URL; deduplicar variantes conservando la mejor resolución; preservar necesidades; resolver licencias y rutas; extender propagación de campos y esquemas. | Ninguna colisión entre videos distintos, ninguna mejora de calidad pierde procedencia, ninguna imagen contextual o no elegible resuelve evidencia. |
| C — Integración completa en staging | Activar la adquisición para personas/eventos explícitos; mantener Pexels para apoyo. Compartir material validado con fallback offline. Ejecutar todos los derivados hasta preview y Asset Readiness, sin promover. | Gates actuales pasan sin relajarse; faltantes siguen visibles; OTIO y Resolve materializado sobreviven round-trip y extracción en otra raíz. |
| D — Activación gradual | Feature flag por run, pool resumido en Review Hub, originales fuera de la carga inicial de Pages, registro de causas de fallback. | Sin regresión en rendimiento, cobertura o costes frente al baseline del mismo episodio. Piloto en Resolve local documentado aparte. |

Para la primera implementación recomiendo **A y B antes de tocar el workflow de
producción**. No fusionar el PR experimental completo sobre main por conveniencia:
reconciliar sus dependencias, workflows y contratos, y trasladar únicamente lo
necesario a una rama fundada en el main vigente. El experimento conserva su función
de laboratorio y sus resultados históricos.

Rollback: desactivar el modo integrado en un nuevo run y usar la adquisición
actual. No editar artefactos de un episodio ya promovido ni saltarse los gates.
Si la búsqueda falla o agota presupuesto, preservar diagnósticos y usar solo
alternativas elegibles; la aprobación del guion no cambia por un fallo multimedia.

## 8. Pruebas de aceptación antes de habilitarlo

- Dos videos con URLs `/watch?v=...` diferentes y dos páginas Commons por `curid`
  siguen siendo activos distintos; dos resoluciones del mismo original conservan
  la de mayor resolución física, incluso si llega después.
- Deduplicación normal y offline preservan cobertura/identidad de los cues; no
  publican archivos eliminados ni inflan 45/5 con copias o alternativas no asignadas.
- Evento raro sin exacto + contexto disponible permanece sin evidencia crítica.
  Caso sin resultados produce faltantes explícitos. Memorial posterior queda como
  contexto. Una mejora de resolución no relaja identidad ni licencia.
- Retrato Fair use, imagen NC-ND y licencia desconocida quedan fuera de los
  seleccionados automáticos. Créditos sobreviven al cambio de variante/proveedor.
- Imagen pequeña permitida llega a Asset Readiness como degradada; archivo roto
  bloquea; video corto conserva advertencia; proxy 360p nunca se reporta como 4K.
- Sustituir un activo regenera edit manifest, Recording Pack, virtual timeline,
  placeholders, OTIO, bridge, preview y readiness con IDs/anclas coherentes.
  Rutas fuera de raíz, contratos inválidos y fingerprints de estilo incompatibles
  fallan antes de promoción.
- Conservación de V1/V2/A1, marcadores, huecos, número de clips y tiempos en
  round-trip OTIO; el puente no sobrescribe una timeline de Resolve existente.
  Falta de A-roll sigue dejando `final_edit_ready=false`.
- Review Hub conserva videos con `preload=none`, máximo dos previsualizaciones
  concurrentes y respeto a ahorro de datos. No incrustar la biblioteca de videos
  como base64 ni cargar todas las alternativas al abrir la página. Los cambios
  locales de script siguen siendo borradores, sin autoridad de producción.
- Compilación, suite completa y tests existentes de dedup, estilo, edit manifest,
  recording pack, virtual timeline, OTIO, placeholders, Resolve, preview,
  Asset Readiness y promoción; después E2E de Actions sin promoción. Una prueba
  con API simulada de Resolve no reemplaza su aceptación en la instalación local.

Esta revisión documental no lanza descargas ni un E2E de integración:
los resultados anteriores siguen en `RESULTS.md`; no constituyen una validación
de la integración que aquí se propone. Las pruebas de aceptación anteriores son
requisitos de la implementación futura.

## Fuentes del diagnóstico

Código leído en el commit fijado al inicio, no deducido de conversaciones:

- [Workflow y orden de promoción](https://github.com/jcval94/AI-News-Daily/blob/e28f85400c60de5db0bfe152619e881b3e23e319/.github/workflows/build-video-kit.yml).
- [Builder y punto de inserción](https://github.com/jcval94/AI-News-Daily/blob/e28f85400c60de5db0bfe152619e881b3e23e319/pipeline/review_media.py), su builder offline y wrappers densos.
- [Identidad, resolución y eliminación de duplicados](https://github.com/jcval94/AI-News-Daily/blob/e28f85400c60de5db0bfe152619e881b3e23e319/pipeline/media_dedup.py).
- [Propagación del asset en edit_manifest](https://github.com/jcval94/AI-News-Daily/blob/e28f85400c60de5db0bfe152619e881b3e23e319/pipeline/edit_manifest.py) y [política de licencias](https://github.com/jcval94/AI-News-Daily/blob/e28f85400c60de5db0bfe152619e881b3e23e319/pipeline/licenses.py).
- [Política de Asset Readiness](https://github.com/jcval94/AI-News-Daily/blob/e28f85400c60de5db0bfe152619e881b3e23e319/config/asset_readiness.yaml) y su implementación; `editing_style.yaml` y sus consumidores.
- [Contrato Resolve Bridge](https://github.com/jcval94/AI-News-Daily/blob/e28f85400c60de5db0bfe152619e881b3e23e319/docs/resolve_bridge.md), módulos de OTIO, placeholders y preview; tests de promoción.
- `review_video_preview.py`, `review_hub_v12.py`, `review_hub_v13.py` y `AGENTS.md`.

Si main cambia antes de implementar, repetir la comparación de estos contratos y
el workflow. El SHA fija el alcance verificable de este plan; no presupone que
los cambios de otras ramas ya estén incorporados.
