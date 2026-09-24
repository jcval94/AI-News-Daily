# Prueba de estrés: 12 referentes × imágenes y videos

24 de septiembre de 2026. Experimento independiente; sin integración en producción ni merge a main.

Resultado inicial: **2/12 imágenes y 3/12 videos exactos**. Después de repetir los casos afectados: **5/12 imágenes y 3/12 videos**. Los demás conservan el resultado inicial; no es una nueva ejecución completa del código final.

El éxito exige archivo descargado y referente exacto. Un resultado de búsqueda, título coincidente o workflow verde no bastan. Las identidades proceden de fichas, nunca de reconocimiento facial. Revisó el asistente mediante fuentes y archivos/fotogramas: no es revisión humana ni auditoría factual completa de la narración. Una negativa no prueba que el material no exista.

| Referente | Imágenes: última prueba | Videos: última prueba |
|---|---|---|
| Khan Baba | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10790709466) | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791715368) |
| Juliane Koepcke | [Exacto](https://github.com/jcval94/AI-News-Daily/actions/runs/35959033518/artifacts/10791831629) | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791142525) |
| Tsutomu Yamaguchi | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10790762843) | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35958457226/artifacts/10791466178) |
| Vesna Vulović | [Exacto](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791395928) | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791745477) |
| Vasili Arkhipov | [Exacto](https://github.com/jcval94/AI-News-Daily/actions/runs/35959033518/artifacts/10791292125) | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791216478) |
| Stanislav Petrov | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791387204) | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35958724059/artifacts/10791042798) |
| Guerra de los Toyota | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791616616) | [Exacto](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791471675) |
| Guerra del Emú | [Exacto](https://github.com/jcval94/AI-News-Daily/actions/runs/36028318300/artifacts/10820328142) | [Exacto](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791480903) |
| Desastre del lago Nyos | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10790813361) | [Parcial: no cuenta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791790720) |
| Inundación de melaza | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791213561) | [Exacto](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791746056) |
| Explosión de Halifax | [Exacto](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791562253) | [Parcial: no cuenta](https://github.com/jcval94/AI-News-Daily/actions/runs/35958724059/artifacts/10791237227) |
| Epidemia de risa de Tanganica | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10792010067) | [Sin descarga exacta](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540/artifacts/10791910194) |

## Evidencia por caso

### Khan Baba

- Imágenes: Sin foto acreditada descargada.
- Videos: YouTube encontró videos específicos pero bloqueó la descarga; sin alternativa de Archive.

### Juliane Koepcke

- Imágenes: Fallo inicial del plan por fechas incompletas; repetición con foto acreditada por Cancillería del Perú.
- Videos: YouTube bloqueado; documental de Archive fuera del límite de duración.
  - Fuente (images): https://commons.wikimedia.org/wiki/File:Ceremonia_de_condecoraci%C3%B3n_a_la_doctora_Juliane_Koepcke_-_46616983225_(cropped).jpg

### Tsutomu Yamaguchi

- Imágenes: El Domo de Hiroshima fue rechazado: no es una foto de Yamaguchi.
- Videos: Falso positivo inicial: Hiroshima/Nagasaki general. Corregido; repetición rechaza el contexto, YouTube sigue bloqueado.

### Vesna Vulović

- Imágenes: Foto identificada de su visita a Checoslovaquia en noviembre de 1972.
- Videos: YouTube bloqueado; sin alternativa exacta descargada.
  - Fuente (images): https://commons.wikimedia.org/wiki/File:Vesna_Vulovi%C4%87_(right)_during_her_visit_in_Czechoslovakia,_November_1972.png

### Vasili Arkhipov

- Imágenes: Falló por nombre/consulta; repetición con retrato identificado en Commons.
- Videos: YouTube bloqueado; sin alternativa exacta descargada.
  - Fuente (images): https://commons.wikimedia.org/wiki/File:Vasili_Arkhipov.jpg

### Stanislav Petrov

- Imágenes: Fotos con transliteración alemana rechazadas; homónimos impidieron resolver entidad única.
- Videos: YouTube bloqueado también en la repetición.

### Guerra de los Toyota

- Imágenes: Sin coincidencia descargada con las consultas iniciales.
- Videos: Documental animado dedicado a la Guerra de los Toyota: 15:38. Explicación moderna, no filmación original de 1987.
  - Fuente (videos): https://archive.org/details/the-toyota-war-animated-history

### Guerra del Emú

- Imágenes: Tras corregir consulta y clasificación del medio: soldados descansando durante la Guerra del Emú, noviembre-diciembre de 1932.
- Videos: Montaje temático con mapa y fechas de la Guerra del Emú: 23 s. Referente exacto; calidad editorial limitada, no filmación original.
  - Fuente (images): https://commons.wikimedia.org/wiki/File:Australian_soldiers_resting_during_Emu_War.jpg
  - Fuente (videos): https://archive.org/details/TikTok-7625969863126879495

### Desastre del lago Nyos

- Imágenes: Sin coincidencia descargada con las consultas iniciales.
- Videos: Falso positivo: zoom geográfico NASA de 13 s. No documenta ni explica el desastre.
  - Fuente (videos): https://archive.org/details/SVS-2348

### Inundación de melaza

- Imágenes: Sin coincidencia descargada en esta ejecución.
- Videos: Video explicativo sobre la inundación de Boston de 1919: 67 s.
  - Fuente (videos): https://archive.org/details/TikTok-7280574985075215658

### Explosión de Halifax

- Imágenes: Foto de la nube del 6-12-1917, acreditada por Nova Scotia Archives.
- Videos: Plan inicial duplicó evento y colisión. La repetición descargó un noticiero de 763 s con segmento 07:12–08:39 pertinente. El archivo completo es una compilación de ocho temas y no cumple.
  - Fuente (images): https://commons.wikimedia.org/wiki/File:Smoke_cloud_from_the_Halifax_Explosion,_probably_taken_off_McNabs_Island_(15318272793).jpg
  - Fuente (videos): https://archive.org/details/60694-yesterdays-newsreel-airmail-history-begins-vwr

### Epidemia de risa de Tanganica

- Imágenes: Sin documento visual del evento exacto descargado.
- Videos: YouTube encontró candidatos; descarga bloqueada y sin alternativa descargada.

## Cambios y límites

- Transcripción apagada por defecto en CLI, función y workflow. source solicita subtítulos existentes; auto activa ASR explícitamente. Todos los videos de estas pruebas registran disabled: cero transcripciones generadas.
- Candidatos relevantes de duración conocida ≤5 min primero, ordenados por duración; después duración desconocida y finalmente largos. Cobertura del evento conserva prioridad. Máximo 30 min/128 MiB. Archive elige el derivado más pequeño; sus búsquedas no siempre informan duración.
- Identidad obligatoria para referentes concretos de video: Python exige el nombre solicitado o un alias literal en la fuente. Hiroshima general ya no sustituye a Yamaguchi.
- Un video puede cubrir varias menciones del mismo suceso; se eliminó el requisito previo de un archivo por mención. La cobertura final sigue siendo obligatoria.
- Consultas de imágenes como combinación de palabras literales, sin exigir adyacencia de toda la frase. Alias acreditados por Wikidata con unicidad y tipo humano. Las fechas biográficas no restringen automáticamente el retrato.
- Una foto histórica catalogada puede contener participantes: el clasificador visual puede llamarla foto de personas aunque la evaluación del catálogo la llame escena. Se mantiene la evidencia literal del evento y el rechazo de imágenes sintéticas.
- Persisten falsos positivos de videos geográficos y compilaciones. Tres archivos rechazados en las ejecuciones: Hiroshima general, zoom Nyos y noticiero general con segmento Halifax. Se preservan como evidencia del fallo, no como éxitos.
- YouTube permitió descubrimiento pero bloqueó descargas. Archive proporcionó los videos descargados. Cero curvas Most Replayed disponibles; no se fabricaron.
- Muestra elegida de seis personas y seis eventos, no aleatoria; no mide precisión universal. Un archivo solicitado por caso. Las animaciones encontradas ya existían; no hubo generación de imágenes.

## Reproducción y conservación

[24 pruebas iniciales](https://github.com/jcval94/AI-News-Daily/actions/runs/35957914540). [Repeticiones de imágenes](https://github.com/jcval94/AI-News-Daily/actions/runs/35959033518). [Foto final Guerra del Emú](https://github.com/jcval94/AI-News-Daily/actions/runs/36028318300). [Halifax/Petrov](https://github.com/jcval94/AI-News-Daily/actions/runs/35958724059). [Yamaguchi corregido](https://github.com/jcval94/AI-News-Daily/actions/runs/35958457226).

ZIP con archivos, planes, candidatos, rechazos, fichas y SHA-256. Caducan el **1 de octubre de 2026**. results-2026-09-24.json conserva enlaces, IDs, hashes, diagnósticos y revisión por caso. Los benchmark.json originales quedaron pendientes de revisión; el JSON consolidado contiene esta adjudicación posterior. Se comprobaron 246 hashes de archivos.

[CI del código final](https://github.com/jcval94/AI-News-Daily/actions/runs/36028324370): compilación y 219 pruebas, 2 omitidas. También se ejecutaron localmente las pruebas específicas de imágenes, videos y benchmark.
