# Multimedia Retrieval Stress Suite

Este experimento prueba una pregunta distinta a la de densidad o readiness:

> **¿El pipeline entendió qué elemento visual se pidió y recuperó candidatos del sujeto correcto?**

La prueba está separada deliberadamente de **Media Integration Staging**. Staging prueba descarga, licencia, decodificación, empaquetado, 45/5 y readiness. Este gauntlet prueba antes de eso: resolución semántica, desambiguación, construcción de queries, discovery y selección por relevancia.

## Caso canónico

La narración puede decir:

> “En Yu-Gi-Oh!, una de las cartas más reconocibles de Joey era **El Mago del Tiempo**.”

El sistema debe conservar `retrieval_subject="El Mago del Tiempo"`, pero su query visual puede resolver la referencia como `Yu-Gi-Oh Time Wizard trading card Joey`. Una foto genérica de un mago o una referencia meteorológica cuentan como **FAIL_WRONG_ENTITY**. Si la identidad se entiende pero ninguna fuente reutilizable supera derechos/procedencia, se registra **SEMANTIC_ONLY**: mejor una carencia honesta que multimedia incorrecta.

## Qué estresa

El corpus cubre alias localizados y franquicias; homónimos; marcas que son palabras comunes; versiones exactas de hardware; eventos frente a lugares; personas anteriores a la fotografía; ambigüedad geográfica; periodos históricos; objetos raros; personas frente a eventos asociados; ambigüedad real que debe fallar cerrada; metáforas; negaciones; material correcto que aparece tarde dentro de un video; títulos correctos con contenido visual inútil; baja resolución exacta frente a stock HD incorrecto; y metadata no confiable.

Dos casos de video se consideran especialmente importantes:

1. **clip offset**: hoy la adquisición de un video largo corta `0–30 s`. Un video puede ser correcto por metadata y, aun así, la escena útil estar en 04:20. El reporte marca `CURRENT_PIPELINE_CLIPS_FROM_ZERO_0_30S`.
2. **metadata/visual mismatch**: título y descripción pueden ser perfectos pero el clip ser un podcast, una diapositiva estática o un talking head. El reporte marca `METADATA_RELEVANCE_WITHOUT_FRAME_LEVEL_VISUAL_PROOF`.

## Ejecución

Validación determinista, sin red ni modelo:

```bash
python -m experiments.media_retrieval_stress.run --profile core --enforce
```

Gauntlet real contra planificadores y proveedores:

```bash
OPENAI_API_KEY=... python -m experiments.media_retrieval_stress.run --profile core --live
```

Suite completa:

```bash
OPENAI_API_KEY=... python -m experiments.media_retrieval_stress.run --profile full --live
```

Añadir `--enforce` sólo cuando se quiera convertir el baseline observado en gate. Por defecto el live gauntlet **conserva los fallos en el artefacto sin maquillarlos ni romper CI**, porque su primera función es descubrir huecos.

Salidas:

- `results/latest.json`: evidencia estructurada por caso, plan, discovery y candidatos seleccionados.
- `results/latest.md`: resumen humano y taxonomía de fallos.

## Estados principales

- `PASS_SELECTED`: un candidato del sujeto correcto sobrevivió la selección.
- `SEMANTIC_ONLY`: se entendió la identidad pero no llegó un candidato reutilizable. Es una degradación diagnosticada, **no un pass**; `may_be_rights_blocked` sólo explica que el hueco puede ser esperable por derechos/proveedor.
- `FAIL_WRONG_ENTITY`: sobrevivió una colisión prohibida.
- `FAIL_NO_RESOLUTION`: ni el plan de búsqueda expresó la identidad deseada.
- `PASS_AMBIGUITY_REFUSED`: el pipeline prefirió no adivinar.
- `FAIL_AMBIGUITY_ACCEPTED`: eligió una interpretación sin contexto suficiente.

## Criterio editorial

La prioridad es **identidad > calidad física > cantidad**.

Una imagen exacta de baja resolución debe quedar etiquetada como lowres, pero es preferible a una imagen HD de otra cosa. Para roles documentales, “no encontré material elegible” es una salida válida; sustituirlo silenciosamente por stock genérico no lo es.
