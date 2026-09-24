# Virtual A-roll + abstract timeline

The virtual timeline lets production validate the shape of an episode before any real presenter footage exists.

It emits:

- `virtual_timeline.json` — NLE-neutral timeline contract;
- `timeline_preview.html` — standalone offline timeline viewer.

## Core model

The presenter exists on V1 from the beginning, even before recording.

Each Recording Pack take becomes one placeholder clip:

```
V1  [opening_t01][opening_t02][beat...][synthesis][cta]
```

Every placeholder has a stable `take_id` / `replace_key`. Real A-roll will later be aligned to those identities.

V2 contains visual/media cues from `edit_manifest.json`:

```
V2       [slot_001]       [slot_008]
V1  [opening_t01][opening_t02][beat...]
```

V2 overlays V1; it never deletes the underlying presenter clip.

## Missing assets remain visible

A missing B-roll asset does not disappear from the virtual edit.

Instead the timeline creates a `media_placeholder` carrying:

- cue ID;
- visual query;
- role;
- intended treatment;
- timing;
- blockers.

This is important because a timeline with silent missing gaps can look healthier than production actually is.

## Timing is intentionally provisional

All times are estimated from the approved script / Recording Pack.

The contract explicitly states:

- `frame_accurate: false`;
- `requires_recording_retime: true`;
- real A-roll may change take durations;
- B-roll must be retimed after speech alignment;
- estimated timeline seconds must never be interpreted as camera source timecode.

The future alignment layer should preserve `take_id`, replace the placeholder, and recalculate downstream timeline timing.

## Track layout

The abstract timeline currently defines:

- V4 — Titles
- V3 — Graphics
- V2 — B-roll / visual evidence
- V1 — JC virtual A-roll
- A1 — JC dialogue placeholder

V3/V4 are intentionally sparse until title/graphic rules are promoted from style guidance into concrete timeline events.

## Preview

`timeline_preview.html` is self-contained and offline.

It provides:

- horizontal timeline;
- zoom;
- fit-to-window;
- separate tracks;
- resolved vs placeholder clips;
- click-to-inspect clip metadata.

It is a diagnostic/edit-planning surface, not a rendered video.

## Readiness

A valid virtual timeline can be `ready_for_virtual_preview=true` while remaining:

- `ready_for_real_a_roll_replace=false`;
- `ready_for_automated_nle_import=false`.

That distinction prevents another false green before real recording and alignment exist.


## Format and markers

The virtual timeline inherits the Recording Pack capture recommendation instead of inventing NLE settings:

- resolution;
- frame rate;
- audio sample rate;
- aspect ratio.

It also emits deterministic markers for every take and the first take of each section. These markers are intended to map directly into future OTIO/Resolve exports and make retakes/navigation easy without another model call.
