# AI News Daily — Agentic Video Kit

A daily AI-news pipeline built with **Google ADK + GitHub Actions**.

## What happens

1. A file lands in `news/YYYY-MM-DD.txt`.
2. GitHub Actions starts automatically.
3. A Google ADK writer creates a 60-90 second Spanish script for a young audience.
4. A critic scores factuality, clarity, relevance, pacing, and tone.
5. A `LoopAgent` repeats critic → quality gate → refiner until the script passes the threshold or reaches the safety iteration cap.
6. A storyboard agent creates exactly one visual search instruction every **4 seconds**.
7. The pipeline downloads one 1280×720 visual for every shot.
   - Pexels is preferred if `PEXELS_API_KEY` exists.
   - Wikimedia Commons is the zero-key fallback.
   - A local fallback title card is generated if both providers fail.
8. FFmpeg builds a silent visual preview (`preview.mp4`).
9. GitHub Actions uploads the complete daily kit as an artifact for 30 days.

## Daily artifact

```text
outputs/YYYY-MM-DD/
├── script.txt
├── review.json
├── storyboard.json
├── media_manifest.json
├── preview.mp4
└── media/
    ├── shot_001.jpg
    ├── shot_002.jpg
    └── ...
```

Every shot is exactly 4 seconds long in the storyboard and preview.

## Required GitHub secret

Create this repository secret under **Settings → Secrets and variables → Actions**:

- `GEMINI_API_KEY` — Gemini API key from Google AI Studio.

Optional:

- `PEXELS_API_KEY` — improves stock-photo coverage. Without it, Wikimedia Commons is used automatically.

ADK also accepts `GOOGLE_API_KEY` locally, but the included workflow expects `GEMINI_API_KEY`.

## Model

The workflow currently defaults to `gemini-3.7-flash`. Override it with the `GEMINI_MODEL` environment variable if needed.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
export GEMINI_API_KEY="..."
python -m pipeline.run --news latest --out outputs
```

To optionally use Pexels:

```bash
export PEXELS_API_KEY="..."
```

## Design notes

The generated media is treated as a **video production kit**, not as a finished narrated video. The action creates a silent visual preview and preserves source/creator/license metadata in `media_manifest.json` so each downloaded asset remains traceable.
