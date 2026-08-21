# AI News Daily — Agentic Video Kit

A daily AI-news pipeline built with **Google ADK + OpenAI + GitHub Actions**.

## What happens

1. A file lands in `news/YYYY-MM-DD.txt`.
2. GitHub Actions starts automatically.
3. Google ADK orchestrates an OpenAI-backed writer that creates a 60-90 second Spanish script for a young audience.
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

- `OPENAI_API_KEY` — OpenAI API key used by the ADK agents through LiteLLM.

Optional:

- `PEXELS_API_KEY` — improves stock-photo coverage. Without it, Wikimedia Commons is used automatically.

## Model

The cost-conscious default is:

```text
gpt-5.4-nano
```

Override it with the `OPENAI_MODEL` environment variable if you want a stronger model, for example `gpt-5.4-mini`.

Google ADK remains the orchestration layer. OpenAI is connected through ADK's `LiteLlm` model wrapper.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
export OPENAI_API_KEY="..."
python -m pipeline.run --news latest --out outputs
```

To select another OpenAI model:

```bash
export OPENAI_MODEL="gpt-5.4-mini"
```

To optionally use Pexels:

```bash
export PEXELS_API_KEY="..."
```

## GitHub Actions

The workflow runs when:

- a `news/*.txt` file changes,
- the agent/pipeline code changes,
- the workflow itself changes,
- or it is started manually with `workflow_dispatch`.

This broader trigger also makes the first deployment self-testing: adding or updating the workflow launches a build against the latest existing news file.

## Design notes

The generated media is treated as a **video production kit**, not as a finished narrated video. The action creates a silent visual preview and preserves source/creator/license metadata in `media_manifest.json` so each downloaded asset remains traceable.
