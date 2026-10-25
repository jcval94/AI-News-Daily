# Biblioteca de música y efectos (contrato v1)

**Estado: catálogo de metadatos, sin pistas curadas.** `catalog/audio/index.json` empieza vacío a propósito. Esta implementación no verifica canciones, no descarga archivos ni concede derechos de uso. No es la biblioteca de narraciones TTS (`.local/tts/library/`).

## Autoridad y almacenamiento

- Git versiona el índice JSON, esquema, validador, documentación y pruebas.
- Los WAV/MP3, evidencias descargadas cuando corresponda y QA local viven bajo `.local/audio/` (ignorado por Git).
- `local_relpath` es opcional, relativo a `.local/audio/` y nunca una ruta absoluta. CI y Pages no leen archivos locales.
- IDs estables para deduplicación. Este catálogo es independiente del `asset_pool.json` visual, que es por ejecución.
- Sin red, scraping, claves API, releases, descargas ni cambios a la timeline productiva.

## Curación y derechos

Cada candidato registra obra, creador, tipo (música, SFX, transición o ambiente), etiquetas, intensidad, duración opcional, proveedor, URL exacta de la obra, identificador de licencia, URL de términos, URL de evidencia y fecha de consulta. El anuncio general de un proveedor no sustituye evidencia por pieza.

`rights_review.status` inicia `pending`. Para `approved` un editor humano debe aportar nombre, fecha, ámbito de plataformas (incluido YouTube), base de licencia, evidencia **de esa pista específica** y un resumen verificable, y confirmar explícitamente **uso comercial, sincronización con video editado y modificaciones**. `rejected` bloquea el uso. NC/ND, fair use, reserva de derechos y licencias desconocidas se bloquean incluso ante una aprobación errónea. Otras licencias NO son aprobadas automáticamente: necesitan revisión humana y evidencia.

`approved` es una decisión editorial documentada; no garantiza ausencia de reclamaciones Content ID ni sustituye asesoría legal. Al publicar videos, cumplir la atribución que exija la licencia y volver a comprobar cambios de términos. El catálogo no prueba por sí mismo que el sitio siga disponible.

## Validación

```bash
python -m pipeline.audio_library --catalog catalog/audio/index.json
python -m unittest tests.test_audio_library -v
```

Los ejemplos sintéticos están en pruebas, **no** en el inventario canónico. El montaje de SFX en OTIO/Resolve y las descargas reales quedan para otra fase: no tocar pre-recording ni promotion gates.

## Política de aprobación reforzada (v1 compatible; revisión v2)

El esquema mantiene `schema_version: 1`, y las entradas `pending` o `rejected` no requieren nuevos campos. **Las entradas `approved` sí requieren ahora**:

- `rights_basis`: `creative_commons`, `provider_specific` o `direct_permission`. La última requiere `permission_record_url` público/verificable; no introducir documentos privados ni secretos al repositorio público.
- `usage_platforms` con `youtube`, y los tres permisos explícitos sobre comercialización, sincronización y modificaciones.
- `track_specific_evidence_confirmed: true`, `evidence_description` suficientemente concreto, `reviewer` y `reviewed_on`. Si `license.checked_on` es posterior a la revisión, el registro debe reaprobarse; una modificación de términos no se presume inocua.
- `attribution_required`, y texto `license.attribution_text` si corresponde. CC BY siempre requiere crédito. CC BY-SA además requiere reconocer expresamente obligaciones share-alike (`share_alike_obligations_acknowledged: true`); no se infiere que cualquier adaptación cumple por sí sola.
- `content_id_review`: `unchecked`, `no_known_claim`, `possible_claim` o `active_claim`. El estado `unchecked` o `active_claim` no permite `approved`; `possible_claim` necesita `content_id_risk_accepted: true` registrado por el editor. `no_known_claim` significa ausencia de reclamación conocida, **no** garantía de ausencia futura.
- `preview_redistribution_allowed` explícito y separado de autorización para montar el video. Aunque sea `true`, **Pages no publica audio** en esta fase.
- Opcionalmente `license.evidence_sha256` puede identificar una copia lícita de la evidencia archivada fuera de Git; no prueba titularidad.

La validación rechaza aprobación contradictoria, campos esenciales ausentes, evidencias fechadas posteriormente a la revisión y variantes obvias de licencias NC/ND, fair use, no-reservadas o desconocidas. Las licencias específicas de un proveedor no se autorizan por nombre: deben documentarse pista por pista y revisarse manualmente.

**Consejo editorial:** conserva URL y fecha, escribe un resumen original breve de por qué esos términos aplican al archivo exacto, y verifica tanto licencia de composición como grabación. Si algún uso depende de condiciones del proveedor, registra la limitación y evita aprobar hasta entenderla. Esta política es un control técnico-editorial conservador, no asesoría jurídica ni protección absoluta contra Content ID.

El comando de validación y el CI no hacen solicitudes de red, no descargan pistas y no marcan derechos como aprobados automáticamente.
