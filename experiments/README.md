# Experiments

This directory contains isolated, reproducible experiments for AI News Daily.

Rules:
- Experiments must not silently change production.
- Every experiment documents hypothesis, inputs, controls, evaluation and limitations.
- Raw outputs stay inside the experiment.
- Promotion to production requires a separate explicit change.

Current experiment: editorial_grid_search — 20 editorial configurations x 3 content folds = 60 scripts.

`notebook_story_flow` reproduces JC's historical epic / hero workflow with a long
unresolved opening and a late documented payoff. It runs independently after each
production episode and keeps every output and approval decision experimental.
