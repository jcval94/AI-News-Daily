# Asset Readiness Gate

This stage answers a concrete pre-recording question:

> Is the visual package good enough to record against, and if not, what should be fixed first?

It is deliberately deterministic. It does not ask an LLM to judge taste.

## Inputs

- `virtual_timeline.json`
- `resolve_bridge_plan.json`
- optional `pre_recording_preview_validation.json`
- physical media files
- `config/asset_readiness.yaml`

## Core metrics

The report calculates both:

- resolved cue ratio;
- resolved planned-visual-seconds ratio.

It also counts:

- missing cues;
- degraded cues;
- technical failures;
- unresolved critical cues.

A low-resolution fallback still counts as resolved media. It is visible as degraded, but does not block by default.

## Critical visual roles

By default:

- `evidence`
- `historical_mirror`

must resolve before recording.

This prevents the presenter from recording a passage that depends on evidence while the corresponding visual remains unknown.

## Default gate

The default policy requires:

- >= 80% of planned cues resolved;
- >= 80% of planned visual seconds resolved;
- <= 3 missing non-critical cues;
- 0 unresolved critical cues;
- 0 technically broken cues.

Low resolution and short source duration are warnings by default rather than blockers.

## Technical inspection

Real assets are inspected from the repository root.

Images are opened and verified with Pillow.

Videos are inspected using the same shared FFmpeg/ffprobe path used by the pre-recording preview. A file that merely exists is not considered healthy.

## Outputs

```
scripts/<date>/
├── asset_readiness.json
└── asset_readiness.html
```

The HTML is a standalone operational radiography.

Example interpretation:

```
Cue coverage        92%
Seconds covered     94%
Missing cues        2
Degraded            1
Critical unresolved 0
Technical failures  0
READY TO RECORD
```

## Prioritized actions

Every gap becomes an explicit action:

- P0 — resolve critical evidence or replace/re-encode broken media;
- P1 — resolve non-critical missing visuals or intentionally accept presenter;
- P2 — prefer higher resolution / longer source if available.

This keeps low-resolution fallbacks viable without hiding quality debt.

## Enforcement

Production runs call the stage with `--enforce`.

When blocked, JSON and HTML are still written first, then the command exits non-zero. The isolated run therefore preserves the diagnosis while canonical promotion remains fail-closed.
