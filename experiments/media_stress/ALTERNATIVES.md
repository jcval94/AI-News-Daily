# Fuentes alternativas: protocolo de repetición

Se conserva `cases.json`: las mismas 12 personas/eventos, una imagen y un video
por referente, criterio exacto y revisión posterior de archivos. No se alteran
las descripciones, la resolución mínima de imágenes ni los límites de videos.
Transcripción desactivada; prioridad para videos cortos. No se generan imágenes.

## APIs incorporadas

| Fuente | Uso | Acceso y límites de esta implementación |
|---|---|---|
| Wikipedia/MediaWiki | Descubrir archivos de artículos en inglés y español, incluidos archivos locales | Pública, sin clave. La pertenencia al artículo no demuestra qué representa una foto. Se exige la ficha del archivo; P18 puede acreditar una transliteración. Las licencias se conservan. |
| Openverse | Ampliar búsqueda de imágenes | API anónima, sin cuenta ni pago; una búsqueda/caso, 20 resultados. Solo descarga desde CDN/catálogos admitidos. 403/429 detiene el proveedor. La sonda local devolvió 403. |
| Wikimedia Commons TimedMediaHandler | Videos con archivos originales/derivados públicos | API sin clave. Bytes limitados, copia local, comprobación con ffprobe/ffmpeg. |
| Sepia Search + PeerTube | Descubrir videos en plataformas federadas | API pública sin clave; frase exacta primero. Si no hay resultados, hasta 30 candidatos con exigencia local de todas las palabras. Se reconfirma público, no directo y `downloadEnabled=true`. MP4 progresivo o archivo MP4 fragmentado completo con audio explícito; no se siguen listas HLS/P2P. |
| NASA Image and Video Library | Videos científicos e históricos del catálogo | API pública sin clave; se prioriza el derivado pequeño. Una coincidencia geográfica no acredita un desastre. |

Se mantienen YouTube, Internet Archive, Commons de imágenes, Met, AIC y LoC.
No se usa la API empresarial de Dailymotion ni servicios de pago de descarga.
Pexels/Pixabay son catálogos de stock y no sustituyen pruebas del referente exacto.
No se añaden claves, suscripciones, proxies, cookies ni evasión de verificaciones.
Las llamadas semánticas/visuales existentes a OpenAI siguen activas; este cambio
no significa que todo el experimento sea gratuito. Las nuevas APIs se usan sin
credenciales pagadas. Los minutos/almacenamiento de Actions dependen de la cuenta.

## Controles y revisión

La selección semántica conserva presupuestos totales (50 videos, 80 imágenes),
con espacio para cada proveedor. Python conserva las decisiones de descarga,
límites y estado. Para hosts federados se validan HTTPS/DNS público y cada
redirección; la conexión TLS usa la IP verificada. El contenido se descarga antes
de procesarlo y ffmpeg solo puede abrir archivos locales. Tamaño de fuente nuevo:
256 MiB; artefacto final: 128 MiB, 360p, máximo 30 minutos.

`source_controls.py` prueba por separado Commons, PeerTube y NASA con clips de
15 segundos, sin llamadas a modelos. Estos controles prueban acceso/decodificación,
no precisión, y nunca se suman a los 24 casos. Un workflow verde puede contener
resultados negativos: las descargas y coincidencias exactas se cuentan después.

La comparación anterior es la última evidencia publicada: 5/12 imágenes y 3/12
videos, compuesta por la ejecución inicial y repeticiones focalizadas. La nueva
ejecución repite los 24 casos completos; no es una prueba aleatoria ni una garantía
de cobertura universal. El plan/modelo puede variar aun con las mismas entradas.

## Documentación de las fuentes

- https://www.mediawiki.org/wiki/Extension:PageImages
- https://www.mediawiki.org/wiki/Extension:TimedMediaHandler/API
- https://docs.openverse.org/api/reference/authentication_and_throttling.html
- https://docs.joinpeertube.org/api/rest-getting-started
- https://search.joinpeertube.org/
- https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf
- https://developers.dailymotion.com/docs/generate-download-urls

El tipo de identidad distingue personas de eventos: para personas se mantiene el nombre literal; para eventos se admite un alias compuesto dentro de 80 palabras de la fuente, con todos sus términos y una coincidencia del evento explícito. Esto evita rechazar «Lake Nyos in 1986 ... disaster» por no ser una frase contigua. La relevancia semántica y la revisión de exactitud siguen siendo necesarias.
