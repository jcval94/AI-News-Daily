# Biblioteca multimedia integrada

La adquisición documental es optativa y posterior a la aprobación del guion.
En **Build AI News Video Kit**, el input `media_retrieval_mode` permite:

- `off` (por defecto): adquisición existente.
- `shadow`: buscar y evaluar alternativas, sin asignarlas al montaje.
- `integrated`: asignar fuentes precisas y elegibles a personas/eventos y roles críticos; Pexels sigue para apoyo conceptual.

Los sujetos explícitos deben aparecer literalmente en la narración aprobada. No
se inventan historias para completar la biblioteca. Necesidades compartidas agrupan
consultas; una imagen contextual o un memorial no satisface evidencia exacta.

`asset_pool.json` vive fuera de la carpeta multimedia reemplazable, dentro del run
`.pipeline-runs/<fecha>/<run-id>/media-pool/`. El fallback offline reutiliza ese
pool y sus necesidades sin llamadas al modelo. Inputs/estilo distintos requieren
un run nuevo. Archivos elegidos y sidecars se copian a rutas relativas del paquete.
La biblioteca de alternativas se conserva en un artefacto separado de siete días.

Límites globales iniciales: 24 archivos, 128 MiB materializados, 10 minutos,
32 llamadas de modelo, ocho necesidades, hasta cuatro imágenes y un video por
necesidad. Los proveedores tienen límites adicionales de entrada y red; no se
trata de un límite de tráfico total. El proceso guarda resultados parciales antes
de agotar tiempo. No hay APIs comerciales nuevas. Se usa el modelo configurado
en el repo; se registran intentos y tokens disponibles, sin inventar un costo.

Transcripción **apagada**. Videos cortos primero; largos en fragmentos de hasta
30 segundos, materializados desde cero. El offset original queda en procedencia.
Most Replayed solo conserva datos realmente publicados por YouTube y no se estima
para otras fuentes. Proxies pequeños se conservan como degradados, sin ampliarlos
para aparentar calidad. Originales alternativos no se precargan en Pages.

La licencia se evalúa antes de asignar: Fair use, NC/ND, desconocidas y “No
restrictions” no obtienen permiso automático. Coincidencia por catálogo no es
verificación humana universal ni prueba de todas las afirmaciones del guion.

`media_provenance` v1 acompaña al seleccionado en edit manifest, timeline virtual
y metadatos `ai_news_daily` de OTIO. Rondas de Resolve usan su mapeo de archivos
locales existente: al extraer en otra raíz se regenera `resolve_bridge` para esa
máquina. V1/A1, cue/take IDs y la obligación de retimar la grabación se conservan.

Pages muestra **Biblioteca multimedia** en la pestaña Media: descargados,
elegibles, asignados, fuentes, calidad y faltantes. No cuenta candidatos como
archivos resueltos. Las ediciones de guion en el navegador siguen siendo borradores.

Prueba reproducible: **Media Integration Staging**, sobre el episodio aprobado
2026-09-04. Ejecuta adquisición densa, Production Script, Recording Pack, timeline,
placeholders, OTIO, Resolve Bridge, preview, Asset Readiness y construcción del
Review Hub; repite el mapeo/readiness en otra raíz. No promueve episodios. Una
corrida solo pasa si conserva 45/5, readiness y al menos una asignación documental.
La aceptación en una instalación real de Resolve continúa pendiente del usuario.

Rollback: escoger `off` en un run nuevo; nunca editar en sitio un episodio promovido.
El laboratorio previo permanece independiente en la rama experimental/PR #46.

## Auditoría de gasto

`media_cost_audit.json` registra cada intento antes de enviarlo, con necesidad,
etapa (planificación, selección o inspección visual), modelo, hora, ID de respuesta,
tokens de entrada/salida/caché, resultado y costo estimado. Una interrupción o un
error sin uso reportado queda como costo desconocido, nunca como llamada gratuita.
El costo usa `config/cost_rates.json`; no equivale a una factura ni incluye otros
runs, escritura del guion, planificación editorial o almacenamiento. La traza
`planning_trace.json` conserva por separado los intentos del planificador multimedia,
incluso si falla. Pages muestra el subtotal documental y los intentos sin precio.

La prueba de staging ejecuta dos casos separados: catálogo controlado sin modelo
y búsqueda semántica real. Ambos exigen el panel de Pages, 45/5, una asignación
documental y readiness tras cambiar de raíz. Los artefactos identifican cada caso.

Pages primero verifica y reutiliza los archivos del episodio extraído: licencia,
decodificación, identidad única, cantidad, apertura y readiness cuando existe.
Conserva el pool y su auditoría sin nuevas llamadas. Un replay de integración se
etiqueta como prueba no promovida, y no se presenta como ejecución de producción.
Si el paquete es incompleto o inválido, se usa la reconstrucción existente.

Antes de adquirir, el plan documental exige sujetos y restricciones presentes en
la narración. Hay como máximo una reparación del plan inválido, registrada en la
traza. Las fotos de esculturas antiguas se clasifican como `object_photo`; la
identidad sigue dependiendo de evidencia literal del catálogo y de los controles
de licencia. Los rechazos de adquisición conservan el plan y las decisiones para
evitar repetir llamadas solo para diagnosticar un error.
