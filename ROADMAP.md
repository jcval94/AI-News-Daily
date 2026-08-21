# AI News Daily — Roadmap

The roadmap is intentionally ordered to maximize learning and robustness before adding more automation.

## Milestone 1 — Validate the editorial system with real news

**Goal:** prove that the new architecture creates a genuinely better episode, not only a more complex pipeline.

Recommended first run:

```text
target_date=2026-08-21
source_mode=recent_window
lookback_days=4
download_multimedia=false
promote_approved=false
```

This should use the available `2026-08-20.txt` and `2026-08-21.txt` inputs.

Review, in order:

1. `selected_news.json` — did the selector prefer substance over corporate noise?
2. `episode_plan.json` — is there a real central question, thesis, hierarchy, analogy strategy, and human stakes?
3. `script.txt` — does it sound like a reflective human narrator rather than a summarized newsletter?
4. `reviews.json` — do judge criticisms match what a human editor notices?
5. `run_report.json` — are duration, Voice/Humanity, AI Smell, retries, token usage, and source provenance coherent?

**Exit criteria:** the plan and script are worth iterating on even if they do not pass every gate yet.

---

## Milestone 2 — Calibrate Voice DNA from reference scripts

**Goal:** replace subjective prompt tweaking with evidence-backed editorial calibration.

Inputs:

- 3–6 scripts that represent the desired voice;
- ideally 2–4 scripts written by the channel owner;
- several external references annotated by what is useful: hook, explanation, rhythm, analogy, humor, reflection, etc.

Extract reusable properties rather than copying distinctive phrasing:

- hook families;
- narrative beats;
- sentence rhythm;
- information/reflection ratio;
- analogy frequency and function;
- uncertainty markers;
- skepticism/hype handling;
- first-person usage;
- humor mechanism;
- transitions;
- mini-conclusions;
- final synthesis;
- AI-language anti-patterns.

Update only the durable editorial artifacts first:

```text
editorial/voice_profile.md
editorial/discourse_profile.md
```

Prompts are implementations of these profiles, not the source of truth.

**Exit criteria:** a human can read the profiles and recognize the intended voice without reading agent code.

---

## Milestone 3 — Build a small editorial regression set

**Goal:** avoid improving one episode while silently degrading another.

Create a small curated set of 3–5 historical news windows with expected qualitative properties, not exact scripts.

Examples of assertions:

- major human-impact story should outrank a funding-only story;
- episode plan should contain a non-generic central question;
- at least one useful analogy when a technical concept needs translation;
- explicit uncertainty when evidence is incomplete;
- no forbidden plastic-AI phrases;
- no unsupported factual claims;
- target duration remains 7–20 minutes;
- `ai_smell_risk` should be low before publication.

Do not require deterministic prose equality. Test contracts and editorial properties.

**Exit criteria:** changes to agents/profiles can be evaluated against multiple known scenarios.

---

## Milestone 4 — Improve multimedia semantics

**Goal:** make visuals explanatory rather than decorative.

Only after the script is consistently good:

- distinguish presenter, image, b-roll, diagram, chart, screenshot, logo;
- prioritize diagrams/visual explanations for analogies and technical concepts;
- validate media relevance before accepting the first search result;
- keep the hard media-download cap;
- retain provider/fallback provenance in `run_report.json`.

Avoid building a heavy media-ranking stack before real scripts demonstrate the need.

**Exit criteria:** multimedia materially improves understanding in sampled episodes.

---

## Milestone 5 — Render an actual video

**Goal:** add a deterministic renderer downstream of approved editorial artifacts.

Renderer input contract:

```text
scripts/<date>/script.txt
scripts/<date>/episode_plan.json
multimedia/<date>/plan.json
multimedia/<date>/manifest.json
```

Then add, incrementally:

1. TTS;
2. timed subtitles;
3. presenter/B-roll sequencing;
4. transitions;
5. final MP4 under `videos/<date>/`.

Keep rendering separate from editorial agents so failures do not require regenerating the script.

**Exit criteria:** a reproducible MP4 can be regenerated from persisted episode artifacts.

---

## Milestone 6 — Publication package + human approval

**Goal:** prepare YouTube-ready metadata without auto-publishing prematurely.

Generate:

- title candidates;
- description;
- chapters;
- tags/topics;
- thumbnail brief;
- factual/source notes.

Require explicit human approval before upload until several episodes are consistently good.

**Exit criteria:** publishing is a reviewable operation, not an opaque side effect of generation.

---

## Milestone 7 — Learn from real audience behavior

**Goal:** close the loop using actual outcomes rather than imagined retention rules.

Track eventually:

- CTR;
- retention at 15s / 30s / key transitions;
- average view duration;
- completion rate;
- comments/shares;
- qualitative feedback.

Feed learnings back into editorial profiles and Attention evaluation carefully. Do not optimize away rigor, nuance, or humanistic values for short-term engagement.

**Exit criteria:** editorial changes cite observed audience evidence instead of intuition alone.

---

# Priority order

```text
NOW
1. Real editorial E2E from latest news
2. Inspect plan + script + report
3. Voice DNA calibration with reference scripts
4. Small editorial regression set

NEXT
5. Better multimedia semantics
6. TTS + subtitles + renderer

LATER
7. Publication package
8. Human approval workflow
9. YouTube upload
10. Analytics feedback loop
```

The guiding rule is simple: **do not automate distribution faster than the system learns to produce something worth distributing.**
