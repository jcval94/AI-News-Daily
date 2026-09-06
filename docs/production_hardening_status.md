# Production hardening status

## Fixed in this change

- Daily news filenames emitted as `YYYY-MM-DD-HH-MM-SS.txt` are now compatible with production source coverage.
- The current `Título:/Fecha:/Fuente:/...` daily digest format is parsed deterministically.
- Source coverage resolves the actual source file per editorial day and records that mapping.
- Timestamped sources are materialized as transient canonical aliases before the existing runtime consumes them.
- Regression tests pin both historical and current source formats.

## Still to harden

- Editorial Review Hub should explicitly treat non-publishable production states (for example `no_source_news`, `no_relevant_news`, `no_novel_essay_angle`) as graceful no-op outcomes rather than assuming every successful Build artifact contains `script.txt`.
- Runtime/configuration defaults should be consolidated so Python defaults, workflow defaults and documentation cannot drift.

These remaining items are architectural hardening, not blockers for the ingestion fix above.
