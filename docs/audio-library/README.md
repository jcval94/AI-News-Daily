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

`rights_review.status` inicia `pending`. Para `approved` un editor humano debe aportar nombre, fecha y confirmar explícitamente **uso comercial, sincronización con video editado y modificaciones**. `rejected` bloquea el uso. NC/ND, fair use, reserva de derechos y licencias desconocidas se bloquean incluso ante una aprobación errónea. Otras licencias NO son aprobadas automáticamente: necesitan revisión humana y evidencia.

`approved` es una decisión editorial documentada; no garantiza ausencia de reclamaciones Content ID ni sustituye asesoría legal. Al publicar videos, cumplir la atribución que exija la licencia y volver a comprobar cambios de términos. El catálogo no prueba por sí mismo que el sitio siga disponible.

## Validación

```bash
python -m pipeline.audio_library --catalog catalog/audio/index.json
python -m unittest tests.test_audio_library -v
```

Los ejemplos sintéticos están en pruebas, **no** en el inventario canónico. El montaje de SFX en OTIO/Resolve y las descargas reales quedan para otra fase: no tocar pre-recording ni promotion gates.
