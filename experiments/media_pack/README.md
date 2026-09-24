# Paquetes multimedia para edición — experimento independiente

Una descripción produce una biblioteca pequeña de imágenes y videos descargados,
una galería navegable y un manifiesto trazable. No genera imágenes. No modifica el
pipeline principal, el guion, el estado de aprobación ni los artefactos canónicos.

```bash
python -m pip install -r experiments/image_search/requirements.txt -r experiments/video_search/requirements.txt
python -m experiments.media_pack.run \
  --description 'La explosión de Halifax del 6 de diciembre de 1917' \
  --images 20 --videos 4 --output media-pack-output/halifax
```

Requiere `OPENAI_API_KEY` para los mismos modelos de planificación, relevancia y
medio visual del experimento anterior, además de ffmpeg y Node para video.
Las APIs de medios son públicas y no se añadió ningún servicio de pago ni cuenta.
No necesita una nueva clave de descarga. `YOUTUBE_API_KEY` sigue siendo opcional.
La transcripción está desactivada; no se ejecuta ASR. Most Replayed solo existe si
YouTube entrega datos reales; otras fuentes conservan su estado no aplicable.

## Consulta y cantidad

Valores predeterminados: 20 imágenes y 4 videos; máximo 48 imágenes, 8 videos y 54
archivos de medios en total. La cantidad es un objetivo, no una promesa: los
faltantes se conservan explícitamente. La búsqueda principal usa hasta 80
candidatos equilibrados entre proveedores, más hasta dos búsquedas de contexto
si falta material. Cada búsqueda mantiene decisiones y errores por fuente.

Orden de alternativas:

1. Material del tema solicitado con los filtros de identidad y evidencia existentes.
2. Material del mismo tema de menor resolución si faltan imágenes estándar.
3. Lugares, mapas u objetos útiles como contexto editorial si aún faltan piezas.

Los resultados del paso 3 llevan `relation=context`, uso sugerido y limitación.
No sustituyen la identidad de una persona ni demuestran un evento. `--no-context`
los desactiva. El modelo propone contexto; no verifica relaciones históricas
adicionales ni autoriza nuevas afirmaciones para el guion.

Las imágenes estándar conservan el umbral anterior de 200 px en el lado corto y
600 en el largo. Solo este paquete permite bajar hasta 80/160 px, sin ampliación,
con revisión visual y etiqueta `lowres`. Los benchmarks estrictos no cambian.
Las imágenes pequeñas se sugieren para un recuadro, no para llenar una pantalla.

Se priorizan videos de corta duración: completos cuando la duración conocida es
<=180 segundos; en los demás casos se intenta un fragmento inicial de 30 segundos.
Los videos se guardan como proxies de hasta 360p, marcados `lowres`. El fragmento
inicial no garantiza el mejor momento editorial; el editor debe revisarlo.
Los límites de red y seguridad existentes se mantienen. El paquete tiene un
presupuesto de 512 MiB de medios y 30 minutos entre operaciones; una operación
en curso conserva su propio timeout y el job completo tiene un límite de 40 minutos.

## Archivos y trazabilidad

```text
media/images/<tema>__<titulo>__exact-o-context__standard-o-lowres__<fuente>__<id-estable>.jpg
media/videos/<tema>__<titulo>__exact-o-context__lowres__<fuente>__<id-estable>.mp4
manifest.json
gallery.html
SUMMARY.md
SHA256SUMS
```

El nombre es ASCII, acotado y resistente a colisiones mediante hash del ID de
fuente y los bytes. El título original, URL, metadatos, licencia declarada,
dimensiones, duración, fragmento, evaluaciones y llamadas del modelo permanecen
en el manifiesto. La identidad del activo es estable; el orden del editor no
se introduce en el nombre de la fuente. Las imágenes se deduplican por URL,
bytes, píxeles, hash perceptual y familia de catálogo; los videos por URL y
bytes, sin afirmar deduplicación perceptual de montajes distintos.

`exact` significa relevancia aceptada por los filtros de evidencia de catálogo,
no identidad facial ni una tasa de precisión medida. El manifiesto distingue
cantidad exacta, contextual y faltantes. Todos los activos requieren revisar
licencia y montaje antes de publicarse; `production_ready=false`.

## GitHub Actions

Workflow `.github/workflows/media-pack-experiment.yml`, despacho manual o cambio
explícito de `live-request.json` en `experiment/youtube-artifacts`. Una consulta
produce un artefacto ZIP de Actions con medios, galería y trazabilidad. Conserva
también paquetes parciales, con `summary.status=partial/empty`; un job verde
solo indica que acabó la búsqueda. No significa que se cubrió la cantidad.
Retención de los artefactos: 7 días. Las pruebas iniciales usan Halifax (12+3)
y Tsutomu Yamaguchi (6+1), incluyendo el caso antes descartado por resolución.

La integración propuesta se documenta en [INTEGRATION.md](INTEGRATION.md).
