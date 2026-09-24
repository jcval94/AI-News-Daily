# Editorial Grid Search — Results

Completed scripts: **41/60**.

Ranking is cross-validated across three time-separated news folds. Balanced score = 0.30 Editorial + 0.30 Voice + 0.25 Attention + 0.15 SEO, with factuality/AI-smell penalties.

## Configuration ranking

| Rank | Config | CV score | Δ vs current-like | Worst fold | Editorial | Attention | Voice | SEO | Factual low | AI-smell low |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | g03_after_scene_5b | 7.25 | +0.20 | 6.75 | 7.57 | 7.77 | 8.20 | 7.00 | 0% | 67% |
| 2 | g09_fit_minimal_4b | 7.12 | +0.06 | 6.76 | 7.13 | 7.70 | 7.87 | 6.93 | 0% | 100% |
| 3 | g19_turn_minimal_5b | 7.07 | +0.02 | 6.55 | 7.50 | 7.40 | 7.97 | 6.97 | 0% | 67% |
| 4 | g00_current_like | 7.05 | +0.00 | 6.78 | 7.63 | 7.73 | 7.60 | 6.77 | 0% | 67% |
| 5 | g08_fit_dense_6b | 6.94 | -0.11 | 6.86 | 7.23 | 7.33 | 7.57 | 6.77 | 0% | 100% |
| 6 | g12_callback_scene_5b | 6.92 | -0.13 | 6.44 | 7.17 | 7.60 | 7.33 | 6.80 | 0% | 100% |
| 7 | g05_callback_tension_4b | 6.82 | -0.23 | 6.71 | 7.43 | 7.03 | 7.60 | 6.80 | 0% | 67% |
| 8 | g07_forced_scene_fast | 6.70 | -0.35 | 6.42 | 7.67 | 6.97 | 7.47 | 6.67 | 0% | 33% |
| 9 | g04_turn_paradox_5b | 7.08 | +0.03 | 7.04 | 7.30 | 7.60 | 7.80 | 6.70 | 0% | 100% |
| 10 | g17_fit_early_thesis | 7.04 | -0.01 | 7.04 | 7.40 | 6.90 | 8.00 | 7.00 | 0% | 100% |
| 11 | g11_turn_scene_4b | 6.99 | -0.07 | 6.99 | 7.60 | 6.90 | 7.70 | 6.80 | 0% | 100% |
| 12 | g10_after_dense_6b | 6.88 | -0.17 | 6.88 | 7.60 | 6.80 | 7.20 | 7.30 | 0% | 100% |
| 13 | g13_fit_spoken_5b | 6.83 | -0.23 | 6.24 | 7.65 | 7.20 | 7.35 | 7.00 | 0% | 50% |
| 14 | g15_fit_no_counter | 6.82 | -0.23 | 6.73 | 6.90 | 7.15 | 7.80 | 6.50 | 0% | 100% |
| 15 | g06_forced_short_4b | 6.78 | -0.27 | 6.51 | 7.15 | 7.45 | 7.55 | 6.90 | 0% | 50% |
| 16 | g02_fit_tension_4b | 6.78 | -0.28 | 6.31 | 7.50 | 7.30 | 7.50 | 6.50 | 0% | 50% |
| 17 | g01_fit_scene_5b | 6.72 | -0.33 | 6.71 | 7.30 | 7.20 | 7.45 | 6.80 | 0% | 50% |
| 18 | g16_fit_more_evidence | 6.55 | -0.50 | 6.55 | 7.20 | 6.60 | 6.90 | 6.80 | 0% | 100% |
| 19 | g18_after_paradox_4b | 6.40 | -0.65 | 6.40 | 7.20 | 6.80 | 7.50 | 6.60 | 0% | 0% |
| 20 | g14_fit_discovery_4b | 0.00 | -7.05 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0% | 0% |

## Factor signals

Effects are fold-centered. Positive means that factor level tended to score above the mean of the same news fold. Fractional-grid effects are directional, not isolated causal estimates.

### beat_target

| Level | N | Fold-centered Δ | Raw mean |
| --- | ---: | ---: | ---: |
| 8 | 3 | +0.137 | 7.052 |
| 5 | 21 | +0.018 | 6.918 |
| 6 | 4 | -0.025 | 6.925 |
| 4 | 13 | -0.054 | 6.873 |

### cadence

| Level | N | Fold-centered Δ | Raw mean |
| --- | ---: | ---: | ---: |
| "structured" | 6 | +0.080 | 6.995 |
| "discovery" | 29 | +0.030 | 6.944 |
| "spoken" | 6 | -0.224 | 6.691 |

### counterargument

| Level | N | Fold-centered Δ | Raw mean |
| --- | ---: | ---: | ---: |
| "optional" | 8 | +0.055 | 6.952 |
| "required" | 33 | -0.013 | 6.905 |

### evidence_target

| Level | N | Fold-centered Δ | Raw mean |
| --- | ---: | ---: | ---: |
| "1-2" | 9 | +0.087 | 7.002 |
| "3-4" | 8 | +0.012 | 6.926 |
| "2-3" | 24 | -0.037 | 6.878 |

### first_evidence_word_budget

| Level | N | Fold-centered Δ | Raw mean |
| --- | ---: | ---: | ---: |
| 160 | 4 | +0.271 | 7.188 |
| 520 | 3 | +0.137 | 7.052 |
| 180 | 6 | +0.025 | 6.940 |
| 300 | 3 | +0.024 | 6.938 |
| 170 | 12 | -0.026 | 6.889 |
| 190 | 3 | -0.058 | 6.857 |
| 200 | 6 | -0.074 | 6.815 |
| 220 | 2 | -0.191 | 6.720 |
| 210 | 2 | -0.206 | 6.782 |

### memory_policy

| Level | N | Fold-centered Δ | Raw mean |
| --- | ---: | ---: | ---: |
| "narrative_turn" | 6 | +0.145 | 7.060 |
| "after_first_evidence" | 5 | +0.066 | 7.010 |
| "fit_gated" | 16 | -0.018 | 6.878 |
| "closing_callback" | 6 | -0.044 | 6.871 |
| "forced_opening" | 8 | -0.081 | 6.852 |

### memory_word_budget

| Level | N | Fold-centered Δ | Raw mean |
| --- | ---: | ---: | ---: |
| 100 | 2 | +0.174 | 7.085 |
| 180 | 3 | +0.137 | 7.052 |
| 90 | 13 | +0.048 | 6.973 |
| 75 | 8 | +0.023 | 6.920 |
| 80 | 4 | -0.015 | 6.901 |
| 85 | 6 | -0.074 | 6.815 |
| 70 | 2 | -0.206 | 6.782 |
| 65 | 3 | -0.216 | 6.698 |

### opening_style

| Level | N | Fold-centered Δ | Raw mean |
| --- | ---: | ---: | ---: |
| "concrete_scene" | 19 | +0.021 | 6.928 |
| "memory_story" | 5 | -0.000 | 6.944 |
| "paradox_question" | 6 | -0.017 | 6.897 |
| "human_tension" | 11 | -0.027 | 6.887 |

### payoff_callback

| Level | N | Fold-centered Δ | Raw mean |
| --- | ---: | ---: | ---: |
| false | 3 | +0.024 | 6.938 |
| true | 38 | -0.002 | 6.912 |

### thesis_timing

| Level | N | Fold-centered Δ | Raw mean |
| --- | ---: | ---: | ---: |
| "early" | 7 | +0.068 | 7.002 |
| "delayed" | 34 | -0.014 | 6.896 |

## Promotion guardrail

Current top configuration: **g03_after_scene_5b**. Treat it as provisional until all 60 scripts are complete and a human spot-check confirms evaluator alignment.

Prefer the smallest factor-level changes that are robust across folds rather than copying an entire winning prompt wholesale.

## Failures / incomplete cells

- g01_fit_scene_5b / fold_2026_08_31: RuntimeError — Director failed treatment contract: expected exactly 5 beats, got 6
- g02_fit_tension_4b / fold_2026_09_24: RuntimeError — Director failed treatment contract: expected exactly 4 beats, got 7
- g04_turn_paradox_5b / fold_2026_08_31: RuntimeError — Director failed treatment contract: expected exactly 5 beats, got 8
- g06_forced_short_4b / fold_2026_09_04: RuntimeError — Director failed treatment contract: expected exactly 4 beats, got 6
- g10_after_dense_6b / fold_2026_08_31: RuntimeError — Director failed treatment contract: expected exactly 6 beats, got 8
- g10_after_dense_6b / fold_2026_09_04: RuntimeError — Director failed treatment contract: expected exactly 6 beats, got 7
- g11_turn_scene_4b / fold_2026_09_04: RuntimeError — Director failed treatment contract: selected_memory_id not in candidate set: electrification-organizacional-redesign
- g11_turn_scene_4b / fold_2026_09_24: RuntimeError — Director failed treatment contract: expected exactly 4 beats, got 6
- g13_fit_spoken_5b / fold_2026_08_31: RuntimeError — Director failed treatment contract: expected exactly 5 beats, got 8
- g14_fit_discovery_4b / fold_2026_08_31: RuntimeError — Director failed treatment contract: expected exactly 4 beats, got 6
- g14_fit_discovery_4b / fold_2026_09_04: RuntimeError — Director failed treatment contract: expected exactly 4 beats, got 6
- g14_fit_discovery_4b / fold_2026_09_24: RuntimeError — Director failed treatment contract: expected exactly 4 beats, got 5
- g15_fit_no_counter / fold_2026_09_24: RuntimeError — Director failed treatment contract: expected exactly 5 beats, got 7
- g16_fit_more_evidence / fold_2026_08_31: RuntimeError — Director failed treatment contract: expected exactly 5 beats, got 8
- g16_fit_more_evidence / fold_2026_09_24: RuntimeError — Director failed treatment contract: expected exactly 5 beats, got 8
- g17_fit_early_thesis / fold_2026_08_31: RuntimeError — Director failed treatment contract: expected exactly 4 beats, got 6
- g17_fit_early_thesis / fold_2026_09_04: RuntimeError — Director failed treatment contract: evidence_indices outside selected news catalog
- g18_after_paradox_4b / fold_2026_09_04: RuntimeError — Director failed treatment contract: expected exactly 4 beats, got 6
- g18_after_paradox_4b / fold_2026_09_24: RuntimeError — Director failed treatment contract: expected exactly 4 beats, got 5

## Method limitations

- Three folds measure robustness across content, not random-seed variance.
- The same model family writes and evaluates, so human review remains necessary.
- Factor effects are partially confounded because this is a bounded fractional grid.
- No refinement loop is used; architecture quality is measured before repair.

