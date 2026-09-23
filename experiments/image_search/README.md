# Experimento independiente: búsqueda precisa de imágenes

Recibe una descripción, consulta catálogos públicos, contrasta evidencia de la ficha,
revisa el tipo de imagen y descarga archivos existentes. **No genera imágenes** y no
utiliza el pipeline de producción ni su fallback de generación. Vive junto al
experimento de videos, con workflow, dependencias y artefactos propios.

## Fuentes implementadas

| Fuente | Uso principal | Evidencia y derechos |
|---|---|---|
| Wikimedia Commons + Wikidata | Personas, lugares, acontecimientos, mapas y fotografías | Nombre canónico, imagen P18 cuando se resuelve una entidad, títulos y descripciones; licencia por archivo |
| Metropolitan Museum of Art | Objetos, arte e historia material | Cultura, periodo, fechas de creación y ficha del objeto; solo `isPublicDomain=true` con imagen disponible |
| Art Institute of Chicago | Arte y objetos históricos | Periodo, origen, descripción y fechas; solo `is_public_domain=true`; imágenes IIIF |
| Library of Congress | Fotografías y documentos históricos | Título, descripción y materias del catálogo; derechos propios de cada ficha |

Los proveedores son alternativas reales: un bloqueo o fallo se registra y permite
consultar los otros. No hay proxies, cookies, evasión de desafíos ni claves de los
catálogos. El Met usa `/v1.1/search`, el endpoint paginado anunciado en septiembre de
2026; su búsqueda `/v1/search` antigua se retira el 1 de octubre de 2026.

## Qué significa precisión aquí

1. Un plan tipado conserva el tema completo, interpreta errores ortográficos obvios
   y expresa nombre canónico, contexto, periodo y tipos de imagen. Si la petición
   es ambigua, falla con una explicación; no escoge arbitrariamente un significado.
2. Consulta hasta 20 candidatos por fuente. Wikidata puede aportar una entidad exacta
   y su imagen declarada; si no puede resolverse, queda registrado y se exige evidencia
   explícita en las fichas. Los candidatos nunca salen de una URL inventada por el modelo.
3. Un evaluador semántico propone coincidencias directas, incertidumbre o rechazo a
   partir de metadatos. Python exige una **cita literal existente** en un campo de
   tema, título o descripción; autoría/licencia no sirven como prueba de lo representado.
4. Para personas se exige el nombre canónico completo en la atribución, o la imagen
   vinculada por P18 a la entidad exacta. Una referencia indirecta, un homónimo o un
   objeto creado por esa persona no equivale a una fotografía de ella. No se usa
   reconocimiento facial para atribuir identidades.
5. Para historia, las fechas del objeto se contrastan con el periodo solicitado.
   La fotografía actual de una escultura romana puede ser pertinente; una pintura
   renacentista inspirada en Roma no pertenece a la Antigüedad. Las ruinas identificadas
   pueden aceptarse como restos históricos, no como fotografías tomadas en la época.
6. Descarga temporalmente y decodifica el archivo. La inspección visual clasifica el
   medio y la utilidad: fotografía de persona, sitio u objeto, obra histórica o mapa.
   Rechaza estatuas cuando se pide una foto de una persona, páginas de error, texto,
   memes y renderizados evidentes. **No identifica caras ni certifica fechas por apariencia.**
7. El código combina todas las condiciones, descarta duplicados y mueve al artefacto
   únicamente los archivos aceptados. Preserva los bytes descargados y su SHA-256.

Ejemplos de pruebas: **Einstein** → fotografías atribuidas a Albert Einstein;
**Roma Antigua** → objetos romanos de época o restos históricos documentados, con su
tipo indicado. No se sustituye por turismo genérico de Roma, Grecia antigua, personas
parecidas, películas o ilustraciones de IA.

No se promete precisión universal ni se interpreta la confianza del modelo como
porcentaje medido. Las fichas públicas pueden contener errores y la revisión semántica
y visual también puede equivocarse. El sistema prioriza devolver menos imágenes ante
evidencia insuficiente. Un resultado parcial conserva artefactos, pero el workflow
marca que no se obtuvo la cantidad solicitada.

## Uso en GitHub Actions

Workflow: **Experiment — Precise image search artifacts**.

- `description`: descripción libre, hasta 2000 caracteres.
- `count`: cantidad deseada, 1–20; cinco por defecto.
- `sources`: combinación de `commons,met,artic,loc`.

Mientras el workflow solo exista en `experiment/youtube-artifacts`, edita
`experiments/image_search/live-request.json` en esa rama y haz commit. Cambiar
`request_id` inicia una ejecución. Admite 1–3 casos secuenciales. Cuando el workflow
esté en la rama por defecto, se podrá usar **Actions → Run workflow**.
Los cambios ordinarios de código no inician descargas. Una nueva petición cancela
la ejecución anterior del experimento de imágenes en la misma rama.

Utiliza el secret existente `OPENAI_API_KEY` para interpretación y revisión, con
`vars.IMAGE_SEARCH_MODEL` o `gpt-5.4-mini`. El modelo analiza texto e imágenes
existentes; no llama a generación de imágenes. El cómputo corre en Actions y consulta
APIs externas, cuyo uso puede tener coste. No necesita un servidor propio.

## Artefactos y límites

- `images/<proveedor>_<id>/source.jpg|png|webp`, ficha y verificaciones individuales.
- `gallery.html`: galería local con origen, periodo/tipo y motivo de selección.
- `plan.json`, `candidates.json`, `assessments.json`, `manifest.json`, `SUMMARY.md`,
  `ATTRIBUTION.md`, `SHA256SUMS`.
- Estado de cada proveedor y motivo de descarte; ninguna URL de referencia cuenta
  como descarga si no hay archivo validado.
- Máximo 25 MiB por imagen, 40 millones de píxeles; mínimo 200 píxeles en el lado
  corto y 600 en el largo. JPEG/PNG/WebP estáticos, sin SVG o HTML ejecutable.
- Hasta 80 candidatos y 40 intentos; quince minutos de presupuesto global comprobado
  entre intentos y veinticinco de timeout del job.
- Hosts HTTPS permitidos por proveedor, validación de redirecciones y contenido real.
- Deduplicación por bytes, píxeles, hash perceptual y nombres de versiones
  recortadas/restauradas del mismo archivo en Commons. Puede descartar
  imágenes distintas muy parecidas; se conserva el motivo.
- Imágenes de tamaño completo cuando el proveedor lo facilita dentro del presupuesto;
  Commons y IIIF pueden entregar derivados oficiales, etiquetados como tales.
- Retención de siete días. Una licencia desconocida conserva esa condición; el catálogo
  y la disponibilidad pública no sustituyen una revisión de derechos de reutilización.

## Verificación local

```bash
python -m pip install -r experiments/image_search/requirements.txt
python -m unittest discover -s tests -p 'test_image_search_experiment.py' -v
python -m experiments.image_search.run --description 'Roma Antigua' \
  --count 5 --output image-search-output/rome-001
```

El directorio de salida debe ser nuevo. Los resultados reales de Actions se registran
en `RESULTS.md` tras descargar y revisar los artefactos; las pruebas unitarias no
demuestran por sí solas precisión en imágenes reales.

Documentación primaria consultada:
[Commons API](https://commons.wikimedia.org/wiki/Commons:API/MediaWiki),
[Wikibase API](https://www.mediawiki.org/wiki/Wikibase/API),
[depicts P180](https://diff.wikimedia.org/2019/09/06/structured-data-on-commons-pt-4-depicts-statements/),
[Met Collection API](https://metmuseum.github.io/),
[Art Institute API e IIIF](https://api.artic.edu/docs/),
[Library of Congress API](https://www.loc.gov/apis/json-and-yaml/),
[análisis visual con Responses](https://developers.openai.com/api/docs/guides/images-vision).
