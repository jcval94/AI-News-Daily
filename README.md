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
3. Cross-episode deduplication uses only stories from previously **approved** episodes. Failed or rejected attempts do not burn a story.
4. `youth_script_writer` creates a Spanish narration between **7 and 12 minutes**, choosing the target length according to the number and depth of selected stories.
5. A Google ADK `LoopAgent` evaluates/refines the script with three judges:
   - factual/editorial critic,
   - **SEO Master**,
   - **YouTube Attention Master**.
6. The script must pass all judge thresholds **and** a deterministic runtime duration gate of 420–720 seconds before multimedia is allowed.
7. **Multimedia Editor Master** selects only the timeline slots that genuinely need external media. Every omitted slot defaults to `presenter`.
8. Only the selected `media` slots download an asset. Pexels is preferred when `PEXELS_API_KEY` exists; Wikimedia Commons is the zero-key fallback.

### Adaptive duration guide

At the default estimate of 2.5 spoken words/second:

- 1–2 substantive stories: aim near **7–8 min**.
- 3–4 substantive stories: aim near **8–9.5 min**.
- 5–6 substantive stories: aim near **9.5–10.5 min**.
- 7–8 substantive stories: aim near **10.5–12 min**.

The hard runtime limit remains **7–12 minutes**; depth should come from useful explanation and context, never filler.

## Run isolation and promotion

Every GitHub Actions execution writes first to an isolated workspace:

```text
.pipeline-runs/<episode-date>/<github-run-id>/
├── scripts/<episode-date>/
└── multimedia/<episode-date>/
```

That isolated run always gets its own `run_report.json` when reporting can execute. A run is copied into the canonical repository folders **only when the script is approved**. Rejected or failed attempts cannot overwrite or mix with the last good episode.

Canonical approved outputs are:

```text
scripts/YYYY-MM-DD/
├── script.txt
├── selected_news.json
├── reviews.json
└── run_report.json

multimedia/YYYY-MM-DD/
├── plan.json
├── manifest.json
└── assets/

videos/                     # reserved for future final rendering
```

Failed/non-publishable isolated runs remain available as GitHub Actions artifacts for debugging and are not promoted to canonical folders.

## Visual timing

The edit timeline remains deterministic:

- **00:00–00:15:** one slot every **3 seconds**.
- **After 00:15:** one slot every **4 seconds**.

The visual timeline is derived from the full spoken-duration estimate without the old 100-second truncation.

Only slots selected as `media` download an external asset. The maximum is controlled by `MAX_MEDIA_DOWNLOADS` (default `12`). Set `DOWNLOAD_MULTIMEDIA=false` to generate the script and edit plan without downloading assets.

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
TARGET_MIN_SECONDS=420
TARGET_MAX_SECONDS=720
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
