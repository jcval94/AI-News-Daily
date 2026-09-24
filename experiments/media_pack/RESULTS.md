# Resultados: paquetes multimedia para edición

Ejecuciones reales del 24 de septiembre de 2026, en la rama experimental y el PR #46. Producción no modificada.

**22 archivos de medios descargados y revisados** en los dos paquetes seleccionados. Cada paquete procede de una sola descripción. No son 22 coincidencias exactas: 16 son material del sujeto solicitado y 6 son contexto editorial explícito.

| Consulta | Objetivo | Descargado | Del sujeto solicitado | Contexto | Imágenes pequeñas |
|---|---|---|---|---|---|
| Explosión de Halifax, 1917 | 12 imágenes + 3 videos | 12 + 3 | 15 | 0 | 0 |
| Tsutomu Yamaguchi | 6 imágenes + 1 video | 6 + 1 | 1 foto | 5 imágenes + 1 video | 1 (408×244) |

- [Descargar paquete Halifax](https://github.com/jcval94/AI-News-Daily/actions/runs/36070171348/artifacts/10838215946) — 10.87 MiB ZIP; ejecución 36070171348.
- [Descargar paquete Yamaguchi](https://github.com/jcval94/AI-News-Daily/actions/runs/36069706416/artifacts/10838020716) — 5.46 MiB ZIP; ejecución 36069706416.

**Caducan el 1 de octubre de 2026.** El código, los IDs, procedencia, nombres, dimensiones, hashes y resultados quedan versionados en este directorio.

## Qué contiene cada paquete

Halifax incluye 11 fotografías históricas y una página de prensa con mapa, además de tres películas de W. G. MacLaughlan catalogadas por los archivos de Nueva Escocia a través de Commons. Las imágenes cubren daños, socorro y reconstrucción temprana. Los videos duran 43.443, 45.245 y 45.412 segundos; son archivos completos de escenas, silenciosos, a 480×360.

Yamaguchi conserva el retrato atribuido por la ficha de Wikipedia a Tsutomu Yamaguchi, sin ampliarlo: 408×244. El contexto son vistas de Hiroshima/Nagasaki —incluido un montaje fotográfico catalogado— y 30 segundos de una ceremonia conmemorativa en Hiroshima. **El video no muestra ni trata específicamente a Yamaguchi**: está señalado como contexto, y el fallo de descarga del video exacto sigue registrado.

La ficha del retrato indica `Fair use`; una imagen contextual de Openverse indica `by-nc-nd 2.0`. Todas las licencias se conservan y están pendientes de validación para publicación. El cumplimiento de la cantidad no equivale a estar listo para producción.

Los paquetes incluyen `gallery.html`, `SUMMARY.md`, `manifest.json`, `SHA256SUMS`, medios con nombres descriptivos y archivos auxiliares del video. Los nombres separan tema, título, exactitud/contexto, resolución, fuente e identificador estable. Las dimensiones y el título original completo permanecen en el manifiesto.

## Intentos y correcciones observadas

| Intento | Halifax | Yamaguchi | Resultado relevante |
|---|---|---|---|
| Primera ejecución: 36069191008 | 0 imágenes + 3 videos | 1 imagen contextual | Citas correctas con comillas adicionales se descartaban; una propuesta de fechas inválida impidió una búsqueda contextual. |
| Segunda: 36069706416 | 11 imágenes + 3 videos | 6 imágenes + 1 video | Recuperó la foto pequeña y multiplicidad; revisión detectó un memorial moderno mal etiquetado en Halifax. |
| Repetición dirigida: 36070171348 | 12 imágenes + 3 videos | No repetido | Se añadió clasificación determinista de memoriales como contexto y se verificó el paquete final de Halifax. |

No se mezclan ejecuciones para aparentar un único run final: Halifax procede del commit `6a3db66b59c88ba4fd00d78971789d262bb338e1`; Yamaguchi, del `44b4b685cdc2738c75c81347083f799ed1c47954`. La selección del modelo y las búsquedas varían: el cambio de cantidad no puede atribuirse únicamente a una corrección. Los resultados completos de los cinco artefactos están en el JSON adjunto.

## Validación y límites

- Se verificaron los digests de los cinco ZIP y los SHA-256 de sus 76 archivos listados. Los paquetes seleccionados contienen 22 medios y 40 archivos listados entre medios, metadatos e informes.
- Se inspeccionaron todas las imágenes de los paquetes seleccionados y muestras de tres fotogramas por video. Se contrastaron fichas de catálogo, identidad atribuida, fechas de captura frente a fechas de digitalización y licencias. No se identificaron personas mediante reconocimiento facial.
- CI del código final: 305 pruebas, 2 omitidas; compilación, imports del runtime y calibración editorial correctos. La ejecución local específica pasó 48 pruebas. La suite local completa carecía de dependencias de producción; la validación integral válida es la de Actions.
- Transcripción apagada en todos los intentos. Ningún video descargado expone Most Replayed; su estado es `not_applicable`, sin gráfica inventada. El código conserva el JSON y SVG cuando YouTube sí los proporciona.
- No se añadió API de pago de descarga. Se utilizaron los modelos semánticos/visuales ya configurados, que sí consumen tokens. No se generaron imágenes.
- Los videos son proxies de hasta 360p. La relevancia no garantiza que un fragmento inicial contenga la mejor toma; el editor debe revisar y, si hace falta, obtener el original elegido.
- Este ensayo demuestra multiplicidad y alternativas etiquetadas en dos consultas. No demuestra cobertura universal ni cambia los resultados estrictos del benchmark anterior de 12 casos por modalidad.

## Incorporación propuesta

Conectar el buscador después de aprobar el guion y normalizar el plan multimedia, antes de descargar cada slot en `pipeline/review_media.py`. Buscar una vez por sujeto y reutilizar el pool; fuentes específicas para personas/eventos y Pexels para B-roll conceptual. Mantener `edit_manifest.json`, validación de licencias, rol visual, límites de cantidad y promoción actuales.

Detalles y contrato del adaptador: [INTEGRATION.md](INTEGRATION.md). Ejecución y nombres: [README.md](README.md). Evidencia durable: [results-2026-09-24.json](results-2026-09-24.json).

## Inventario de los paquetes seleccionados

| Caso | Medio | Relación | Fuente | ID | Dimensiones |
|---|---|---|---|---|---|
| halifax | image | exact | commons | [23354071](https://commons.wikimedia.org/wiki/File:The_Duke_of_Devonshire,_Governor-General_of_Canada,_addressing_Voluntary_Aid_Detachment_staff_after_the_Halifax_Explosion.jpg) | 1920×985 |
| halifax | image | exact | commons | [53037029](https://commons.wikimedia.org/wiki/File:Campbell_Road_(later_Barrington_Street)_looking_north_from_Rector_Street_after_the_explosion_(15315649424).jpg) | 1920×1540 |
| halifax | image | exact | commons | [53037110](https://commons.wikimedia.org/wiki/File:St._Joseph%27s_Convent,_corner_of_Kaye_and_Gottingen_streets,_Halifax,_with_ruins_of_St._Joseph%27s_Roman_Catholic_Church_at_right_and_St._Joseph%27s_Girl_School_at_left_(15751858929).jpg) | 1920×1576 |
| halifax | image | exact | commons | [65640694](https://commons.wikimedia.org/wiki/File:Aftermath_of_the_Halifax_Explosion_-_Cons%C3%A9quences_de_l%E2%80%99explosion_d%E2%80%99Halifax_(8148373112).jpg) | 1920×1394 |
| halifax | image | exact | commons | [65640709](https://commons.wikimedia.org/wiki/File:View_of_Halifax,_Nova_Scotia,_from_Pier_8,_after_the_disaster_-_Vue_d%E2%80%99Halifax_en_Nouvelle-%C3%89cosse,_apr%C3%A8s_le_d%C3%A9sastre,_prise_%C3%A0_partir_du_quai_no_8_(8148340641).jpg) | 1920×715 |
| halifax | image | exact | commons | [65640712](https://commons.wikimedia.org/wiki/File:View_of_Halifax,_Nova_Scotia,_from_the_waterfront,_after_the_explosion_on_December_6,_1917_-_Vue_g%C3%A9n%C3%A9rale_d%E2%80%99Halifax_en_Nouvelle-%C3%89cosse,_prise_%C3%A0_partir_du_bord_de_l%E2%80%99eau_apr%C3%A8s_l%E2%80%99explosion_du_6_d%C3%A9cembre_1917_(8148373232).jpg) | 1920×846 |
| halifax | image | exact | commons | [73404773](https://commons.wikimedia.org/wiki/File:Registering_for_aid_after_Halifax_explosion_(24267277398).jpg) | 1050×804 |
| halifax | image | exact | wikipedia | [es-e1f95c9e4225710d3c33](https://commons.wikimedia.org/wiki/File:Halifax_Explosion_blast_cloud_restored.jpg) | 1200×1905 |
| halifax | image | exact | commons | [93986163](https://commons.wikimedia.org/wiki/File:19171208_Halifax_explosion_with_map_-_The_Boston_Daily_Globe.jpg) | 1920×2124 |
| halifax | image | exact | commons | [53037135](https://commons.wikimedia.org/wiki/File:Soldiers_standing_guard_in_the_midst_of_the_devastation_on_Kaye_Street_east_of_Gottingen_Street,_Halifax_(15937894705).jpg) | 1920×1609 |
| halifax | image | exact | commons | [53037284](https://commons.wikimedia.org/wiki/File:%22The_only_sport_in_Halifax_during_the_reconstruction%22_(15752147287).jpg) | 1920×1108 |
| halifax | image | exact | commons | [54849568](https://commons.wikimedia.org/wiki/File:Children%27s_Christmas_party_after_Halifax_explosion_(10966949964).jpg) | 1050×799 |
| halifax | video | exact | commons | [25154157](https://commons.wikimedia.org/wiki/File:Halifax_Explosion,_W.G._MacLaughlan,_1917-1920,_Scene_04.webm) | 480×360 |
| halifax | video | exact | commons | [25154171](https://commons.wikimedia.org/wiki/File:Halifax_Explosion,_W.G._MacLaughlan,_1917-1920,_Scene_10.webm) | 480×360 |
| halifax | video | exact | commons | [25154162](https://commons.wikimedia.org/wiki/File:Halifax_Explosion,_W.G._MacLaughlan,_1917-1920,_Scene_08.webm) | 480×360 |
| yamaguchi | image | exact | wikipedia | [en-1b5c97f33e8a7883cb46](https://en.wikipedia.org/wiki/File:Tsutomu-Yamaguchi-Japanes-001.jpg) | 408×244 |
| yamaguchi | image | context | wikipedia | [en-8fec725c663c84039d1e](https://commons.wikimedia.org/wiki/File:Ganbaku_Dome_of_Hiroshima_from_distance.jpg) | 900×603 |
| yamaguchi | image | context | openverse | [b5600ebb-cde3-465f-85e0-57c16ad86d2c](https://openverse.org/image/b5600ebb-cde3-465f-85e0-57c16ad86d2c) | 1024×768 |
| yamaguchi | image | context | commons | [36919248](https://commons.wikimedia.org/wiki/File:Hiroshima_montage2.jpg) | 1220×1678 |
| yamaguchi | video | context | commons | [81260918](https://commons.wikimedia.org/wiki/File:Hiroshima_Peace_Memorial_Ceremony_%26_Peace_Message_Lantern_Floating_Ceremony_(B-Roll)_DOD_107097600-5d50f879d663c.webm) | 640×360 |
| yamaguchi | image | context | commons | [26287606](https://commons.wikimedia.org/wiki/File:Nagasaki_(4696131594).jpg) | 1600×1067 |
| yamaguchi | image | context | wikipedia | [en-ed4c63718ebf22b11773](https://commons.wikimedia.org/wiki/File:Nagasaki_Fountain_of_Peace.jpg) | 1600×1200 |
