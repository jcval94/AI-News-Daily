# Resultados observados — 23 de septiembre de 2026

Experimento en `experiment/youtube-artifacts`, [PR #46](https://github.com/jcval94/AI-News-Daily/pull/46).
El pipeline de producción no interviene. Todos los trabajos remotos usan GitHub Actions.

Resultado acumulado verificado: **11 videos distintos completos y 11 transcripciones**
(cinco históricos, cinco financieros y uno específico de Enron), todos de Archive.
**0 descargas directas de YouTube y 0 curvas reales Most Replayed** por el bloqueo
observado desde los runners. No es una validación de descarga universal de YouTube.

## Videos y transcripciones verificados

La [ejecución con transcripciones](https://github.com/jcval94/AI-News-Daily/actions/runs/35881143125)
obtuvo cinco videos históricos y uno financiero. La
[siguiente ejecución financiera](https://github.com/jcval94/AI-News-Daily/actions/runs/35882284507)
obtuvo cinco, incluido el financiero anterior. Entre ambas hay **10 videos distintos
completos y 10 transcripciones**, todos desde Internet Archive. El caso financiero
no cubrió Enron y su gate falló aunque alcanzó 5/5 descargas.
La [prueba específica posterior](https://github.com/jcval94/AI-News-Daily/actions/runs/35883196184)
sí completó 1/1 con cobertura de «La caída de Enron» y transcripción disponible.
YouTube pidió verificación humana: **0 videos descargados
directamente de YouTube**. No se presenta el fallback como una descarga de YouTube,
incluso cuando el identificador del elemento de Archive empieza por `youtube-`.

Se descargaron los cuatro ZIP de Actions y se comprobaron todos sus `SHA256SUMS`,
los streams de video y las duraciones mediante `ffprobe`. Las once transcripciones
contienen texto y segmentos con marcas de tiempo.

| Video / ID de Archive | Duración | Transcripción | Segmentos |
|---|---:|---|---:|
| `youtube-MGE__5URvTA` — Marchas/himnos de la Segunda Guerra Mundial | 325,5 s | ASR generado | 22 |
| `youtube-UWQsz20KK5M` — Discurso histórico | 325,5 s | ASR generado | 26 |
| `Challeng1944` — A Challenge to Democracy | 1084,0 s | ASR generado | 292 |
| `EducationForDeathTheMakingOfTheNazi` — Education for Death | 608,1 s | ASR generado | 155 |
| `Japanese1943` — Japanese Relocation | 568,5 s | ASR generado | 74 |
| `cowomn-Financial_Fraud` — Financial Fraud | 180,1 s | Subtítulos publicados en Archive | 163 |
| `TheManBehindtheWorldsBiggestFinancialFraudInvestigators` — Financial Fraud | 552,7 s | ASR generado | 169 |
| `cg_0130-Tips_to_Protect_your_Wealth_and_Self_from_Financial_Fraud_and_Scammers` | 1775,2 s | Subtítulos publicados en Archive | 1306 |
| `cowomn-Financial_Fraud_-_Easy_Steps_to_Protect_Your_Money_Online` | 26,5 s | ASR generado | 6 |
| `cowomn-Financial_Fraud_-_Real-Life_Scam_Story_-_Told_by_Woodbury_Police` | 47,3 s | ASR generado | 12 |
| `the-enron-story` — The Enron Story | 657,0 s | ASR generado | 143 |

La selección histórica incluye material de época y propaganda, además de una
compilación musical. La coincidencia temática de metadatos no certifica las fechas,
afirmaciones ni calidad editorial de las fuentes. El ASR está identificado como
generado y no se ha revisado palabra por palabra contra el audio.

Artefactos de esta ejecución, con caducidad el **30 de septiembre de 2026**:

- [Cinco videos históricos y transcripciones](https://github.com/jcval94/AI-News-Daily/actions/runs/35881143125/artifacts/10760758384): 113.904.295 bytes.
- [Video financiero, subtítulos y diagnósticos de Enron](https://github.com/jcval94/AI-News-Daily/actions/runs/35881143125/artifacts/10760297926): 4.450.487 bytes.
- [Cinco videos financieros y transcripciones](https://github.com/jcval94/AI-News-Daily/actions/runs/35882284507/artifacts/10761620721): 50.763.108 bytes. No contiene un video de Enron.
- [The Enron Story y transcripción](https://github.com/jcval94/AI-News-Daily/actions/runs/35883196184/artifacts/10762560046): 18.579.619 bytes; gate de cantidad y evento aprobado.

## Most Replayed

**Ninguna curva real obtenida en estas pruebas.** Todos los videos descargados
proceden de Archive, cuyo `most_replayed.json` informa `not_applicable`.
Los intentos directos de YouTube quedaron bloqueados antes de obtener sus metadatos
completos. El soporte de extracción y SVG está implementado, pero su funcionamiento
con datos reales de YouTube no ha podido verificarse desde estos runners.

Las pruebas automatizadas validan intervalos, intensidades, picos, datos ausentes y
generación del SVG con datos sintéticos de prueba; esos datos no se publican como
observaciones. No se reconstruye ni inventa una curva a partir del audio.

## Iteraciones y limitaciones detectadas

| Ejecución | Resultado relevante |
|---|---|
| [35818437356](https://github.com/jcval94/AI-News-Daily/actions/runs/35818437356) | Fragmentos iniciales: coincidencias léxicas aceptaron falsos positivos. No constituyen una muestra válida de diez videos. |
| [35818632823](https://github.com/jcval94/AI-News-Daily/actions/runs/35818632823) | Selector semántico inicial: 3/5 históricos; error de referencias en Enron. Se introdujeron referencias cortas validadas y deduplicación. |
| [35818719958](https://github.com/jcval94/AI-News-Daily/actions/runs/35818719958) | Cancelada. Motivó preflight de duración y preparación de archivos fuera del directorio del artefacto. No se cuenta como muestra validada. |
| [35819438289](https://github.com/jcval94/AI-News-Daily/actions/runs/35819438289) | Un video completo de Enron y uno pertinente de la Batalla de las Ardenas verificados. Un segundo video histórico era un falso positivo: se excluye de los resultados útiles. |
| [35879587060](https://github.com/jcval94/AI-News-Daily/actions/runs/35879587060) | Modelo más capaz y búsqueda por título/materia; históricos bloqueados por discrepancia del límite de selecciones, corregida a 50 en esquema y código. Enron: 3/5 de contexto financiero, evento sin cubrir. |
| [35881143125](https://github.com/jcval94/AI-News-Daily/actions/runs/35881143125) | 5/5 históricos + 1/5 financieros, seis transcripciones; ningún video de Enron ni curva Most Replayed en esta ejecución. |
| [35882284507](https://github.com/jcval94/AI-News-Daily/actions/runs/35882284507) | 5/5 financieros y cinco transcripciones; falla correctamente por ausencia de Enron. Se localizó un falso negativo del filtro léxico previo al selector semántico. |
| [35883196184](https://github.com/jcval94/AI-News-Daily/actions/runs/35883196184) | 1/1 específico de Enron, transcripción ASR de 143 segmentos y cobertura del evento; workflow **success**. |

El video específico de Enron de la cuarta ejecución es
`la-cai-da-de-enron-la-gran-estafa-americana`, dura 1245,936 s y ocupa 31.008.294 bytes
(H.264/AAC, 640×360). Su [artefacto](https://github.com/jcval94/AI-News-Daily/actions/runs/35819438289/artifacts/10732258975)
se verificó íntegramente, pero se creó antes de añadir transcripciones.

La búsqueda combinada de títulos y materias dejaba fuera videos específicos frente
a entrevistas populares de más de 30 minutos. La corrección posterior prioriza
títulos y amplía a materias cuando hay pocos resultados; conserva los presupuestos
de duración, tamaño y número de intentos.

La siguiente corrección permite que el evaluador semántico revise candidatos aunque
no satisfagan los grupos léxicos exactos. Por ejemplo, un plan con `enron + bankruptcy`
excluía incorrectamente el título «La caída de Enron». Las coincidencias de nombres
en títulos priorizan el pool, pero no conceden cobertura por sí mismas. La cantidad
pedida sigue siendo independiente del gate de eventos; los intentos para peticiones
pequeñas tienen un mínimo de diez y siempre conservan el límite temporal.

## Verificación del código

- Compilación de `app`, `pipeline` y `experiments` correcta.
- Suite completa: 193 pruebas, resultado `OK`, una omitida por no estar matplotlib
  en el entorno mínimo de producción. La prueba SVG y las otras siete de complementos
  se ejecutaron aparte con matplotlib instalado y pasaron.
- CI del commit con transcripciones:
  [35881154752 — success](https://github.com/jcval94/AI-News-Daily/actions/runs/35881154752).
- CI de la búsqueda priorizada por título:
  [35882291851 — success](https://github.com/jcval94/AI-News-Daily/actions/runs/35882291851).
- CI del código final:
  [35883200875 — success](https://github.com/jcval94/AI-News-Daily/actions/runs/35883200875).
- Las ausencias de transcripción y de heatmap se informan por separado. El gate exige
  cantidad y cobertura explícita; nunca considera éxito un ZIP de diagnósticos vacío.

No se puede garantizar cualquier video público de YouTube desde una IP de Actions.
La muestra original de diez descargas directas de YouTube sigue sin conseguirse;
los [resultados del experimento fijo](../youtube_artifacts/RESULTS.md) documentan
también el bloqueo observado en septiembre de 2026.
