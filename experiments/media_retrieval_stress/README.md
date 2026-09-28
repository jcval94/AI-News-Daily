# Multimedia Retrieval Stress Lab

Laboratorio **aislado** para someter a estrés la comprensión semántica que precede a la adquisición de multimedia.

## Frontera de aislamiento

Todo lo relacionado con estas pruebas vive dentro de:

`experiments/media_retrieval_stress/`

Este laboratorio:

- no modifica producción;
- no escribe en `pipeline/`, `app/`, `.github/` ni `tests/`;
- no promueve resultados automáticamente;
- no reutiliza un fallo del experimento como cambio de comportamiento productivo;
- guarda inputs, prompts lógicos, outputs y evaluaciones dentro de su propia carpeta.

## Objetivo de esta primera etapa

Antes de probar proveedores reales, aislar la pregunta más importante:

> **¿La IA entendió exactamente qué multimedia debe buscar?**

Ejemplo canónico:

- narración: `El Mago del Tiempo` dentro de un pasaje de Yu-Gi-Oh!;
- identidad correcta: `Time Wizard`, carta de Yu-Gi-Oh!;
- query válida: `Yu-Gi-Oh Time Wizard trading card Joey Wheeler`;
- drift prohibido: mago genérico, hechicero con reloj, clima, personaje inventado.

Los derechos y la disponibilidad del asset son una etapa posterior. No encontrar un asset reutilizable nunca autoriza a degradar la identidad.

## Capas

```text
cases/
  ↓
contracts/
  ↓
harness/planner
  ↓
deterministic assertions
  ↓
harness/adversarial critic
  ↓
results/
```

### 1. Contracts

Definen qué entra y qué debe salir. Son la fuente de verdad del experimento.

### 2. Planner

Una IA convierte la mención narrativa en una identidad visual exacta y consultas buscables.

### 3. Deterministic assertions

Código sin IA comprueba términos obligatorios/prohibidos, decisión de buscar o rechazar, cardinalidad de queries y grounding.

### 4. Adversarial critic

Una segunda llamada, separada del planner, intenta encontrar drift semántico: homónimos, qualifiers omitidos, negaciones ignoradas, metáforas literalizadas, periodos perdidos, etc.

## Reglas rectoras

1. **Identidad > calidad > cantidad.**
2. Un nombre localizado puede mapearse a un alias canónico, pero la identidad debe permanecer intacta.
3. Un qualifier explícito —franquicia, fabricante, año, geografía, versión— forma parte de la identidad.
4. Una entidad negada es una exclusión, nunca un target.
5. Si la mención es genuinamente ambigua, la salida correcta es `refuse`.
6. Los objetos comerciales/copyright se buscan de forma exacta; los derechos se evalúan después.
7. El planner nunca afirma que un asset existe, está licenciado o fue descargado.
8. Un resultado conceptual no puede satisfacer una necesidad documental exacta.
9. El critic no premia “más resultados”; premia precisión.
10. Todos los runs deben ser reproducibles y auditables.

## Ejecución

Validación local de contratos/casos, sin red:

```bash
python -m experiments.media_retrieval_stress.harness.selftest
```

Stress run con IA:

```bash
OPENAI_API_KEY=... OPENAI_MODEL=... \
python -m experiments.media_retrieval_stress.harness.run \
  --cases experiments/media_retrieval_stress/cases/core.json \
  --repetitions 3
```

Los resultados se escriben exclusivamente en `experiments/media_retrieval_stress/results/`.


## Two-stage stress architecture

The lab now separates two failure surfaces:

### Stage A — semantic planning

Question: **what exactly should we search for?**

Runner:

```bash
python -m experiments.media_retrieval_stress.harness.run \
  --profile experiments/media_retrieval_stress/profiles/core_strict.json \
  --model <MODEL_ID> \
  --enforce
```

This stage catches aliases, namesakes, ambiguity, negation, metaphor literalization,
period/geography loss and generic substitution in search intent.

### Stage B — adversarial candidate selection

Question: **given plausible search results, which assets are actually acceptable?**

Runner:

```bash
python -m experiments.media_retrieval_stress.harness.candidate_run \
  --profile experiments/media_retrieval_stress/profiles/candidate_strict.json \
  --model <MODEL_ID> \
  --enforce
```

The synthetic candidate suite includes:

- exact low-resolution asset vs wrong 4K asset;
- highest-quality duplicate of the same identity;
- historical event vs modern scenic footage;
- Plato bust vs photorealistic anachronism;
- correct long video whose useful scene is after the first 30 seconds;
- relevant metadata with visually useless frames;
- rights-blocked exact asset vs rights-eligible generic substitute;
- prompt injection hidden inside candidate metadata.

Both stages persist raw attempts and a separate scorecard. A scorecard is a verdict over
raw evidence; it never replaces or rewrites that evidence.
