# AI News Daily — Production Agentic Video Kit

A twice-weekly AI production pipeline designed as a small, understandable agentic system.

The product is **not a news recap**. It produces reflective video essays about AI, cognition, education, work, ethics, reasoning, and human consequences. Recent news is evidence for the essay, not the organizing structure.

## Architecture principle

**LLMs propose, plan, write, and judge; deterministic code controls the workflow.**

Google ADK provides the agent runtime. `pipeline/run.py` owns retries, validation, refinement iterations, duration gates, state, outputs, and side effects.

Editorial identity is versioned separately from prompts:

```text
editorial/
├── voice_profile.md
└── discourse_profile.md
```

This lets prompts and models evolve without redefining the channel's identity.

## Editorial principle

The core hierarchy is now:

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

The key rule is:

> **The essay is the product. The news is evidence.**

A company announcement, model launch, paper, benchmark, or product should not normally be the hook. The viewer should first understand the human question; names and technical labels arrive only when they become useful.

## Agent roles

1. `news_relevance_selector` — selects at most 8 developments that could serve as evidence for a meaningful essay.
2. `editorial_director` — starts from a human tension, formulates the central question and provisional thesis, then chooses only the current stories that help investigate it.
3. `essay_script_writer` — writes the 7–20 minute reflective Spanish video essay.
4. `script_critic` — factuality, clarity, rigor, and FACT/INTERPRETATION/HYPOTHESIS/UNCERTAINTY judge.
5. `seo_master` — discoverability judge without forcing keywords or entities into the opening.
6. `youtube_attention_master` — earned-attention judge for a video essay, not a news roundup.
7. `voice_humanity_critic` — rejects scripts that are correct but generic, news-like, inaccessible, plastic, or recognizably AI-written.
8. `script_refiner` — revises using all judge feedback while preserving essay-first structure.
9. `multimedia_editor_master` — chooses only slots where visuals add explanatory, historical, or contextual value.

There is **no LLM quality-gate agent**. Python evaluates the final gate deterministically.

## Editorial flow

```text
raw news
   ↓
Selector: possible evidence
   ↓
selected_news.json
   ↓
Editorial Director
   ├── human observation / hook
   ├── historical mirror
   ├── central question
   ├── provisional thesis
   ├── target duration
   └── 2–4 preferred evidence stories
   ↓
episode_plan.json
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

Selection means “worth considering as evidence”; it does not mean every story appears.

## How news should be used

Every included story needs an argumentative function before it enters the script:

- `evidence` — makes an abstract idea concrete;
- `counterexample` — complicates the initial thesis;
- `symptom` — reveals a broader transformation;
- `consequence` — shows what happens when an idea leaves the lab;
- `limit case` — tests how far a trend can go;
- `bridge` — connects a technical change with a human consequence.

If a story has no distinct function, the Director should omit it.

Prefer three strong pieces of evidence to eight shallow headlines.

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

Good energy:

> “No sé si te pasa algo parecido, pero últimamente cada anuncio de inteligencia artificial me deja una sensación rara…”

This is an example of tone, not a line to copy mechanically.

Avoid default openings such as:

- “Hoy salió una noticia…”
- “Esta semana X anunció…”
- a company/model/product name before the viewer understands why it matters;
- a first minute that sounds like a list of headlines.

## Voice and language

The narrator is a reflective, experienced AI communicator: analytically curious, provocative, humanist, fascinated by technology but skeptical of hype.

Core principles:

- roughly 40% information / 60% reflection, context, interpretation, and human impact;
- **neutral Latin American Spanish with slight Mexican familiarity**;
- avoid voseo and strong Rioplatense forms (`vos`, `mirá`, `pará`, `acá`, `pensá`, `suscribite`);
- target audience is curious but not necessarily technical;
- explain the idea in ordinary language before naming technical terms;
- avoid unnecessary jargon and rare vocabulary when a simpler word exists;
- analogies are central to explanation, not decoration;
- uncertainty is stated honestly;
- corporate hype can be challenged directly;
- intellectual rigor outranks retention;
- no plastic AI language, fake urgency, or dishonest clickbait.

Useful clarity test:

> If a curious 15-year-old would have to pause the video to decode the sentence, rewrite it.

Terms such as `runtime`, `orchestration`, `inference`, `embedding`, `latency`, `benchmark` or `RAG` are not forbidden, but the underlying idea must be explained first.

## Historical framing

Historical references are used as mirrors for the present, not as decoration. The curated source-backed library lives inside `editorial/discourse_profile.md` and currently includes:

- Platón, writing, and memory;
- adoption and organizational impact of electricity;
- human “computers” before electronic computers;
- automated teaching in the 1950s–60s;
- VisiCalc and spreadsheet automation;
- ATMs and changing bank work.

The Writer may paraphrase only the facts included there. It must not invent historical quotes, people, dates, books, or anecdotes.

One strong historical mirror near the opening is useful when the connection is honest; one or two later parallels may appear if they illuminate different dimensions.

## Facts vs reflection

The editorial critic explicitly distinguishes:

```text
FACT            directly supported by current-news evidence or curated history
INTERPRETATION  the narrator's clearly labeled reading
HYPOTHESIS      a plausible possibility, not a reported result
UNCERTAINTY     something we genuinely do not know
```

This protects the reflective component without allowing speculation to masquerade as fact.

## Duration

The deterministic range is **7–20 minutes** (420–1200 seconds).

Duration follows the depth of the thesis, not the number of news items. A strong essay with 2–4 cases is preferable to a 20-minute roundup padded with headlines.

## Source windows

Scheduled production keeps the twice-weekly cadence:

- **Tuesday:** available Friday, Saturday, Sunday, Monday files.
- **Friday:** available Tuesday, Wednesday, Thursday files.
- missing daily files are non-fatal;
- no source → `no_source_news`;
- sources but nothing useful → `no_relevant_news`.

Daily source inputs remain:

```text
news/YYYY-MM-DD.txt
```

Manual production can use `recent_window`, which allows generation on any date using the target day plus the preceding `NEWS_LOOKBACK_DAYS - 1` calendar days.

## Manual / on-demand generation

**Actions → Build AI News Video Kit → Run workflow**

Manual inputs:

- `target_date` — episode date; blank means today in Mexico City.
- `source_mode=recent_window` — use newest available material.
- `source_mode=scheduled_window` — reproduce Tuesday/Friday policy.
- `lookback_days` — 1–14 days for `recent_window`; default 4.
- `download_multimedia` — disable for a cheaper script-only experiment.
- `promote_approved` — `false` keeps the result only as an Actions artifact; `true` promotes an approved run to canonical outputs.

Recommended editorial experiment:

```text
source_mode=recent_window
download_multimedia=false
promote_approved=false
```

Scheduled Tuesday/Friday runs always use `scheduled_window` and only promote approved outputs.

## Real editorial evaluation

Review these artifacts together:

```text
selected_news.json
episode_plan.json
script.txt
reviews.json
run_report.json
```

Ask:

- Does the opening work even if I do not know this week's news?
- Is there a real human tension before any headline appears?
- Does the historical mirror sharpen the question?
- Would the central question still be interesting next month?
- Are current stories being used as evidence rather than as chapters of a roundup?
- Are names and technical terms introduced only after their meaning is clear?
- Does the final synthesis genuinely complicate or deepen the opening thesis?
- Does this sound like a thoughtful human essay rather than a polished AI newsletter?

## Episode states

`run_state.json` is authoritative:

- `approved`
- `no_source_news`
- `no_relevant_news`
- `script_not_approved`
- `failure`
- `missing_openai_secret`

Only `approved` runs may replace canonical outputs, and manual runs additionally require `promote_approved=true`.

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

A factual script can fail because it has no voice, is too technical, or still feels like a news roundup.

## Retries

Agent calls retry only likely transient failures (rate limits, timeouts, connection/service errors) with bounded exponential backoff. Invalid inputs/configuration errors are not retried.

Media retries are independent. If Pexels/Wikimedia fail, the pipeline can fall back to a local generated card.

## Isolation and outputs

Each Actions attempt is first built under:

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
```

Failed/non-publishable attempts remain as Actions artifacts and never overwrite canonical episodes.

## Observability

`execution_trace.json` records each model attempt, logical step, iteration, retry, timing, error class, and token usage when ADK exposes it.

`run_report.json` includes:

- state/reason;
- source hashes and effective source-window configuration;
- model/quality configuration;
- selection and duplicates;
- central question, thesis, hook, target duration, and story count;
- deterministic gate;
- Editorial / SEO / Attention / Voice scores;
- Voice Fidelity / Intellectual Depth / Human Relevance / Analogy Quality / AI Smell;
- retries and token usage;
- multimedia/provider metrics;
- hashes for outputs and editorial profiles.

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

## Validation

Deterministic CI runs without API secrets:

```bash
python -m compileall app pipeline
python -c "import app.agent, pipeline.run; print('runtime imports ok')"
python -m unittest discover -s tests -v
```

A real model/media E2E is available through **Actions → Build AI News Video Kit → Run workflow**. Production remains scheduled Tuesday/Friday at 09:00 America/Mexico_City.

## Roadmap

The detailed next steps live in [`ROADMAP.md`](ROADMAP.md). Editorial quality comes first: validate the essay architecture with real news, calibrate Voice DNA against reference scripts, freeze a small editorial regression set, and only then invest in TTS/rendering and publication automation.
