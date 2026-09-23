# Experimento independiente: descripción → videos → artefactos

Una descripción libre produce consultas, búsquedas públicas, selección de videos,
descargas verificadas y un artefacto de GitHub Actions. Este módulo no importa
`app` ni `pipeline`, no genera episodios y no publica en el Review Hub. Conserva
el experimento original de diez videos fijos en `experiments/youtube_artifacts/`.

## Uso en GitHub

Workflow: **Experiment — Description to video artifacts**.

- `description`: tema libre, en español u otro idioma. Incluye los eventos concretos
  que quieres cubrir, por ejemplo: «malas prácticas financieras y la caída de Enron».
- `count`: de 1 a 25 videos, diez por defecto.
- `sources`: `youtube` por defecto; `archive` o `youtube,archive` son opciones explícitas.
- `mode`: `full` descarga el video completo dentro del presupuesto; `clip` conserva
  los primeros 15 segundos como prueba de acceso. No busca automáticamente el mejor
  instante dentro del video.

Mientras este workflow viva únicamente en la rama `experiment/youtube-artifacts`,
puedes ejecutarlo editando `live-request.json` en esa rama desde GitHub y haciendo
commit. Cambiar `request_id` también inicia una prueba. El archivo admite 1-3 casos
independientes. Los cambios de código por sí solos no inician descargas.

Cuando el workflow exista en la rama por defecto, usa **Actions → Run workflow**
y escribe la descripción en el formulario. El experimento no se fusiona con `main`
automáticamente y no tiene cron ni disparadores de producción.

Secrets usados: `OPENAI_API_KEY` para interpretación semántica y, opcionalmente,
`YOUTUBE_API_KEY` para la búsqueda oficial. Sin la segunda clave usa la búsqueda
pública de yt-dlp. Se reutiliza `vars.OPENAI_MODEL` o el modelo ya configurado en
el repo, `gpt-5.4-nano`. Todo el cómputo ocurre en Actions; consulta las APIs de los
proveedores y no necesita un servidor propio. El uso de esas APIs puede tener coste.

## Cómo generaliza

1. Un único planificador recibe la descripción como datos, sin herramientas. Produce
   un esquema estricto de tema, eventos, consultas y grupos de términos. No contiene
   listas fijas de temas ni de IDs de video.
2. Pydantic valida la salida. Cada evento tiene que citar un fragmento literal del
   usuario. Una frase amplia sobre inversionistas se convierte en consultas sobre
   prácticas financieras; no se convierte en una acusación comprobada ni se inventa
   una empresa para completar la lista.
3. Busca primero los eventos y después el tema, con hasta ocho consultas únicas y
   quince resultados por consulta y proveedor. Deduplica por proveedor e ID.
4. Compara títulos/descripciones con alias del tema y evento. Una segunda llamada
   semántica evalúa hasta 25 candidatos por proveedor y propone hasta 30 alternativas:
   descarta menciones incidentales en biografías, etiquetas o temas ajenos. Pydantic
   y el código exigen IDs conocidos, eventos presentes y ausencia de duplicados.
   Prioriza eventos y procura diversidad de autores. Esta selección sigue siendo una
   evaluación de metadatos, no verificación visual ni factual.
5. Descarga solo fuentes seleccionadas. Un desafío de YouTube o un límite de cuota
   detiene ese proveedor; no usa cookies, proxies de evasión ni autenticación privada.
   Archive, cuando se selecciona, conserva su identidad: no se presenta como YouTube.
6. Comprueba stream de video, resolución, duración, tamaño, una muestra de decodificación
   y SHA-256. Borra descargas fallidas o parciales antes de subir el artefacto.

Un evento sin video descargado hace fallar el gate aunque se complete la cantidad
con contexto general. Los fallos individuales permiten probar otros candidatos hasta
el límite de intentos. El éxito requiere cantidad **y** cobertura de todos los eventos.

## Presupuestos y resultados

- Hasta tres eventos explícitos, 25 videos y 45 intentos de descarga.
- Máximo 360p, 128 MiB por video final y 30 minutos para videos completos.
- Tiempo máximo por descarga: cuatro minutos; presupuesto del bucle: veinte minutos;
  timeout del job: treinta minutos. Los procesos hijos se terminan al exceder límites.
- Artefactos durante siete días: no constituyen un archivo permanente.
- Disponibilidad pública y derechos de republicación son conceptos distintos. Se
  conserva la licencia declarada o `unknown`, sin presumir permiso para reutilización.

El ZIP contiene `plan.json`, `candidates.json`, `manifest.json`, `SUMMARY.md`,
`ATTRIBUTION.md`, `SHA256SUMS` y `videos/<proveedor>_<id>/`. `manifest.json` conserva
la descripción, consultas, selección, errores, proveedor, cobertura por evento y
conteos reales. Nunca incluye claves ni URLs firmadas de streams de YouTube.

Las URLs de candidatos son referencias; solo una entrada `status=downloaded` con
archivo de video validado cuenta como descarga. El workflow sube diagnósticos incluso
si falla y luego aplica el gate. Un ZIP de diagnósticos sin videos no es éxito.

## Uso local y verificación

```bash
python -m pip install -r experiments/video_search/requirements.txt
# También requiere ffmpeg/ffprobe y Node.js para yt-dlp.
export VIDEO_DESCRIPTION='Malas prácticas financieras y la caída de Enron'
python -m experiments.video_search.run --count 10 --sources youtube \
  --mode full --output video-search-output/enron-001
python -m unittest discover -s tests -p 'test_video_search_experiment.py' -v
```

El directorio de salida debe ser nuevo y estar dentro de `video-search-output/`.
`--planner literal` permite búsquedas sin OpenAI, pero exige coincidencia de la frase
y **no** ofrece reconocimiento semántico de eventos; queda identificado en el manifiesto.

Prueba inicial de la generalización: dos casos de cinco fragmentos (Segunda Guerra
Mundial y Enron), con ambas fuentes habilitadas. Los resultados reales se registran
en `RESULTS.md` después de inspeccionar Actions. El experimento anterior encontró
desafíos de verificación humana desde runners de GitHub; no se promete acceso a
cualquier video de YouTube por el hecho de ser público.

Referencias de implementación:
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[YouTube search.list](https://developers.google.com/youtube/v3/docs/search/list),
[Internet Archive metadata](https://archive.org/developers/md-read.html),
[yt-dlp](https://github.com/yt-dlp/yt-dlp),
[GitHub workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).
