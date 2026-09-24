# Edit manifest contract

`multimedia/YYYY-MM-DD/edit_manifest.json` is the editor-facing handoff contract for an approved episode.

It is intentionally **not** another narration artifact. `script.txt` stays clean. The manifest overlays editing guidance on top of the approved script and downloaded multimedia.

## Authority model

The contract separates three kinds of authority:

- **factual/editorial authority** remains in the approved script, episode plan, claim ledger, and source artifacts;
- **timeline authority** is estimated before recording and therefore explicitly marked `requires_recording_retime: true`;
- **director signals** are suggestions, never factual or editorial overrides.

A downstream editor may change a transition or visual treatment without changing what the essay claims.

## Director signals

Every timeline interval contains a `director` object. The important distinction is:

- `intent`: why the visual choice exists;
- `visual_role`: evidence, explanation, context, rhythm, emotional grounding, presenter, etc.;
- `transition_in` / `transition_out`: suggested cut language;
- `treatment`: suggested visual treatment such as natural motion or a subtle push-in;
- `pacing`: fast / normal / calm guidance;
- `return_to_presenter`: whether the cue should resolve back to A-roll;
- `note`: concise producer/director guidance.

This keeps narrative intent stable while allowing style presets to evolve later.

## Timing

Version 1 uses script word timing because no recorded A-roll exists yet.

The contract must never imply frame accuracy before recording. A later ingest/alignment phase should preserve cue IDs and script anchors while replacing estimated timestamps with real spoken timestamps.

## Presenter-first baseline

Presenter is the default visual continuity. Multimedia is an overlay used when it materially adds evidence, explanation, context, analogy, contrast, emotional grounding, or intentional rhythm.

The generated timeline therefore alternates explicit `presenter` and `media` intervals rather than assuming that every available asset must be shown.

## Local-editor future

The manifest is deliberately NLE-neutral. Future adapters can translate it to OpenTimelineIO, DaVinci Resolve, CapCut handoff packages, or another editor without changing the editorial pipeline.
