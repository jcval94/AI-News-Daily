# AI News Daily — Production Agentic Video Kit

A twice-weekly AI-news production pipeline built to be understandable as a small production agentic system.

## Architecture principle

**LLMs propose and judge; deterministic code controls the workflow.**

Google ADK provides the agent runtime (`Agent`, `Runner`, session state). `pipeline/run.py` owns the production state machine: retries, validation, refinement iterations, duration gates, output promotion, and side effects. This avoids using an LLM as the final authority for business-critical control flow.

### Agent roles

1. `news_relevance_selector` — selects at most 8 unique, high-value stories.
2. `youth_script_writer` — writes the first 7–12 minute Spanish narration.
3. `script_critic` — factual/editorial judge.
4. `seo_master` — YouTube SEO judge.
5. `youtube_attention_master` — hook/retention judge.
6. `script_refiner` — revises the script from judge feedback.
7. `multimedia_editor_master` — selects only slots where external media adds value.

There is **no LLM quality-gate agent**. Python evaluates the final gate deterministically.

## Production cadence

- **Tuesday:** use available Friday, Saturday, Sunday, Monday files.
- **Friday:** use available Tuesday, Wednesday, Thursday files.
- Missing daily files are non-fatal.
- If no source exists, status is `no_source_news`.
- If sources exist but nothing is worth publishing, status is `no_relevant_news`.

Daily source inputs remain `news/YYYY-MM-DD.txt`.

## Episode states

`run_state.json` is the authoritative machine-readable state for an attempted episode:

- `approved` — publishable and eligible for canonical promotion.
- `no_source_news` — clean skip; no source files.
- `no_relevant_news` — clean skip; sources existed but selector chose nothing.
- `script_not_approved` — refinement limit reached without passing every gate.
- `failure` — unexpected runtime failure.
- `missing_openai_secret` — workflow preflight failure.

Only `approved` runs may replace canonical `scripts/<date>/` and `multimedia/<date>/` outputs.

## Quality loop

The production loop is explicit Python orchestration:

```text
select → write → [editorial + SEO + attention judges]
                    ↓
             deterministic gate
               ↙          ↘
          refine          approved
             ↖              ↓
              └────── multimedia plan
```

Default deterministic approval requires:

- narration between **420 and 720 seconds** (7–12 minutes),
- editorial score >= 8.7,
- editorial `factuality_risk == low`,
- SEO score >= 8.5,
- Attention score >= 8.5,
- all three judges explicitly approve.

The loop runs at most `MAX_REFINEMENT_ITERATIONS` times.

## Retries

Agent calls retry only likely transient failures (rate limits, timeouts, connection/service errors) with bounded exponential backoff. Invalid input/configuration errors are not retried.

Defaults:

```text
AGENT_MAX_ATTEMPTS=3
AGENT_RETRY_BASE_SECONDS=2.0
MEDIA_HTTP_MAX_ATTEMPTS=3
```

Media API/download retries are independent from model retries. If both Pexels and Wikimedia fail, the pipeline creates a local fallback card instead of aborting the whole approved kit.

## Isolation and outputs

GitHub Actions builds each attempt under:

```text
.pipeline-runs/<episode-date>/<github-run-id>/
```

This prevents stale files from previous attempts being mixed with a new script.

An approved run is promoted to:

```text
scripts/YYYY-MM-DD/
├── run_state.json
├── execution_trace.json
├── run_report.json
├── selected_news.json
├── script.txt
└── reviews.json

multimedia/YYYY-MM-DD/
├── plan.json
├── manifest.json
└── assets/

videos/  # reserved for future final rendering
```

Failed/non-publishable attempts remain available as GitHub Actions artifacts but are not promoted.

## Observability

`execution_trace.json` records each agent attempt:

- logical step and agent,
- refinement iteration,
- attempt number,
- success/error,
- elapsed seconds,
- retryability,
- error class/message,
- ADK token usage when `usage_metadata` is available.

`run_report.json` derives a durable episode report from persisted artifacts and includes:

- episode state and reason,
- source window and SHA-256 source hashes,
- effective configuration,
- selected stories and duplicates,
- final deterministic gate and judge scores,
- retry/attempt counts and token usage,
- multimedia/fallback/provider-error counts,
- SHA-256 hashes for generated artifacts.

This makes a run auditable without depending on console logs.

## Multimedia timing

- First 15 seconds: deterministic 3-second slots.
- After 15 seconds: 4-second slots.
- Omitted editor slots = presenter/on-camera.
- Returned editor slots = external media.
- `MAX_MEDIA_DOWNLOADS` is a hard runtime cap.

## Configuration

Required secret:

```text
OPENAI_API_KEY
```

Optional secret:

```text
PEXELS_API_KEY
```

Useful repository variables:

```text
OPENAI_MODEL=gpt-5.4-nano
SCRIPT_QUALITY_THRESHOLD=8.7
JUDGE_THRESHOLD=8.5
MAX_REFINEMENT_ITERATIONS=5
MAX_MEDIA_DOWNLOADS=12
DOWNLOAD_MULTIMEDIA=true
SELECTION_HISTORY_DAYS=30
TARGET_MIN_SECONDS=420
TARGET_MAX_SECONDS=720
WORDS_PER_SECOND=2.5
AGENT_MAX_ATTEMPTS=3
AGENT_RETRY_BASE_SECONDS=2.0
MEDIA_HTTP_MAX_ATTEMPTS=3
```

## Validation

Deterministic CI runs without API secrets:

```bash
python -m compileall app pipeline
python -m unittest discover -s tests -v
```

A real model/media E2E remains available through **Actions → Build AI News Video Kit → Run workflow**. Production also runs Tuesday/Friday at 09:00 America/Mexico_City.
