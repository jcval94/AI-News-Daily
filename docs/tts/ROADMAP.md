# TTS roadmap and Definition of Done

Status is intentionally conservative: code existing is not the same as a model being accepted on the Windows workstation.

## Phase 0 — repository audit

**Status:** done.

**DoD**
- canonical script source identified;
- Pages, multimedia, local harness, Resolve Bridge, workflows and retention patterns inspected;
- no parallel orchestration framework introduced.

**Decision:** `script_sections.json.sections[*].spoken_text` is the TTS source of truth. Hidden writer markers, Narrative Memory IDs and evidence metadata are not speech input.

## Phase 1 — architecture and contracts

**Status:** done.

**DoD**
- versioned full narration schema;
- lightweight web schema;
- deterministic section IDs/filenames;
- source/spoken separation;
- cumulative timestamps with arithmetic/contiguity validation;
- native/edit/web artifact classes defined;
- engine/network provenance recorded.

## Phase 2 — local scaffold

**Status:** code complete; workstation acceptance pending.

**DoD**
- TTS code isolated under `pipeline/tts/`;
- model/runtime packages isolated from core CI in `.venv-tts`;
- heavy outputs stay in `.local/tts`;
- `tts.render` is allowlisted in the existing local harness;
- no raw audio enters Git.

Acceptance pending: run the setup and render on the ASUS Zenbook S16.

## Phase 3 — first engine functional

**Status:** adapter implemented; real-machine acceptance pending.

**DoD**
- Kokoro renders a real approved episode by semantic section;
- native WAV is preserved;
- 48 kHz mono PCM s16le derivative is generated for editing;
- one master narration is reproducible;
- an unavailable primary engine restarts the whole run with Piper, never mixes voices section-by-section;
- Edge-TTS cannot be selected by an automated local render job.

## Phase 4 — Voice Bake-off

**Status:** experiment harness and fixture implemented; listening run pending.

**DoD**
- same representative fixture rendered by all configured candidates;
- technical metrics measured: generation time, duration, RTF, file size, format, errors;
- perceptual rubric completed by a human: naturalness, pronunciation, prosody, energy, clarity, pace, stability;
- winner selected only after listening;
- no synthetic "naturalness" score is treated as ground truth.

## Phase 5 — audio QA

**Status:** code complete; threshold calibration pending.

**DoD**
- file/existence, duration, sample rate, channels and PCM width checked;
- peak/RMS/clipping/silence checked without destructive processing;
- FFmpeg integrated LUFS and long-silence observations recorded;
- suspiciously short sections and manifest/file mismatches fail or warn explicitly;
- QA thresholds calibrated on real renders.

## Phase 6 — real script integration

**Status:** contract integration complete; real model run pending.

**DoD**
- a real approved `scripts/YYYY-MM-DD/script_sections.json` renders end-to-end;
- internal IDs/markers are demonstrably absent from synthesized text;
- every semantic section has one native/edit/web derivative;
- manifest `script_id` ties the audio to the exact script revision.

## Phase 7 — Pages publication and observability

**Status:** UI + deployed smoke contract implemented; real audio asset publication pending.

**DoD**
- Script view shows Voice/TTS availability, date/script identity, engine, voice, duration, section count, warnings;
- master and section players use `preload="none"`;
- missing TTS stays non-blocking;
- web audio is hosted outside Git history with bounded retention;
- Voice Bake-off candidates are listenable side-by-side;
- deployed Pages smoke test verifies the live TTS panel.

## Phase 8 — Resolve Bridge consumer

**Status:** intentionally deferred.

**DoD**
- Resolve reads `narration_manifest.json` rather than guessing filenames;
- narration import and section markers are idempotent;
- read-back verifies timeline placement;
- SRT/VTT can be derived from the same timings.

## File map

### Existing abstractions reused
- `scripts/YYYY-MM-DD/script.txt`
- `scripts/YYYY-MM-DD/script_sections.json`
- `pipeline/run.py` and `pipeline/script_sections.py`
- `pipeline/review_hub_v14.py` semantic Script map
- `pipeline/local/*` staged Windows harness
- `config/local/local_job.schema.json`
- `.github/workflows/editorial-review-hub.yml`
- `pipeline/architecture_manifest.py`
- existing bounded Pages history/review artifacts

### New
- `pipeline/tts/*`
- `config/tts.yaml`
- `config/tts/*.schema.json`
- `evals/tts/voice_bakeoff_es.txt`
- `docs/tts/*`
- `pipeline/review_hub_v15.py`
- `tests/tts/*`
- `tests/test_review_hub_tts.py`

### Modified
- `pipeline/review_hub.py`
- `pipeline/local/jobs.py`
- `config/local/local_job.schema.json`
- `docs/local/README.md`
- `pipeline/architecture_manifest.py`
- `tests/test_architecture_manifest.py`
- `tests/local/test_local_jobs.py`
- `.github/workflows/editorial-review-hub.yml`
- `.gitignore`

## GitHub Actions boundary

Actions should continue to own script/contracts/tests/Pages assembly and deployed smoke tests. Actions should **not** download Kokoro/Piper models or render production narration. The Windows workstation owns model inference, WAV masters, caches and heavy logs. A later publication step may upload bounded lightweight web derivatives and commit only the small web manifest.

## Experiments that still decide policy

1. Kokoro Spanish voice winner and usable speed range on the Zenbook.
2. Piper quality/RTF trade-off versus Kokoro and whether it is acceptable as emergency fallback.
3. Edge-TTS perceptual delta, treated only as an online benchmark.
4. pronunciation dictionary entries for OpenAI, LLM, GPT-5, NVIDIA, Claude, Gemini and future names;
5. LUFS/long-silence advisory thresholds from real narration rather than arbitrary mastering assumptions;
6. MP3 64 kbps versus Opus/AAC for Pages after browser/size listening comparison;
7. retention count and release-asset strategy after observing real asset sizes.
