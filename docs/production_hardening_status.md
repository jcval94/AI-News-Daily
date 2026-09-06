# Production hardening status

## Fixed in this change

- Daily news filenames emitted as `YYYY-MM-DD-HH-MM-SS.txt` are compatible with production source coverage.
- The current `Título:/Fecha:/Fuente:/...` daily digest format is parsed deterministically.
- Source coverage resolves the actual source file per editorial day and records that mapping.
- Timestamped sources are materialized as transient canonical aliases before the existing runtime consumes them.
- Regression tests pin both historical and current source formats, including the live September files already in the repository.
- Editorial Review Hub treats non-publishable terminal states (`no_source_news`, `no_relevant_news`, `no_novel_essay_angle`, `missing_openai_secret`) as successful no-op outcomes instead of failing because `script.txt` is absent.
- Runtime media defaults now match production policy: `MAX_MEDIA_DOWNLOADS=54` and `MEDIA_MIN_RELEVANCE_SCORE=0.22`.
- Configuration contract tests derive workflow expectations from `PIPELINE_ENV_DEFAULTS` so drift is detected in CI.

## Next hardening candidates

- Extract typed domain contracts from `app/agent.py` into a dedicated contracts/domain package.
- Version all persisted inter-stage JSON artifacts explicitly and document compatibility policy.
- Gradually split orchestration responsibilities out of `pipeline/run.py` without changing behavior.

These are architecture improvements; the production P0 failures identified on 2026-09-05 are addressed by this change.
