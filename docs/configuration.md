# Runtime configuration inventory

`pipeline.core.PIPELINE_ENV_DEFAULTS` is the canonical inventory **and canonical default-value source** for `PipelineConfig` environment variables. CI contains contract tests that require the production workflow to expose every inventory key and that pin important production defaults to the same values used by Python.

Repository variables may override defaults in Actions. `NEWS_SOURCE_MODE` and `NEWS_LOOKBACK_DAYS` are resolved from manual/scheduled workflow inputs; all remaining values use the repository variable or the code default.

Current production media defaults are `MAX_MEDIA_DOWNLOADS=54` and `MEDIA_MIN_RELEVANCE_SCORE=0.22`.

Do not introduce a new `PipelineConfig` environment variable or duplicate a default value in a new config artifact. Add the variable to `PIPELINE_ENV_DEFAULTS`, expose it in `.github/workflows/build-video-kit.yml`, and extend the configuration contract test when the workflow has special handling for that variable.
