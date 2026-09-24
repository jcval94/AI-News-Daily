# Propuesta de integración al pipeline principal

Propuesta únicamente: ningún archivo de producción se ha modificado.
Código de referencia revisado en `main` a fecha 2026-09-24, commit
`e5ba65fdb9ae39bb813a5abb886386dc30c97000`. Esta rama experimental conserva su
historia independiente; antes de integrar habrá que reconciliar los cambios
recientes de main, no copiar versiones antiguas sobre ellos.

## Punto de conexión

La idea de conectarlo cerca de Pexels encaja con la arquitectura existente.
Propongo ampliar **la capa de adquisición después del plan multimedia aprobado**,
con una biblioteca compartida de candidatos por episodio. Pexels seguiría siendo
uno de los proveedores. No se ejecutaría durante redacción, crítica o refinamiento.

En el main revisado:

- `pipeline/review_media.py::build_review_media` planifica segmentos, aplica el
  presupuesto y llama `download_video_shot_asset` / `download_shot_asset` por slot.
- `pipeline/media.py` resuelve Pexels/Wikimedia y materializa los archivos.
- `build_review_media` escribe `plan.json`, `manifest.json`, créditos y llama
  `pipeline/edit_manifest.py::write_edit_manifest` antes de construir el ZIP.
- `edit_manifest` ya conserva rol visual, intención, tratamiento y readiness.
  `license_valid=false` o un archivo inexistente bloquean `usable_for_edit`.

La búsqueda ampliada debe entrar **antes del bucle de descarga por slot**, tras
normalizar los segmentos. Así una sola consulta por sujeto alimenta varios planos,
sin repetir búsquedas/modelos/descargas para cada aparición de la misma persona.

## Flujo propuesto

1. El guion pasa los gates actuales. El plan identifica `beat_id`, `evidence_ids`,
   `slot_number`, `visual_query`, tipo y rol visual. Python conserva autoridad sobre
   estado, presupuesto, reintentos, rutas y promoción.
2. Agrupar necesidades equivalentes por identidad, periodo, geografía y función
   editorial. Personas/eventos exigen identidad; una analogía conceptual puede
   buscar B-roll genérico. No agrupar solo por una palabra compartida.
3. Buscar una biblioteca por necesidad. Orden sugerido: fuentes específicas de
   catálogo/archivo para personas y eventos; Pexels para B-roll conceptual.
   Mantener todos los candidatos viables y seleccionar varios, con deduplicación.
4. Asignar activos a slots: preferir exactos; si falta resolución, permitir un
   original pequeño con tratamiento adecuado. Contexto solo en slots cuyo rol
   permita contexto/explicación, nunca para cubrir un requisito de evidencia exacta.
5. Validar licencia, existencia, decodificación y compatibilidad con el slot.
   Copiar/crear enlace del activo elegido con el nombre editorial existente;
   conservar `asset_id` y hash de origen. Los demás quedan como alternativas.
6. Emitir los contratos actuales y la biblioteca de alternativas. Pasar por
   `write_edit_manifest`, los gates multimedia y promoción existentes.

## Contrato del adaptador

No conviene entregar el manifiesto experimental directamente al editor automático.
Necesita un adaptador validado entre el pool de activos y los registros actuales:

| Paquete experimental | Registro de producción / condición |
|---|---|
| `asset_id`, `sha256` | Identidad estable de fuente y trazabilidad; conservar al renombrar |
| `path` | `file`, ruta relativa dentro del directorio multimedia del episodio |
| `source`, `url` | `provider`, `source_url` |
| `metadata.creator` / `creator` | `creator` y atribución |
| `license` | `license`; **no** implica `license_valid=true` |
| `kind` y formato real | `asset_type`, `mime_type` |
| `relation`, `quality`, `need` | Rol permitido, advertencias y tratamiento del director |
| Segmento y duración del video | Rango fuente utilizable, separado de los tiempos del guion |
| Slot del plan aprobado | `shot_number`, `beat_id`, `evidence_ids`, inicio/fin estimados |

Mantener un `asset_pool.json` con alternativas y un único `manifest.json` de
seleccionados. Un activo puede apoyar varios slots: no se duplica su descarga ni
se cuentan copias renombradas como recursos visuales distintos. Los nombres de
fuente describen el contenido; `media_filename(segment)` conserva la asociación
con beat/slot al preparar el handoff del episodio.

El conjunto de alternativas **no cuenta** para satisfacer el gate actual de
materiales materializados/asignados (45 cuando el presupuesto es >=45, y 5 en el
primer tramo de 20 segundos). Una imagen contextual no convierte en cubierto un
slot que requiere evidencia exacta. No se cambia la aprobación del guion por un
fallo multimedia. El timing sigue siendo estimado y
`requires_recording_retime=true` hasta alinear una grabación real.

## Despliegue gradual sugerido

1. Flag desactivado por defecto, por ejemplo `MEDIA_RETRIEVAL_EXPERIMENT=1`:
   ejecutar sobre un episodio aprobado, guardar pool en `.pipeline-runs/...`,
   comparar contra Pexels actual sin sustituir la entrega canónica.
2. Validar equivalencia del adaptador, licencias, rutas, identidad y ausencia de
   duplicados; medir cobertura exacta por slot, variedad, resolución, tiempo y
   coste real de llamadas. Probar permisos denegados y resultados vacíos.
3. Activar para personas/eventos explícitos; mantener Pexels para los demás slots.
   Presupuesto compartido de proveedores/modelos y caché por episodio para evitar
   multiplicar el coste de los packs independientes por 54 slots.
4. Incorporar alternativas elegibles a Review Hub con evidencia, vista previa y
   etiquetas visibles. El editor elige la toma sin reescribir hechos del guion.

## Límites que quedan antes de producción

- La pertinencia de video se evalúa con metadatos; aún no hay una localización
  semántica de escenas. El fragmento inicial puede contener introducción o título.
- Los videos descargados son proxies 360p; para edición HD habría que añadir una
  adquisición posterior del original elegido, manteniendo identidad y licencia.
- Todos los paquetes conservan `license_validated=false`. La autorización de uso
  debe resolverse con las reglas de `pipeline/licenses.py` ampliadas por proveedor,
  sin convertir disponibilidad pública en licencia de reutilización.
- `context` es una propuesta editorial explícita. La verificación del vínculo con
  el guion y de afirmaciones históricas corresponde al contrato editorial existente.
- La primera versión deduplica videos por URL/bytes, no montajes casi idénticos.
- Las cuotas de cantidad pueden quedar incompletas y los artefactos Actions
  caducan a los 7 días. Elegir permanencia del material seleccionado por separado
  de los metadatos/resultados versionados; no guardar videos pesados en Git.

Nada de esto habilita generación de imágenes ni transcripción por defecto.
