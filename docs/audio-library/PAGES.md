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

La publicación canónica sigue siendo `Editorial Review Hub`, que genera episodios y construye todo el sitio. La publicación incremental usa el workflow `.github/workflows/audio-pages-refresh.yml`:

1. Se ejecuta automáticamente tras cambios en `catalog/audio/index.json`, el contrato o código de la biblioteca, y también manualmente.
2. Examina hasta 40 ejecuciones recientes del Review Hub en `main`, seleccionando un run con **job deploy exitoso** y artefacto completo `editorial-pages-snapshot-...` no expirado (retención 30 días).
3. Compara los bytes de `index.html` del artefacto contra los de la página pública actual para rechazar una base desactualizada o inaccesible.
4. Valida la integridad del sitio (raíz, navegación, episodios, salud, memoria, métricas, laboratorio); genera **únicamente** un nuevo directorio `audio/` y comprueba hashes de los archivos críticos del sitio y de cada página de episodio, sin modificar ningún otro directorio.
5. Despliega **el sitio completo recuperado**, no una carpeta parcial, usando las mismas acciones oficiales de Pages; prueba la URL pública de la biblioteca, el JavaScript y la raíz tras el despliegue.
6. Comparte el lock `editorial-review-hub-main` con el publicador pesado para evitar desplegar simultáneamente.

**Fail closed:** si no hay artefacto desplegado confiable, el sitio es inaccesible, falta alguna sección, el catálogo es inválido o la base pública es diferente, la acción falla y **no despliega**. En ese caso ejecutar el Review Hub completo; nunca sustituirlo por un Pages parcial. No descarga audios, no ejecuta modelos ni reconstruye multimedia.

La primera ejecución automática de este workflow al fusionarlo en main solo debe considerarse confirmada si GitHub Actions reporta despliegue y pruebas HTTP exitosos. La existencia del código o CI verde no prueba que la página pública se haya actualizado.
