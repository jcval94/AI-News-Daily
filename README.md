# AI News Daily — Production Agentic Video Kit

A twice-weekly AI production pipeline for reflective Spanish-language video essays about AI, cognition, education, work, ethics, reasoning, and human consequences.

The product is **not a news recap**. Recent news is evidence for an essay; it is not the organizing structure.

## Architecture principle

**LLMs propose, plan, write, judge, refine, and suggest visuals; deterministic code controls the workflow.**

Google ADK provides the agent runtime. Deterministic Python and GitHub Actions own source-coverage checks, validation, retries, refinement routing, quality gates, state, side effects, promotion, artifacts, and deployment.

The current production entrypoint is `pipeline.run_hardened`, while the core editorial orchestration remains in `pipeline/run.py`.

Editorial identity is versioned separately from prompts:

```text
editorial/
├── voice_profile.md
└── discourse_profile.md
```

This lets prompts and models evolve without silently redefining the channel's identity.

## Mental model

```text
GitHub Actions trigger
        ↓
source coverage preflight
        ↓
news ingestion + approved memory
        ↓
Selector
        ↓
Editorial Director + Claim Ledger
        ↓
novelty gate
        ↓
Writer
        ↓
4 independent judges
        ↓
deterministic quality gate
        ↓
[factual → voice → secondary] isolated repair, only if needed
        ↓
approved script
        ↓
dense multimedia package
        ↓
report + promotion
        ↓
ai-news-run-* artifact
        ↓
Review Hub / GitHub Pages
```

The system intentionally keeps probabilistic generation separate from deterministic authority.

## Editorial principle

The preferred hierarchy is:

```text
human experience
   ↓
tension / discomfort / paradox
   ↓
verified historical mirror
   ↓
central question
   ↓
provisional thesis
   ↓
current news as evidence
   ↓
reflection / contrast / synthesis
```

> **The essay is the product. The news is evidence.**

A company announcement, model launch, paper, benchmark, or product should not normally be the hook. The viewer should first understand the human question; names and technical labels arrive only when they become useful.

## Agent inventory

`app/agent.py` contains the planning, writing, judging, and multimedia agents:

1. `news_relevance_selector` — selects at most 8 developments with editorial/human value.
2. `editorial_director` — creates the question, thesis, evidence plan, idea-led beats, and **Claim Ledger** before prose exists.
3. `essay_script_writer` — writes the reflective essay inside the factual boundary established by evidence + Claim Ledger.
4. `script_critic` — factuality, clarity, rigor, and claim discipline.
5. `seo_master` — discoverability without forcing keywords or entities into the opening.
6. `youtube_attention_master` — earned attention, progression, and pacing.
7. `voice_humanity_critic` — voice fidelity, depth, human relevance, analogies, and AI-smell.
8. `multimedia_editor_master` — proposes explanatory/contextual visuals when model-backed planning is available.

`app/refiners.py` contains deliberately isolated refiners:

9. `factual_script_refiner` — repairs factuality with access to source evidence and Claim Ledger.
10. `voice_script_refiner` — repairs voice after factuality passes, without access to the source corpus.
11. `secondary_script_refiner` — repairs SEO/attention/pacing only after factuality and voice pass.

There is **no LLM quality-gate agent** and no LLM-controlled refinement loop. Python decides which refiner, if any, runs next.

## Claim Ledger

Every planned evidence item has exactly one Claim Ledger entry created before the writer. The ledger separates:

```text
supported_facts
allowed_interpretations
hypotheses
uncertainties
prohibited_claims
source_limitations
```

The ledger is a factual boundary, not a prose outline. `news_text` remains the ultimate source of truth if a ledger entry conflicts with the underlying source material.

Runtime validation fails closed if the ledger is missing, duplicated, misaligned with evidence, points to the wrong selected-news index, or lacks supported facts.

## Why refinement is isolated

One refinement iteration never optimizes factuality and voice simultaneously.

Deterministic routing order:

```text
1. factual repair
2. voice repair
3. secondary SEO / attention / pacing polish
```

This prevents a style rewrite from silently changing factual semantics and prevents factual repair from oscillating with voice repair.

## How news should be used

Every included story needs an argumentative function before it enters the script:

- `evidence` — makes an abstract idea concrete;
- `counterexample` — complicates the initial thesis;
- `symptom` — reveals a broader transformation;
- `consequence` — shows what happens when an idea leaves the lab;
- `limit case` — tests how far a trend can go;
- `bridge` — connects a technical change with a human consequence.

If a story has no distinct function, the Director should omit it. Prefer three strong pieces of evidence to eight shallow headlines.

## Opening contract

The preferred opening is:

```text
recognizable human observation
   ↓
unease / contradiction
   ↓
verified historical mirror
   ↓
central question
   ↓
provisional thesis
```

Only after that does current news normally enter.

Avoid default openings such as:

- “Hoy salió una noticia…”
- “Esta semana X anunció…”
- a company/model/product name before the viewer understands why it matters;
- a first minute that sounds like a list of headlines.

## Voice and language

The narrator is reflective, analytically curious, humanist, fascinated by technology but skeptical of hype.

Core principles:

- roughly 40% information / 60% reflection, context, interpretation, and human impact;
- neutral Latin American Spanish with slight Mexican familiarity;
- avoid voseo and strong Rioplatense forms;
- explain the idea in ordinary language before naming technical terms;
- analogies are explanatory tools, not decoration;
- uncertainty is stated honestly;
- intellectual rigor outranks retention;
- no plastic AI language, fake urgency, or dishonest clickbait.

Useful clarity test:

> If a curious 15-year-old would have to pause the video to decode the sentence, rewrite it.

## Historical framing

Historical references are used as mirrors for the present, not as decoration. The curated source-backed library lives inside `editorial/discourse_profile.md`.

The Writer may paraphrase only facts included there. It must not invent historical quotes, people, dates, books, or anecdotes.

## Facts vs reflection

The editorial system distinguishes:

```text
FACT            directly supported by evidence
INTERPRETATION  the narrator's clearly labeled reading
HYPOTHESIS      a plausible possibility, not a reported result
UNCERTAINTY     something we genuinely do not know
```

This protects the reflective component without allowing speculation to masquerade as fact.

## Duration

The deterministic range is **7–20 minutes** (420–1200 seconds).

Duration follows the depth of the thesis, not the number of news items.

## Source coverage and windows

Before any model call, production runs `pipeline.source_coverage`.

Default production policy requires:

- at least one structured news item;
- at least **75% coverage of the expected daily window**.

If coverage is insufficient, the run stops as `no_source_news` before spending model tokens.

Scheduled production keeps the twice-weekly cadence:

- **Tuesday:** Friday–Monday window.
- **Friday:** Tuesday–Thursday window.

Missing daily files can be tolerated only while the configured coverage threshold still passes.

Daily inputs remain:

```text
news/YYYY-MM-DD.txt
```

Manual production can use `recent_window`, which considers the target day plus the preceding `NEWS_LOOKBACK_DAYS - 1` calendar days.

## Manual / on-demand generation

**Actions → Build AI News Video Kit → Run workflow**

Manual inputs:

- `target_date` — episode date; blank means today in Mexico City.
- `source_mode=recent_window` — use newest available material.
- `source_mode=scheduled_window` — reproduce Tuesday/Friday policy.
- `lookback_days` — 1–14 days for `recent_window`; default 4.
- `download_multimedia` — disable for a cheaper script-only experiment.
- `promote_approved` — `false` keeps the result only as an Actions artifact; `true` promotes an approved run to canonical outputs.

Recommended safe editorial experiment:

```text
source_mode=recent_window
download_multimedia=false
promote_approved=false
```

Scheduled Tuesday/Friday runs use `scheduled_window` and promote only approved outputs.

## Episode states

`run_state.json` is authoritative:

- `approved`
- `no_source_news`
- `no_relevant_news`
- `no_novel_essay_angle`
- `script_not_approved`
- `failure`
- `missing_openai_secret`

Only `approved` runs are publishable/promotable.

## Deterministic quality gate

Default approval requires:

- narration between **420 and 1200 seconds**;
- editorial score >= 8.7;
- factuality risk `low`;
- SEO score >= 8.5;
- Attention score >= 8.5;
- Voice/Humanity score >= 8.7;
- Voice/Humanity `ai_smell_risk == low`;
- every judge explicitly approves.

A factual script can still fail because it has weak voice, poor attention, excessive AI-smell, or insufficient duration.

## Dense multimedia policy

Multimedia is generated **only after the script passes the editorial gate**.

Current production defaults:

- up to **54 assets**;
- 0–20 s: dense, video-first cold open at roughly **3.5 s** per slot;
- after 20 s: one candidate about every **10 s** across the spoken timeline;
- media gate: **>=45 assets** when the production budget is at least 45;
- cold-open gate: **>=5 assets in the first 20 s**;
- provider/model quota failures may fall back to deterministic/local media generation;
- a media failure can block promotion but can never turn a rejected script into an approved one.

The Review Hub reuses canonical production multimedia when it exists and satisfies the contract. Legacy/sparse artifacts may be rebuilt for review only; that reconstructed media is not treated as proof of what production generated.

## Retries and FinOps

Agent calls retry only likely transient failures with bounded exponential backoff. Permanent quota failures are classified as non-retryable so the system does not burn attempts unnecessarily.

When provider usage is emitted before a failed stream, partial usage is preserved in `execution_trace.json` when available.

Media retrieval has its own bounded HTTP retry policy.

## Isolation and promotion

Every attempt is built under:

```text
.pipeline-runs/<episode-date>/<github-run-id>/
```

Approved canonical outputs become:

```text
scripts/YYYY-MM-DD/
├── run_state.json
├── execution_trace.json
├── run_report.json
├── selected_news.json
├── episode_plan.json
├── script_sections.json
├── script.txt
└── reviews.json

multimedia/YYYY-MM-DD/
├── plan.json
├── manifest.json
├── credits.json
└── assets/
```

Failed/non-publishable attempts remain isolated and never overwrite canonical episodes.

## Observability

`execution_trace.json` records model attempts, logical steps, iteration, retry, timing, error class, usage when exposed, and refinement routing.

`run_report.json` provides a durable summary with configuration, hashes, gate results, quality dimensions, retries, token usage, and multimedia/provider metrics.

`pipeline/architecture_manifest.py` is the living architecture source used by the E2E teaching view.

`pipeline/run_journey.py` reconstructs the **observed run path** from persisted artifacts so GitHub Pages can distinguish:

- executed;
- inferred;
- not required;
- not reached;
- terminal;
- not observed.

It also avoids treating Review Hub reconstruction as production provenance.

## Review Hub and GitHub Pages

Production is the source of truth for Pages:

```text
Build AI News Video Kit
        ↓
ai-news-run-* artifact
        ↓
Editorial Review Hub
        ↓
GitHub Pages
```

Editorial Regression is a separate QA lane; it is not the canonical content source for Pages.

The Review Hub includes script, evidence, multimedia, costs, technical diagnostics, Living Architecture, and the observed run journey.

## Configuration

Required secret:

```text
OPENAI_API_KEY
```

Optional secrets:

```text
PEXELS_API_KEY
YOUTUBE_API_KEY
```

`YOUTUBE_API_KEY` enables post-approval real-footage discovery. The pipeline stores YouTube links and metadata only in the isolated run as `.pipeline-runs/<date>/<run-id>/multimedia/<date>/footage_candidates.json`. The GitHub Actions run artifact is retained for 30 days and this YouTube API metadata is deliberately excluded from canonical `multimedia/` history. The pipeline does **not** download YouTube audiovisual content and never auto-declares fair use.

Useful repository variables:

```text
OPENAI_MODEL=gpt-5.4-nano
SCRIPT_QUALITY_THRESHOLD=8.7
JUDGE_THRESHOLD=8.5
VOICE_THRESHOLD=8.7
MAX_REFINEMENT_ITERATIONS=5
MAX_MEDIA_DOWNLOADS=54
MIN_SOURCE_COVERAGE_RATIO=0.75
MEDIA_MIN_RELEVANCE_SCORE=0.22
DOWNLOAD_MULTIMEDIA=true
SELECTION_HISTORY_DAYS=30
ESSAY_HISTORY_DAYS=120
MAX_RECENT_ESSAYS=12
TARGET_MIN_SECONDS=420
TARGET_MAX_SECONDS=1200
WORDS_PER_SECOND=2.5
AGENT_MAX_ATTEMPTS=3
AGENT_RETRY_BASE_SECONDS=2.0
MEDIA_HTTP_MAX_ATTEMPTS=3
MEDIA_HTTP_RETRY_BASE_SECONDS=1.0
NEWS_SOURCE_MODE=scheduled_window
NEWS_LOOKBACK_DAYS=4
```

## Validation

Deterministic CI runs without API secrets:

```bash
python -m compileall app pipeline
python -c "import app.agent, pipeline.run; print('runtime imports ok')"
python -m unittest discover -s tests -v
python -m pipeline.editorial_calibration --cases evals/editorial/cases.json --output /tmp/editorial-calibration.json
```

For production changes, also validate the model-backed **Editorial Regression** and production-backed **Editorial Review Hub** workflows.

A real model/media E2E is available through **Actions → Build AI News Video Kit → Run workflow**. Scheduled production runs Tuesday and Friday at 09:00 America/Mexico_City.

## Roadmap

The detailed next steps live in [`ROADMAP.md`](ROADMAP.md). The current architecture intentionally favors evidence quality, bounded agent behavior, observability, and deterministic production control over adding more frameworks or agents for appearance alone.
