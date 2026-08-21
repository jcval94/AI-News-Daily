# AI News Daily — Production Agentic Video Kit

A twice-weekly AI production pipeline designed as a small, understandable agentic system.

The product is **not a rapid news recap**. It uses recent AI news as evidence for reflective audiovisual essays about technology, cognition, education, work, ethics, reasoning, and human consequences.

## Architecture principle

**LLMs propose, plan, write, and judge; deterministic code controls the workflow.**

Google ADK provides the agent runtime. `pipeline/run.py` owns retries, validation, refinement iterations, duration gates, state, outputs, and side effects.

Editorial identity is versioned separately from prompts:

```text
editorial/
├── voice_profile.md
└── discourse_profile.md
```

This lets prompts/models evolve without redefining what the channel is supposed to sound like.

## Agent roles

1. `news_relevance_selector` — selects at most 8 unique stories with real editorial/human value.
2. `editorial_director` — creates the episode's central question, thesis, target duration, story roles, narrative beats, analogy goals, skepticism, human stakes, and historical framing.
3. `essay_script_writer` — writes the first 7–20 minute reflective Spanish narration from evidence + plan + editorial profiles.
4. `script_critic` — factuality and intellectual-rigor judge.
5. `seo_master` — discoverability judge without clickbait or keyword stuffing.
6. `youtube_attention_master` — earned-attention and retention judge.
7. `voice_humanity_critic` — rejects scripts that are correct but generic, shallow, plastic, inaccessible, or recognizably AI-written.
8. `script_refiner` — revises using all judge feedback while preserving facts, plan, and voice.
9. `multimedia_editor_master` — chooses only slots where external visuals add explanatory/contextual value.

There is **no LLM quality-gate agent**. Python evaluates the final gate deterministically.

## Editorial flow

```text
raw news
   ↓
selector
   ↓
selected_news.json
   ↓
Editorial Director
   ↓
episode_plan.json
   ├── current-news opening
   ├── verified historical parallel
   ├── central question
   ├── thesis
   ├── target duration
   ├── story roles
   ├── beats
   ├── analogy goals
   ├── skepticism
   └── human stakes
   ↓
Writer
   ↓
[Editorial + SEO + Attention + Voice judges]
   ↓
deterministic gate
   ↙        ↘
refine     approved
   ↖          ↓
    └──── multimedia
```

The episode plan may omit selected stories. Selection means “worth considering”; it does not mean every story must appear.

## Voice and discourse

The narrator is a reflective, experienced AI communicator: analytically curious, provocative, humanist, fascinated by the technology but skeptical of hype.

Core principles:

- roughly 40% information / 60% reflection, context, interpretation, and human impact;
- **neutral Latin American Spanish with slight Mexican familiarity**, avoiding strong regionalisms and voseo;
- the target audience is curious but not necessarily technical;
- explain the idea in ordinary language before naming technical terms;
- avoid unnecessary jargon and rare vocabulary when a simpler word exists;
- analogies are central to explanation, not decoration;
- historical parallels are used to reveal patterns, not to sound cultured;
- uncertainty is stated honestly;
- corporate hype can be challenged directly;
- intellectual rigor outranks retention;
- progressive revelation is preferred to headline dumping;
- no plastic AI language, corporate neutrality, fake urgency, or dishonest clickbait.

The full source of truth lives in `editorial/voice_profile.md` and `editorial/discourse_profile.md`.

### Historical framing

The preferred opening pattern is:

```text
current news
   ↓
surprising verified historical parallel
   ↓
deeper question
```

The curated historical references live directly in `editorial/discourse_profile.md` and include source links. The Writer may use those references as factual historical context, but must not invent historical quotes, people, dates, books, or anecdotes.

The profile currently includes examples around writing and memory, electrification, human “computers”, automated teaching, VisiCalc, and ATMs. One strong historical reference should normally appear near the opening when the connection is honest; one to three additional parallels may appear later if they genuinely clarify a different idea.

### Technical accessibility

A useful editorial test is:

> If a curious 15-year-old would have to pause the video to decode the sentence, rewrite it.

Terms such as `runtime`, `orchestration`, `inference`, `embedding`, `latency`, `benchmark` or `RAG` are not forbidden, but they should appear only after the underlying idea has been explained in common language.

## Duration

The deterministic range is **7–20 minutes** (420–1200 seconds).

The Editorial Director chooses the intended duration from available substance:

- 1–2 substantive stories: ~7–10 min
- 3–4: ~10–14 min
- 5–6: ~14–17 min
- 7–8: ~17–20 min

These are editorial guidelines, not quotas. Never pad.

## Source windows

Scheduled production preserves the original editorial cadence:

- **Tuesday:** use available Friday, Saturday, Sunday, Monday files.
- **Friday:** use available Tuesday, Wednesday, Thursday files.
- Missing daily files are non-fatal.
- If no source exists: `no_source_news`.
- If sources exist but nothing is worth publishing: `no_relevant_news`.

Daily source inputs remain `news/YYYY-MM-DD.txt`.

Manual production can instead use `recent_window`. In that mode, the episode may run on **any date** and considers the target day plus the preceding `NEWS_LOOKBACK_DAYS - 1` calendar days. Missing files are still ignored safely.

For example, a manual run for `2026-08-21` with a 4-day recent window considers:

```text
2026-08-18
2026-08-19
2026-08-20  ← available
2026-08-21  ← available
```

This is useful for an early episode or an editorial experiment without changing the scheduled Tuesday/Friday contract.

## Manual / on-demand generation

The content workflow is deliberately runnable by hand:

**Actions → Build AI News Video Kit → Run workflow**

Manual inputs:

- `target_date` — episode date; blank means today in Mexico City.
- `source_mode=recent_window` — useful when you want the newest available material now.
- `source_mode=scheduled_window` — reproduces the production Tuesday/Friday source policy.
- `lookback_days` — 1–14 calendar days for `recent_window`; default 4.
- `download_multimedia` — turn off for a cheaper script/voice-only experiment.
- `promote_approved` — when `false`, the run stays only as an Actions artifact even if approved; when `true`, an approved result becomes canonical.

Recommended modes:

```text
Editorial experiment
source_mode=recent_window
download_multimedia=false
promote_approved=false

Early publishable episode
source_mode=recent_window
download_multimedia=true
promote_approved=true
```

Scheduled Tuesday/Friday runs always use `scheduled_window` and promote only approved outputs.

## Real editorial evaluation

For an editorial test, review these artifacts first:

```text
selected_news.json
episode_plan.json
script.txt
run_report.json
```

The most important questions are not only whether the script passes. Check whether:

- the current news appears early;
- the historical parallel is real, surprising, and actually useful;
- the script is understandable without an AI/ML background;
- technical terms are translated into human ideas;
- `episode_plan.json` contains a compelling central question and thesis;
- the narration sounds reflective, human, skeptical of hype, and worth listening to.

## Episode states

`run_state.json` is authoritative:

- `approved`
- `no_source_news`
- `no_relevant_news`
- `script_not_approved`
- `failure`
- `missing_openai_secret`

Only `approved` runs may replace canonical outputs, and manual runs additionally require `promote_approved=true` before promotion.

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

The Voice & Humanity judge separately tracks:

- voice fidelity;
- intellectual depth;
- human relevance;
- analogy quality;
- AI-smell risk.

A factual script can still fail because it has no voice or because it is inaccessible to the intended audience.

## Facts vs reflection

The editorial critic explicitly distinguishes:

```text
FACT            directly supported by current-news evidence or curated history
INTERPRETATION  the narrator's clearly labeled reading
HYPOTHESIS      a plausible possibility, not a reported result
UNCERTAINTY     something we genuinely do not know
```

This prevents the 60% reflective component from being incorrectly treated as factual error while still rejecting speculation disguised as evidence.

## Retries

Agent calls retry only likely transient failures (rate limits, timeouts, connection/service errors) with bounded exponential backoff. Invalid inputs/configuration errors are not retried.

Media retries are independent. If Pexels/Wikimedia fail, the pipeline can fall back to a local generated card.

## Isolation and outputs

Each Actions attempt is built first under:

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
├── script.txt
└── reviews.json

multimedia/YYYY-MM-DD/
├── plan.json
├── manifest.json
└── assets/

videos/  # future final rendering
```

Failed/non-publishable attempts remain as Actions artifacts and never overwrite canonical episodes. Manual experiments with `promote_approved=false` behave the same way even when the script is approved.

## Observability

`execution_trace.json` records each model attempt, logical step, iteration, retry, timing, error class, and token usage when ADK exposes it.

`run_report.json` v4 includes:

- state/reason;
- source hashes and effective source-window configuration;
- effective model/quality configuration;
- selection and duplicates;
- central question, thesis, hook, target duration, and story count;
- deterministic gate;
- Editorial / SEO / Attention / Voice scores;
- Voice Fidelity / Intellectual Depth / Human Relevance / Analogy Quality / AI Smell;
- retries and token usage;
- multimedia/provider metrics;
- hashes for outputs and editorial profiles.

## Multimedia timing

- First 15 seconds: deterministic 3-second slots.
- After 15 seconds: 4-second slots.
- Omitted editor slots = presenter/on-camera.
- Returned slots = external media.
- `MAX_MEDIA_DOWNLOADS` is a hard code-enforced cap.

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
VOICE_THRESHOLD=8.7
MAX_REFINEMENT_ITERATIONS=5
MAX_MEDIA_DOWNLOADS=12
DOWNLOAD_MULTIMEDIA=true
SELECTION_HISTORY_DAYS=30
TARGET_MIN_SECONDS=420
TARGET_MAX_SECONDS=1200
WORDS_PER_SECOND=2.5
AGENT_MAX_ATTEMPTS=3
AGENT_RETRY_BASE_SECONDS=2.0
MEDIA_HTTP_MAX_ATTEMPTS=3
NEWS_SOURCE_MODE=scheduled_window
NEWS_LOOKBACK_DAYS=4
```

The workflow overrides `NEWS_SOURCE_MODE` and `NEWS_LOOKBACK_DAYS` for manual runs; repository defaults remain production-safe.

## Validation

Deterministic CI runs without API secrets:

```bash
python -m compileall app pipeline
python -c "import app.agent, pipeline.run; print('runtime imports ok')"
python -m unittest discover -s tests -v
```

A real model/media E2E is available through **Actions → Build AI News Video Kit → Run workflow**. Production remains scheduled Tuesday/Friday at 09:00 America/Mexico_City.

## Roadmap

The detailed next steps live in [`ROADMAP.md`](ROADMAP.md). The next milestone is deliberately **not** video rendering. First, validate the editorial system with real news, then calibrate voice against reference scripts, then freeze a small regression set before adding TTS/rendering and publication automation.
