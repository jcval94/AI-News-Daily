# Editorial Grid Search — Final 20 × 3 CV

**Estado:** completo. Se generaron y evaluaron **60/60 guiones**: 20 configuraciones × 3 ventanas temporales independientes.

## Resultado principal

La señal más consistente no fue “quitar Narrative Memory”, sino **moverla fuera de la apertura obligatoria y reducir el número de casos actuales**. El mejor tratamiento fue `g19_turn_minimal_5b`: 1–2 evidencias actuales, Narrative Memory como giro narrativo intermedio, 5 beats y tesis descubierta progresivamente.

Frente al brazo `g00_current_like` (historia obligatoria al abrir, 8 beats, 3–4 evidencias), `g19` mejoró el score balanceado medio en **+0.56 puntos**, y ganó en los tres folds (+0.95, +0.56 y +0.16). Su peor fold fue 6.89 vs 5.94 del baseline.

## Ranking completo

| # | Config | CV | Δ pareado vs baseline | Peor fold | Editorial | Attention | Voice | SEO | Longitud OK |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `g19_turn_minimal_5b` | 7.28 | +0.56 | 6.89 | 7.77 | 7.23 | 8.17 | 6.97 | 100% |
| 2 | `g12_callback_scene_5b` | 7.08 | +0.35 | 6.67 | 7.20 | 7.53 | 8.10 | 6.37 | 100% |
| 3 | `g15_fit_no_counter` | 7.03 | +0.31 | 6.58 | 7.63 | 7.50 | 7.70 | 6.83 | 100% |
| 4 | `g11_turn_scene_4b` | 7.03 | +0.30 | 6.79 | 7.20 | 7.37 | 7.83 | 6.83 | 100% |
| 5 | `g10_after_dense_6b` | 6.97 | +0.24 | 6.23 | 7.47 | 7.33 | 7.60 | 7.20 | 33% |
| 6 | `g06_forced_short_4b` | 6.92 | +0.19 | 5.86 | 7.60 | 7.23 | 7.60 | 6.77 | 100% |
| 7 | `g09_fit_minimal_4b` | 6.88 | +0.15 | 6.71 | 7.23 | 7.17 | 7.63 | 6.50 | 100% |
| 8 | `g17_fit_early_thesis` | 6.87 | +0.14 | 6.33 | 7.53 | 7.43 | 7.27 | 6.90 | 0% |
| 9 | `g13_fit_spoken_5b` | 6.75 | +0.03 | 6.45 | 7.10 | 7.10 | 7.63 | 6.83 | 100% |
| 10 | `g00_current_like` | 6.73 | +0.00 | 5.94 | 7.17 | 7.13 | 7.63 | 6.47 | 67% |
| 11 | `g18_after_paradox_4b` | 6.65 | -0.08 | 6.61 | 7.13 | 7.50 | 7.40 | 6.63 | 67% |
| 12 | `g14_fit_discovery_4b` | 6.65 | -0.08 | 6.45 | 7.13 | 7.03 | 7.37 | 6.70 | 100% |
| 13 | `g07_forced_scene_fast` | 6.62 | -0.11 | 6.08 | 7.07 | 7.03 | 7.80 | 6.57 | 100% |
| 14 | `g16_fit_more_evidence` | 6.59 | -0.14 | 6.29 | 7.17 | 6.83 | 7.33 | 6.63 | 33% |
| 15 | `g02_fit_tension_4b` | 6.57 | -0.16 | 6.19 | 7.30 | 6.93 | 7.43 | 6.67 | 67% |
| 16 | `g08_fit_dense_6b` | 6.56 | -0.17 | 6.22 | 7.20 | 6.97 | 7.43 | 6.73 | 33% |
| 17 | `g03_after_scene_5b` | 6.56 | -0.17 | 6.34 | 7.17 | 6.70 | 7.70 | 6.70 | 67% |
| 18 | `g04_turn_paradox_5b` | 6.42 | -0.31 | 5.75 | 6.93 | 6.97 | 7.37 | 6.47 | 67% |
| 19 | `g05_callback_tension_4b` | 6.30 | -0.43 | 5.93 | 6.70 | 6.50 | 6.97 | 6.93 | 67% |
| 20 | `g01_fit_scene_5b` | 6.20 | -0.53 | 4.82 | 6.27 | 6.77 | 7.20 | 6.23 | 67% |

## Qué parece mover la aguja

- **memory_policy:** mejor señal `"narrative_turn"` (+0.178); peor `"fit_gated"` (-0.055).
- **opening_style:** mejor señal `"memory_story"` (+0.090); peor `"paradox_question"` (-0.164).
- **memory_word_budget:** mejor señal `70` (+0.185); peor `100` (-0.313).
- **first_evidence_word_budget:** mejor señal `210` (+0.185); peor `220` (-0.531).
- **beat_target:** mejor señal `6` (+0.031); peor `5` (-0.006).
- **evidence_target:** mejor señal `"1-2"` (+0.088); peor `"3-4"` (-0.022).
- **counterargument:** mejor señal `"optional"` (+0.041); peor `"required"` (-0.007).
- **thesis_timing:** mejor señal `"delayed"` (+0.003); peor `"early"` (-0.014).
- **cadence:** mejor señal `"discovery"` (+0.024); peor `"structured"` (-0.089).
- **payoff_callback:** mejor señal `true` (+0.009); peor `false` (-0.173).

## Lectura editorial

- **Narrative Memory funciona mejor como giro que como obligación de apertura.** `narrative_turn` tuvo la señal agregada más positiva (+0.178); `g19` y `g11` están ambos en el top 4. Esto encaja con la hipótesis inicial: la historia aporta cuando reinterpreta algo ya concreto.
- **Menos evidencia fue mejor.** El nivel `1-2` tuvo la mejor señal (+0.088). La amplitud de casos parece empujar al texto hacia dossier/lista.
- **Discovery cadence ayudó; “spoken” por sí solo no.** No basta pedir frases respirables: la estructura debe producir descubrimiento real.
- **4 vs 5 vs 6 beats no mostró una señal grande por sí solo.** El placement de la historia y la anchura de evidencia fueron más claros que el conteo bruto de beats.
- **La apertura concreta ayuda, pero no domina por sí sola.** El mejor tratamiento (`g19`) abre desde tensión humana y reserva la historia para el giro; por eso no conviene convertir “concrete_scene” en una nueva regla rígida.

## Caveat importante de factualidad

El evaluador clasificó **59/60 guiones con riesgo factual `medium` y solo 1/60 como `low`**. Por eso este experimento es mucho más útil para comparar **arquitectura narrativa relativa** que para declarar que un guion ya está listo para publicación. El score balanceado penaliza ese riesgo, pero no debe interpretarse como sustituto del gate factual de producción.

## Longitud

El control de longitud mejoró, pero no fue perfecto: **44/60** guiones quedaron dentro del rango objetivo tras un máximo de dos intentos. La longitud se reporta explícitamente y no se oculta en el ranking.

## Recomendación de promoción

Promovería primero una variante mínima basada en `g19`, no el prompt completo: **Narrative Memory obligatoria pero preferentemente como `narrative_turn`; 1–2 evidencias fuertes; 4–5 beats; primera evidencia temprano; tesis que evoluciona; callback final solo cuando esté ganado.** Después la validaría en el pipeline real con el juez factual actual y refinamiento normal.

No recomiendo convertir ninguno de estos resultados en una nueva regla absoluta: con n=3 folds por configuración, las señales deben usarse como dirección de diseño y confirmarse con más episodios reales.

## Trazabilidad

- GitHub Actions run de la ejecución final: `36073833346`.
- `scores.jsonl`: scorecard compacto de los 60 guiones.
- `scripts_index.csv`: índice fold/configuración, longitud, score y artifact ID.
- `scripts/`: tres guiones completos por configuración.
- `summary.csv`: resumen CV por configuración.
- `factor_effects.csv`: efectos fold-centered por nivel de factor.
