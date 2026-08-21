# Editorial regression set

This directory contains **real E2E outputs** recovered from GitHub Actions artifacts and the human editorial disposition they received during review. It is not synthetic gold data.

Current baseline: three human-rejected full scripts. That is enough to measure obvious false-accept behavior, but **not enough to calibrate deterministic voice-dimension thresholds or justify changing judge models** because there are no human-approved full scripts yet.

Run:

```bash
python -m pipeline.editorial_calibration --cases evals/editorial/cases.json
```

Activation policy: collect at least five full human-labeled scripts with at least two accepted and two rejected examples before enabling dimension floors or judge-model diversification.
