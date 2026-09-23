# Resultados reales — 23 de septiembre de 2026

Experimento independiente en [PR #46](https://github.com/jcval94/AI-News-Daily/pull/46).
No se generaron imágenes. La ejecución y las descargas se realizaron en GitHub Actions;
después se bajaron los ZIP para comprobar sus hashes, decodificar los archivos y revisar
su aspecto junto con las fichas de procedencia.

**Muestra final: diez imágenes revisadas — cinco fotografías atribuidas a Einstein y
cinco fotografías de objetos romanos.** Las descargas verificadas proceden de Commons
y del Met. Los resultados finales combinan Roma de la primera ejecución y Einstein
de la ejecución corregida; el archivo de Einstein inicial conserva el duplicado y
no es la muestra final recomendada.

## Einstein tras corregir la deduplicación

[Ejecución 35926606328](https://github.com/jcval94/AI-News-Daily/actions/runs/35926606328),
commit `fb30fdaf843ef2fec09529f5e21d016c05936569`: **5/5, success**.
[Descargar muestra final de Einstein](https://github.com/jcval94/AI-News-Daily/actions/runs/35926606328/artifacts/10779108674)
(3.516.561 bytes; caduca el 30 de septiembre de 2026).

| Archivo de Commons | Ficha / contexto |
|---|---|
| `6372844` — Albert Einstein Head cleaned | Retrato atribuido a Einstein, 1947 |
| `34239518` — Einstein 1921 by F Schmutzer - restoration | Fotografía de una conferencia en Viena, 1921 |
| `1794649` — Solvay conference 1927 Version2 | Foto colectiva; el catálogo lo identifica entre los participantes |
| `45353782` — 08608 einstein 1916 | Fotografía en la biblioteca de Paul Ehrenfest, 1916 |
| `118921110` — Uniandes advisory board 1954-55 | Foto colectiva; la descripción enumera a Albert Einstein |

Se verificaron todos los hashes y dimensiones. Cuatro archivos coinciden exactamente
con los ya inspeccionados y el quinto también se revisó visualmente. Son tres imágenes
individuales y dos colectivas, todas con atribución expresa en la ficha. Se rechazaron
28 candidatos por metadatos, una imagen pequeña y tres variantes duplicadas, incluida
la que había pasado incorrectamente en la primera prueba.

## Primera prueba: dos descripciones sin URLs ni IDs preseleccionados

[Ejecución 35926068957](https://github.com/jcval94/AI-News-Daily/actions/runs/35926068957),
commit `2f36c4df6d48f1f29d2f10540ea7fc9ad907dbe7`. Ambos jobs terminaron en `success`.

| Entrada exacta | Solicitadas | Archivos aceptados | Fuentes de las descargas |
|---|---:|---:|---|
| `Einstein` | 5 | 5 | Wikimedia Commons |
| `Roma Antigua` | 5 | 5 | Wikimedia Commons (3), Metropolitan Museum (2) |

**La primera muestra de Einstein contiene dos variantes de la misma fotografía.**
Por tanto, cinco archivos no equivalían a cinco fotografías distintas. La inspección
detectó este problema y motivó una corrección: agrupar nombres de versiones recortadas,
limpiadas y restauradas de un archivo de Commons, además de hashes de bytes, píxeles y
perceptuales. La primera muestra queda como evidencia del problema, no como validación
de cinco composiciones diferentes.

Artefactos iniciales, con caducidad el **30 de septiembre de 2026**:

- [Einstein, primera muestra](https://github.com/jcval94/AI-News-Daily/actions/runs/35926068957/artifacts/10779286136): 4.042.181 bytes; contiene la variante duplicada descrita.
- [Roma Antigua, muestra verificada](https://github.com/jcval94/AI-News-Daily/actions/runs/35926068957/artifacts/10778779077): 9.110.539 bytes.

Cada ZIP incluye `gallery.html`, imágenes, sus fichas, verificaciones, plan, candidatos,
decisiones, motivos de descarte, resumen y `SHA256SUMS`.

## Evidencia de identidad y contexto

`Einstein` se interpretó como **Albert Einstein** y se resolvió a **Wikidata Q937**,
clasificado como ser humano. La resolución excluye entidades homónimas como trenes y
pinturas. Las atribuciones proceden de las fichas, no de reconocimiento facial.
La primera selección incluye retratos, una fotografía de 1916, una de 1921 y una
fotografía colectiva de Solvay cuya descripción incluye explícitamente a Albert Einstein.

`Roma Antigua` se interpretó como civilización/periodo, con intervalo de búsqueda
753 a. C.–476 d. C. No implica que todas las piezas estén actualmente en la ciudad de
Roma ni que las fotografías se hayan tomado en la Antigüedad. La muestra descargada
contiene cinco **fotografías de objetos romanos**, no reconstrucciones del aspecto de
la ciudad antigua:

| Catálogo | Pieza | Evidencia de la ficha |
|---|---|---|
| Commons `44334825` | Medallón funerario de Maria Saal | Descripción: relieve romano antiguo |
| Met `248891` | Estatua de bronce de un joven aristócrata | Cultura romana; 27 a. C.–14 d. C. |
| Commons `49090093` | Relieve funerario en Klagenfurt | Descripción: lápida romana antigua |
| Met `256126` | Soporte de pórfido para una pila | Cultura romana; siglo II d. C. |
| Commons `62061288` | Monumento expuesto en Maastricht | Descripción: monumento romano antiguo |

Los cinco archivos se inspeccionaron visualmente: representan objetos y coinciden con
el tipo de contenido de sus fichas. Uno presenta reflejos del cristal de exposición;
el objeto sigue siendo reconocible, aunque su calidad editorial es menor. Las fechas
y culturas se sustentan en los catálogos, no se deducen de su apariencia.

## Proveedores y descartes observados

| Fuente | Einstein: candidatos | Roma: candidatos | Resultado observado |
|---|---:|---:|---|
| Wikimedia Commons | 19 | 20 | Metadatos e imágenes descargables |
| Met | 1 | 19 | Metadatos e imágenes descargables; solo imágenes de dominio público según su API |
| Art Institute of Chicago | 20 | 20 | Catálogo accesible; un intento de imagen IIIF devolvió HTTP 403. Se detuvo esa fuente y se continuó con otras |
| Library of Congress | 0 | 0 | Las consultas de esta prueba no aportaron candidatos; no se validó una descarga de esta fuente |

El caso Einstein descartó 28 candidatos en la validación de metadatos; durante la
descarga rechazó una imagen pequeña y una variante casi idéntica. La deduplicación
perceptual inicial dejó pasar el recorte documentado arriba. Roma descartó 11 candidatos
por metadatos y un intento por el HTTP 403 de Chicago. No se rellenó la cantidad con
los candidatos rechazados ni se modificaron los criterios para aprobar los jobs.

## Verificación y alcance

- Todos los SHA-256 de ambos ZIP comprobados; todos los archivos aceptados se
  decodificaron y sus dimensiones coincidieron con el manifiesto.
- Suite del código inicial: 208 pruebas, `OK`, una omitida por matplotlib del experimento
  previo. [CI 35926076243: success](https://github.com/jcval94/AI-News-Daily/actions/runs/35926076243).
- Suite tras corregir variantes duplicadas: 209 pruebas, `OK`, una omitida por el mismo
  motivo. Incluye una regresión que reproduce el recorte/restauración detectado.
  [CI 35926612103: success](https://github.com/jcval94/AI-News-Daily/actions/runs/35926612103).
- Ninguna llamada a generación de imágenes. La copia reducida para inspección se hace
  en memoria; el artefacto conserva exactamente los bytes proporcionados por la fuente.
- Esta es una revisión de dos consultas concretas, **no una medición de precisión
  universal**. Persisten límites de cobertura, disponibilidad, derechos, calidad del
  catálogo y errores posibles del evaluador. Ante dudas, el sistema devuelve menos
  resultados y marca la petición como parcial.
