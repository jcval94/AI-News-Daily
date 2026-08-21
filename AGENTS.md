# AGENTS.md

This repository builds a twice-weekly AI-news video production kit with Google ADK as the orchestration layer and OpenAI models through `LiteLlm`.

## Core production contract

- Tuesday episodes consume the available Friday, Saturday, Sunday and Monday `news/YYYY-MM-DD.txt` files.
- Friday episodes consume the available Tuesday, Wednesday and Thursday files.
- Missing daily files are non-fatal. Continue with what exists; if the entire window is empty, exit cleanly without inventing content.
- Select at most 8 relevant stories and remove semantic duplicates.
- Cross-episode deduplication must use only previously **approved** canonical episodes. Failed/rejected attempts must never burn a story.
- Keep Google ADK as orchestrator and `OPENAI_API_KEY` as the required model credential.
- Default model is `gpt-5.4-nano` unless `OPENAI_MODEL` overrides it.

## Script duration contract

- Final narration must be between **7 and 12 minutes**.
- Default deterministic bounds are `TARGET_MIN_SECONDS=420` and `TARGET_MAX_SECONDS=720`.
- At `WORDS_PER_SECOND=2.5`, that is roughly 1050–1800 words.
- Target depth should scale with selected material: fewer/shallow stories toward 7 minutes, more/deeper stories toward 12 minutes.
- Do not pad with filler.
- Duration is a deterministic runtime gate in addition to LLM judging. Never reintroduce a hard upper clamp such as 100 seconds in duration estimation or visual timeline construction.

## Agent order

1. `news_relevance_selector`
2. `youth_script_writer`
3. `script_quality_loop`, containing:
   - editorial/factual critic,
   - SEO Master,
   - YouTube Attention Master,
   - quality gate,
   - refiner.
4. `multimedia_editor_master` only after deterministic approval.

Do not bypass the runtime approval check even when an LLM returns `approved=true`.

Default approval requirements:

- duration between 420 and 720 seconds,
- editorial score >= 8.7,
- factuality risk == `low`,
- SEO Master score >= 8.5,
- YouTube Attention Master score >= 8.5.

If the refinement limit is reached without unanimous/deterministic approval, save the attempt in the isolated run workspace and skip multimedia/promotion.

## Run isolation and promotion

Production GitHub Actions must never generate directly into canonical episode directories.

Each attempt writes to:

```text
.pipeline-runs/<episode-date>/<run-id>/scripts/
.pipeline-runs/<episode-date>/<run-id>/multimedia/
```

Only an approved run may replace:

```text
scripts/<episode-date>/
multimedia/<episode-date>/
```

A rejected/failed rerun must leave the previous canonical approved episode untouched. Its `run_report.json` remains available in the isolated workflow artifact.

## Multimedia contract

- 00:00–00:15 uses one slot every 3 seconds.
- After 00:15, use one slot every 4 seconds.
- The timeline must cover the full narration duration; never truncate long narration.
- The Multimedia Editor returns only slots that require external media. Omitted timeline slots default to `presenter`.
- `media` means exactly one external visual may be downloaded for that slot.
- `MAX_MEDIA_DOWNLOADS` is a hard cap.
- `DOWNLOAD_MULTIMEDIA=false` must still allow script/edit-plan generation.

## Important paths

- `news/`: raw source digests; do not rewrite historical files during unrelated work.
- `app/agent.py`: ADK agents and schemas.
- `pipeline/run.py`: deterministic production orchestration and gates.
- `pipeline/report.py`: post-run observability; must not invoke an LLM or require model initialization.
- `pipeline/media.py`: external media retrieval.
- `scripts/YYYY-MM-DD/`: canonical **approved** episode script, selected stories, reviews and `run_report.json`.
- `multimedia/YYYY-MM-DD/`: canonical **approved** editor plan, manifest and selected assets.
- `videos/`: reserved for the future renderer.
- `.github/workflows/build-video-kit.yml`: production schedule, isolated workspace, reporting and promotion.

## run_report.json contract

Every attempted Actions episode should produce an isolated `run_report.json` when the reporting step can run. Only an approved run is promoted into `scripts/YYYY-MM-DD/run_report.json`.

At minimum record:

- episode/build status,
- GitHub run ID / commit SHA when available,
- expected, available and missing source dates,
- model and relevant configuration,
- selected-news count and duplicate count,
- script existence, word count, duration estimate and approval status,
- final scores/approval for all three judges,
- multimedia slot counts and downloaded/fallback asset counts,
- artifact paths.

## Workflow outcome semantics

- `approved`: successful and eligible for canonical promotion.
- `no_source_news`: successful no-op; no fabricated episode.
- `script_not_approved`: non-publishable and should fail visibly after preserving the isolated report/artifact.
- configuration/runtime `failure`: fail visibly after reporting when possible.

## Change discipline

Prefer the smallest change that satisfies the task. Preserve:

- Tuesday/Friday windows,
- missing-file tolerance,
- max-8 selection,
- all three judges,
- deterministic 7–12 minute duration gate,
- media-only-after-approval,
- 3-second cadence for the first 15 seconds,
- isolated-run-before-promotion semantics.

When agent schemas or `output_key` values change, update every consumer in the same change.

## Validation

Before considering a change complete, validate at minimum:

- `python -m compileall app pipeline`,
- Tuesday and Friday source-date mapping,
- missing daily source files do not crash the run,
- selector cannot exceed 8 items,
- unapproved episodes are excluded from cross-episode history,
- 7-minute and 12-minute scripts pass the deterministic duration boundary while shorter/longer scripts fail,
- timeline duration never truncates narration,
- first 15 seconds create five 3-second slots,
- later slots use 4-second cadence,
- failed judge/duration approval skips multimedia and promotion,
- media count never exceeds `MAX_MEDIA_DOWNLOADS`,
- `pipeline.report` can build a report without calling OpenAI.
