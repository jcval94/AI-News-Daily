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

Maintain two complementary regression layers: historical human-labelled scripts for judge calibration, plus model-backed scenarios that execute the CURRENT agents against frozen news windows. The model-backed workflow is manual/on-demand because it consumes API budget.

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

# Current priority order

```text
NOW
1. Run Local Harness P0 on the real Windows 11 Zenbook
2. Verify Resolve scripting + native OTIO with doctor -Resolve -Deep -OtioSmoke
3. Snapshot the real toolchain/hardware; choose WhisperX CPU/GPU strategy from evidence
4. Run one controlled P1 episode through ingest → transcription → alignment → Resolve sync/import

NEXT
5. Implement aligned_timeline.build from real A-roll timings
6. Add proxy generation only if measured hardware/media performance needs it
7. Add captions and audio normalization downstream of aligned media
8. Validate one end-to-end rough cut in Resolve without overwriting the pre-recording timeline

LATER
9. Thin MCP layer for creating valid jobs and reading receipts — never arbitrary shell
10. Publication package + human approval
11. YouTube upload only after repeated local/production acceptance
12. Audience analytics feedback loop
```

## Local post-production milestone — implemented

The repository already includes:

- Recording Pack + teleprompter;
- Recording Ingest Contract/scanner;
- WhisperX adapter;
- Recording Alignment;
- Resolve Alignment Bridge;
- Virtual Timeline + native OTIO;
- physical placeholders;
- pre-recording preview;
- Asset Readiness Gate;
- Windows Local Editing Harness with doctor/toolchain/status;
- repo→local staging trust boundary;
- idempotent receipts and Windows CI.

The next architectural milestone is **real workstation acceptance**, not another abstraction layer.

**Exit criteria:** P0/P0-Resolve pass on the Zenbook, then one P1 episode produces durable receipts and a non-destructive Resolve timeline using real media.

The guiding rule remains: **do not automate distribution faster than the system learns to produce something worth distributing, and do not automate local side effects faster than the workstation can prove them.**
