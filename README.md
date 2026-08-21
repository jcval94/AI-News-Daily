# AI News Daily — Agentic Video Kit

AI-news video pipeline built with **Google ADK + OpenAI + GitHub Actions**.

## Production cadence

Daily files remain under `news/YYYY-MM-DD.txt`, but script/video-kit production runs only twice per week:

- **Tuesday:** use whatever is available from **Friday, Saturday, Sunday and Monday**.
- **Friday:** use whatever is available from **Tuesday, Wednesday and Thursday**.

Missing daily files are non-fatal. The pipeline logs the missing dates and continues with the files that exist. If the whole editorial window is empty, the workflow exits successfully without fabricating a script.

The scheduled workflow runs at **09:00 America/Mexico_City** on Tuesdays and Fridays. A manual `workflow_dispatch` can reproduce any Tuesday/Friday by supplying `target_date=YYYY-MM-DD`.

## Editorial pipeline

1. Combine the available daily news files for the target window.
2. `news_relevance_selector` removes semantic duplicates and selects only the strongest stories, with a hard maximum of **8**.
3. The selector also compares against recent `scripts/*/selected_news.json` history to avoid repeating a story in later episodes unless there is a materially new development.
4. `youth_script_writer` creates the Spanish narration.
5. A Google ADK `LoopAgent` evaluates/refines the script with three judges:
   - factual/editorial critic,
   - **SEO Master**,
   - **YouTube Attention Master**.
6. The loop exits when all three judges approve, or stops at the configured iteration cap. If unanimous approval was not reached, the script/reviews are saved and multimedia is skipped.
7. Only an unanimously approved script proceeds to multimedia planning. The script is written to disk **before** any multimedia download starts.
8. **Multimedia Editor Master** decides slot by slot whether the final edit should show:
   - `presenter`: a person on camera, so no external stock asset is downloaded;
   - `media`: an external visual materially helps, so one asset is downloaded.
9. Pexels is preferred when `PEXELS_API_KEY` exists; Wikimedia Commons is the zero-key fallback.

## Visual timing

The edit timeline is deterministic:

- **00:00–00:15:** one slot every **3 seconds** (5 visible changes).
- **After 00:15:** one slot every **4 seconds**.

Only slots selected as `media` download an external asset. The maximum is controlled by `MAX_MEDIA_DOWNLOADS` (default `12`). Set `DOWNLOAD_MULTIMEDIA=false` to generate the script and edit plan without downloading assets.

## Repository folders

```text
news/                       # daily source digests
scripts/YYYY-MM-DD/
├── script.txt
├── selected_news.json
└── reviews.json

multimedia/YYYY-MM-DD/
├── plan.json
├── manifest.json
└── assets/                 # only media slots selected by the editor

videos/                     # reserved for future final video generation
```

The scheduled GitHub Action commits generated `scripts/` and `multimedia/` outputs back to the branch and also uploads them as a workflow artifact.

## Required GitHub secret

Create this repository secret under **Settings → Secrets and variables → Actions**:

- `OPENAI_API_KEY` — used by Google ADK agents through LiteLLM.

Optional:

- `PEXELS_API_KEY` — improves stock-photo coverage.

## Model and parameters

The cost-conscious default model is:

```text
gpt-5.4-nano
```

Useful repository variables (`Settings → Secrets and variables → Actions → Variables`):

```text
OPENAI_MODEL=gpt-5.4-nano
SCRIPT_QUALITY_THRESHOLD=8.7
JUDGE_THRESHOLD=8.5
MAX_REFINEMENT_ITERATIONS=5
MAX_MEDIA_DOWNLOADS=12
DOWNLOAD_MULTIMEDIA=true
SELECTION_HISTORY_DAYS=30
```

## Run locally

Example for a Friday production window:

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
export OPENAI_API_KEY="..."
python -m pipeline.run --target-date 2026-08-21
```

Example for a Tuesday production window:

```bash
python -m pipeline.run --target-date 2026-08-25
```

To create the script/edit plan without external downloads:

```bash
python -m pipeline.run --target-date 2026-08-25 --no-download-multimedia
```

## Design note

The current output is a **production kit**, not a finished narrated video. `videos/` is intentionally reserved for the later rendering stage. Downloaded asset source/creator/license metadata is kept in `multimedia/YYYY-MM-DD/manifest.json` for traceability.
