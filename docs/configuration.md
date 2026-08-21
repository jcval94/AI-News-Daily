# Runtime configuration inventory

`pipeline.core.PIPELINE_ENV_DEFAULTS` is the canonical inventory of PipelineConfig environment variables. CI contains a contract test that requires every inventory key to be exposed by the production workflow for both build and report steps.

Repository variables may override defaults in Actions. `NEWS_SOURCE_MODE` and `NEWS_LOOKBACK_DAYS` are resolved from manual/scheduled workflow inputs; all remaining values use the repository variable or the code default.

Do not introduce a new PipelineConfig environment variable without adding it to `PIPELINE_ENV_DEFAULTS` and exposing it in `.github/workflows/build-video-kit.yml`.
