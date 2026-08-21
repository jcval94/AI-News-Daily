# AGENTS.md

This repository builds a twice-weekly AI-news video production kit with Google ADK as the orchestration layer and OpenAI models through `LiteLlm`.

## Core production contract

- Tuesday episodes consume the available Friday, Saturday, Sunday and Monday `news/YYYY-MM-DD.txt` files.
- Friday episodes consume the available Tuesday, Wednesday and Thursday files.
- Missing daily files are non-fatal. Continue with what exists; if the entire window is empty, exit cleanly without inventing content.
- Select at most 8 relevant stories and remove semantic duplicates, including events already used in recent episodes unless there is a materially new development.
- Keep Google ADK as orchestrator and `OPENAI_API_KEY` as the required model credential.
- Default model is `gpt-5.4-nano` unless `OPENAI_MODEL` overrides it.

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

- editorial score >= 8.7,
- factuality risk == `low`,
- SEO Master score >= 8.5,
- YouTube Attention Master score >= 8.5.

If the refinement limit is reached without unanimous approval, save the script/reviews and skip multimedia.

## Multimedia contract

- 00:00-00:15 uses one slot every 3 seconds.
- After 00:15, use one slot every 4 seconds.
- `presenter` means no external media download.
- `media` means exactly one external visual may be downloaded for that slot.
- `MAX_MEDIA_DOWNLOADS` is a hard cap.
- `DOWNLOAD_MULTIMEDIA=false` must still allow script/edit-plan generation.

## Important paths

- `news/`: raw source digests; do not rewrite historical files during unrelated work.
- `app/agent.py`: ADK agents and schemas.
- `pipeline/run.py`: deterministic production orchestration.
- `pipeline/report.py`: post-run observability; must not invoke an LLM or require model initialization.
- `pipeline/media.py`: external media retrieval.
- `scripts/YYYY-MM-DD/`: script, selected stories, reviews and `run_report.json`.
- `multimedia/YYYY-MM-DD/`: editor plan, manifest and selected assets.
- `videos/`: reserved for the future renderer.
- `.github/workflows/build-video-kit.yml`: production schedule and E2E execution.

## run_report.json contract

Every attempted episode should produce `scripts/YYYY-MM-DD/run_report.json` when the reporting step can run. The report is derived from persisted artifacts rather than agent internals so observability remains decoupled from generation.

At minimum record:

- episode/build status,
- expected, available and missing source dates,
- model and relevant configuration,
- selected-news count and duplicate count,
- script existence, word count, duration estimate and approval status,
- final scores/approval for all three judges,
- multimedia slot counts and downloaded/fallback asset counts,
- artifact paths.

The report should still be generated after a pipeline failure when GitHub Actions reaches the reporting step.

## Change discipline

Prefer the smallest change that satisfies the task. In particular:

- preserve Tuesday/Friday windows,
- preserve missing-file tolerance,
- preserve max-8 selection,
- preserve all three judges,
- preserve media-only-after-approval,
- preserve 3-second cadence for the first 15 seconds,
- do not change `pipeline/media.py`, dependencies or workflow permissions unless the task actually requires it.

When agent schemas or `output_key` values change, update every consumer in the same change.

## Validation

Before considering a change complete, validate at minimum:

- `python -m compileall app pipeline`,
- Tuesday and Friday source-date mapping,
- missing daily source files do not crash the run,
- selector cannot exceed 8 items,
- first 15 seconds create five 3-second slots,
- later slots use 4-second cadence,
- failed judge approval skips multimedia,
- media count never exceeds `MAX_MEDIA_DOWNLOADS`,
- `pipeline.report` can build a report without calling OpenAI.

The production workflow should remain scheduled on Tuesday/Friday. Any branch-only E2E push trigger must be explicitly scoped so it does not make `main` run the expensive pipeline on every push.
