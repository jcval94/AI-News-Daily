# Editorial Grid Search with 3-fold cross-validation

## Goal

Measure which editorial architecture reliably improves **Editorial, Attention, Voice and SEO** after the recent drop associated with forcing Narrative Memory into every opening.

This experiment is isolated from production.

## Sample

- 20 editorial configurations.
- 3 time-separated content folds.
- 1 independently generated script per configuration/fold.
- **60 scripts total**.

The three scripts per configuration are content folds, not three stochastic rewrites of one topic. The purpose is robustness across different news days.

## Ten factors

1. Narrative Memory placement.
2. Opening style.
3. Narrative Memory word budget.
4. Maximum words before first current evidence.
5. Number of large narrative beats.
6. Evidence breadth.
7. Required vs optional counterargument.
8. Early vs delayed thesis.
9. Structured, discovery or spoken cadence.
10. Required opening/payoff callback.

The reference arm is **g00_current_like**.

## Controls

- Roughly 1,450 words for every arm.
- Every arm still uses one verified Narrative Memory item.
- Same three folds for every arm.
- Same voice/discourse profiles.
- No refinement loop: first-pass architecture only.
- Evaluator is blind to treatment and plan.
- One evaluator returns all headline metrics in a single pass.
- Evaluator is neutral to memory placement.

## Primary score

Balanced score = 0.30 Editorial + 0.30 Voice + 0.25 Attention + 0.15 SEO, with modest penalties for medium/high factuality risk and AI-smell risk.

Diagnostics also capture voice fidelity, intellectual depth, human relevance, analogy quality, opening fit, first-evidence effectiveness, narrative motion, thesis evolution and evidence density.

## Cross-validation analysis

A configuration is complete only with 3/3 folds.

Factor effects are computed on **fold-centered scores**: each result is compared with the mean of its own fold before aggregating by factor value. This reduces the effect of some news days simply being easier.

This is a bounded fractional grid, not the full Cartesian product, so factor effects are directional/associative rather than clean causal estimates.

## Outputs

- results/raw/: one JSON scorecard per configuration/fold.
- results/scripts/: generated scripts.
- results/summary.csv: configuration CV table.
- results/factor_effects.csv: factor signals.
- results/RESULTS.md: readable conclusions.
- results/run_manifest.json: completion audit.

## Promotion rule

Nothing becomes production behavior automatically. After results, promote only the smallest changes supported across folds, then validate them in the real pipeline.
