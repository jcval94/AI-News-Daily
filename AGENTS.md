# AGENTS.md

This repository builds a twice-weekly AI-news video production kit with Google ADK as the orchestration layer and OpenAI models through `LiteLlm`.

## Repository goal

Transform daily AI-news inputs under `news/YYYY-MM-DD.txt` into a high-quality, youth-oriented Spanish video script and only then create the multimedia plan/assets required for production.

Production runs are intentionally twice weekly:

- Tuesday: consume the available Friday, Saturday, Sunday and Monday news files.
- Friday: consume the available Tuesday, Wednesday and Thursday news files.

Missing daily files are non-fatal. Continue with the files that exist. If the entire expected window is empty, exit successfully without fabricating content.

## Important directories

- `news/`: raw daily AI-news digests. Treat these as source material; do not rewrite historical inputs as part of unrelated changes.
- `app/agent.py`: ADK agents, schemas, editorial judges and Multimedia Editor Master.
- `pipeline/run.py`: deterministic orchestration around the agents, schedule-window logic, approval gates, output persistence and media download decisions.
- `pipeline/media.py`: external asset retrieval and local fallback generation. Avoid changing this unless media-provider behavior itself needs to change.
- `scripts/YYYY-MM-DD/`: generated script, selected-news record and judge outputs for an episode.
- `multimedia/YYYY-MM-DD/`: edit plan, manifest and downloaded assets for approved scripts only.
- `videos/`: reserved for future final rendered videos.
- `.github/workflows/build-video-kit.yml`: Tuesday/Friday scheduled production and manual dispatch.

## Agent pipeline contract

Keep the pipeline order stable unless the requested feature explicitly requires otherwise:

1. `news_relevance_selector`
   - Select at most 8 stories.
   - Remove semantic duplicates inside the current editorial window.
   - Check recent `scripts/*/selected_news.json` history and avoid reusing the same event unless there is a materially new development.
2. `youth_script_writer`
   - Produce a factual Spanish script for roughly ages 16-28.
   - Use selected stories only; raw news remains the factual source of truth.
3. `script_quality_loop`
   - Editorial/factual critic.
   - SEO Master.
   - YouTube Attention Master.
   - Quality gate.
   - Refiner.
4. Only after all judges pass the deterministic thresholds, call `multimedia_editor_master`.
5. Download assets only for segments classified as `media`; never download external assets for `presenter` segments.

Do not bypass the deterministic approval check in `pipeline/run.py` even if an LLM returns `approved=true`.

## Script approval requirements

Default thresholds are currently:

- editorial score >= 8.7,
- factuality risk == `low`,
- SEO Master score >= 8.5,
- YouTube Attention Master score >= 8.5.

Thresholds are configurable through environment/repository variables. The runtime gate must evaluate both the boolean approval and numeric score.

If the iteration cap is reached without unanimous approval:

- save the script and reviews for diagnosis,
- do not call the multimedia editor,
- do not download multimedia.

## Multimedia timing contract

The timeline is deterministic before the editor makes content decisions:

- 00:00-00:15: one slot every 3 seconds,
- after 00:15: one slot every 4 seconds.

The editor decides each slot as either:

- `presenter`: person on camera, no external asset,
- `media`: one useful external visual asset.

Respect `MAX_MEDIA_DOWNLOADS` as a hard cap. If a model asks for more media slots than allowed, the runner must degrade the excess safely to `presenter` rather than downloading extra assets.

`DOWNLOAD_MULTIMEDIA=false` must still allow script and edit-plan generation while skipping external downloads.

## Model and credentials

- Required secret: `OPENAI_API_KEY`.
- Optional secret: `PEXELS_API_KEY`.
- Default model: `gpt-5.4-nano`.
- Model override: `OPENAI_MODEL`.

Google ADK remains the orchestrator. OpenAI is connected through ADK's `LiteLlm`; do not replace ADK with direct OpenAI orchestration unless the task explicitly asks for an architectural migration.

Never commit API keys, tokens, credentials or generated `.env` files.

## Change discipline

Prefer the smallest change that satisfies the request.

Before editing:

- inspect the current branch and relevant files,
- preserve the Tuesday/Friday window behavior,
- preserve missing-file tolerance,
- preserve the maximum-8-news invariant,
- preserve the three-judge approval gate,
- preserve media-only-after-approval behavior,
- preserve the 3-second first-15-seconds timing contract.

Avoid broad refactors while fixing a focused issue. Do not modify `news/` history, `pipeline/media.py`, dependencies or workflow permissions unless the requested change actually requires it.

## Validation expectations

At minimum, validate:

- Python syntax with `python -m compileall app pipeline`.
- Tuesday date mapping: Friday/Saturday/Sunday/Monday.
- Friday date mapping: Tuesday/Wednesday/Thursday.
- missing daily files do not crash the pipeline.
- a completely empty window exits cleanly.
- selector returns no more than 8 stories.
- first 15 seconds produce exactly five 3-second slots.
- later slots use 4-second cadence.
- multimedia is skipped when judge approval fails.
- multimedia downloads never exceed `MAX_MEDIA_DOWNLOADS`.

When changing agent schemas or output keys, update every consumer in `pipeline/run.py` in the same change. A schema/output-key mismatch is considered a breaking change.

## GitHub Actions behavior

The production workflow should remain scheduled for Tuesday and Friday and keep `workflow_dispatch` for manual testing.

Generated editorial artifacts may be committed by `github-actions[bot]` under:

- `scripts/`,
- `multimedia/`,
- `videos/`.

Do not reintroduce a workflow that runs the expensive script-generation pipeline on every daily news-file push unless explicitly requested. Daily news collection and twice-weekly production are separate concerns.

## Future video rendering

`videos/` is intentionally reserved for a later rendering stage. When implementing final video generation, prefer consuming the existing approved `script.txt` plus `multimedia/*/plan.json` contract rather than coupling rendering back into editorial selection.

The ideal future renderer should be replaceable without changing the selection, judging or script-generation stages.
