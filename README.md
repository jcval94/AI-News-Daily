# AI News Daily — Agentic Video Kit

AI-news video pipeline built with **Google ADK + OpenAI + GitHub Actions**.

## Production cadence

The daily `news/YYYY-MM-DD.txt` files remain the source material, but video production runs only twice per week:

- **Tuesday:** use whatever is available from Friday, Saturday, Sunday and Monday.
- **Friday:** use whatever is available from Tuesday, Wednesday and Thursday.

Missing daily files are skipped. If the entire expected window is unavailable, the workflow finishes cleanly with a diagnostic `status.json` instead of failing.

GitHub Actions is scheduled for **09:00 America/Mexico_City** on Tuesdays and Fridays. Manual execution remains available through `workflow_dispatch`.

## Editorial pipeline

1. Combine the available daily news files for the current window.
2. `news_relevance_selector` removes semantic duplicates and selects only the strongest stories, with a hard maximum of **8**.
3. `youth_script_writer` creates a 60-90 second Spanish script for a young audience.
4. A Google ADK `LoopAgent` evaluates/refines the script with three judges:
   - factual/editorial critic,
   - **SEO Master**,
   - **YouTube Attention Master**.
5. The loop stops only when all three approve or the iteration limit is reached.
6. If all three do **not** approve, the script and diagnostics are saved and multimedia download is intentionally skipped.
7. Only after approval, **Multimedia Editor Master** decides slot by slot whether the video should show:
   - `presenter`: a person on camera, with no external multimedia download;
   - `media`: an external visual is useful and should be downloaded.
8. External assets use Pexels when configured, then Wikimedia Commons as zero-key fallback.
9. FFmpeg builds a silent visual preview and GitHub Actions uploads the kit as an artifact.

## Visual timing

The timeline is deterministic before the Multimedia Editor makes its decisions:

- **00:00-00:15:** one slot every **3 seconds**.
- **After 00:15:** one slot every **4 seconds** by default.

Only slots classified as `media` download an external asset. Presenter slots use a local placeholder in the preview, so they do not consume/download stock media.

The maximum number of external assets is parameterized with:

```text
MAX_MEDIA_DOWNLOADS=12
```

It can also be overridden when manually launching the GitHub Action.

## Artifact

```text
outputs/YYYY-MM-DD/
├── script.txt
├── selection.json
├── review.json
├── seo_review.json
├── attention_review.json
├── editor_plan.json          # only after script approval
├── media_manifest.json       # only after script approval
├── preview.mp4               # only after script approval
├── status.json
├── media/                    # downloaded media slots only
└── preview_frames/           # local presenter placeholders
```

## Required GitHub secret

Create this repository secret under **Settings → Secrets and variables → Actions**:

- `OPENAI_API_KEY` — used by Google ADK agents through `LiteLlm`.

Optional:

- `PEXELS_API_KEY` — improves stock-photo coverage. Without it, Wikimedia Commons is used automatically.

## Model

The cost-conscious default is:

```text
gpt-5.4-nano
```

Override it with `OPENAI_MODEL` if needed.

Google ADK remains the orchestration layer; OpenAI is connected through ADK's `LiteLlm` wrapper.

## Run locally

Scheduled-window behavior using the local date in Mexico City:

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
export OPENAI_API_KEY="..."
python -m pipeline.run --news scheduled --out outputs
```

Reproduce a specific Tuesday/Friday window:

```bash
python -m pipeline.run --news scheduled --run-date 2026-08-21 --out outputs
```

Tune multimedia usage:

```bash
export MAX_MEDIA_DOWNLOADS=8
export MEDIA_SLOT_SECONDS=4
```

## Design notes

The output is a **video production kit**, not a finished narrated video. Downloaded asset source/creator/license information is kept in `media_manifest.json` for traceability.
