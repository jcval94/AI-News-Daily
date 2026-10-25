# Biblioteca sonora en Pages (v1)

Este PR añade **una vista estática separada** bajo `/audio/index.html`, enlazada desde la navegación de episodios en escritorio y móvil. Se crea dentro de `pages-site/audio/` antes de subir el artefacto normal de Pages.

- Recibe exclusivamente `catalog/audio/index.json`; las rutas locales y datos de revisión internos no se utilizan para descargar audio.
- Filtros de un clic por tipo, emoción, intensidad, proveedor y estado de derechos; búsqueda textual, conteo y estado vacío honesto.
- Escapa metadatos no confiables; los enlaces HTTPS a fuente, términos y evidencia se abren con `noopener noreferrer`.
- No publica audios ni añade reproductores para pistas no verificadas.
- No cambia TTS, pre-recording, timeline, edición, selección editorial ni promoción.
- Si el catálogo está vacío, la vista sigue siendo útil como puerta de entrada y explica qué falta.

Ejemplo local:
```bash
python -m pipeline.audio_library_pages --catalog catalog/audio/index.json --output-dir /tmp/pages-site/audio
python -m unittest tests.test_audio_library_pages -v
node --check /tmp/pages-site/audio/audio.js
```

**Integración**: esta rama depende del PR de contratos del catálogo. Fusionar primero dicho PR; no se debe promover la UI si el validador base no está presente.

## Actualización

La primera publicación se ejecuta al fusionar este PR porque cambia el workflow de Pages. Las ediciones posteriores del catálogo **sí disparan CI de validación**, pero no inician por sí solas una producción multimedia costosa: aparecen en la siguiente reconstrucción ordinaria de Pages o en un `workflow_dispatch` solicitado expresamente.
