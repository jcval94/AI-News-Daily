# DaVinci Resolve Bridge v0

The Resolve bridge is intentionally split into two layers:

1. `resolve_bridge_plan.json` is deterministic and CI-testable on any machine.
2. `--execute` talks to the local DaVinci Resolve scripting API.

GitHub Actions never pretends to execute Resolve.

## Inputs and generated files

The bridge consumes:

- `virtual_timeline.json`;
- canonical `timeline.otio`;
- `placeholder_media/placeholder_manifest.json`;
- resolved multimedia under `multimedia/<date>/...`.

It generates:

- `resolve_bridge_plan.json`;
- `resolve_timeline.otio`;
- `resolve_otio_validation.json`;
- optionally, after local execution, `resolve_bridge_execution.json`.

`timeline.otio` remains the canonical NLE-neutral interchange. The bridge never mutates it.

`resolve_timeline.otio` is a Resolve-oriented materialization of that timeline: planned V1/V2 clips are given concrete ExternalReference URLs pointing to either real media or physical placeholder slates.

## Why native OTIO import is the primary execution path

The deterministic plan still validates every placement by track, frame and duration, but Resolve execution does **not** rebuild the timeline clip-by-clip by default.

The primary strategy is:

```
virtual_timeline.json
        ↓
timeline.otio
        ↓
materialize V1/V2 media references
        ↓
resolve_timeline.otio
        ↓
MediaPool.ImportTimelineFromFile(...)
        ↓
Resolve rough-cut timeline
```

This keeps our own placement validation while delegating the actual editorial reconstruction to Resolve's native OTIO importer.

Direct `AppendToTimeline` placement is deliberately not the default v0 execution path.

## Project layout

v0 creates or loads the target project, applies timeline settings, creates its organizational bins and imports a fresh rough-cut timeline:

- V1 — JC A-Roll placeholders
- V2 — B-roll / evidence
- V3 — Graphics
- V4 — Titles
- A1 — JC Dialogue

Media Pool bins:

- `00_OTIO_Imported`
- `01_A-Roll_Placeholders`
- `02_B-Roll`
- `03_Graphics`
- `99_Missing_B-Roll`

The bridge refuses to overwrite an existing timeline with the same name.

## Placeholder behavior

Every V1 take gets a lightweight PNG slate with its stable `take_id`.

Unresolved V2 cues get a separate missing-media slate. Resolved B-roll always points to the real asset and is never replaced by a placeholder.

The PNGs are proxies, not final media. Their manifest carries stable IDs and expected timing; `resolve_timeline.otio` supplies concrete file references while preserving the canonical timeline structure.

A1 remains intentionally unresolved until real dialogue/A-roll exists.

## Local execution

With DaVinci Resolve running and its scripting module available:

```bash
python -m pipeline.resolve_bridge --target-date YYYY-MM-DD --execute
```

For plan/materialization only:

```bash
python -m pipeline.resolve_bridge --target-date YYYY-MM-DD
```

The non-execution mode still requires `timeline.otio` and writes `resolve_timeline.otio`, so CI validates the same handoff that the local Resolve executor will consume.

The module first tries `DaVinciResolveScript` directly, then the standard Developer/Scripting module locations and `RESOLVE_SCRIPT_API`.

## Safety

v0 fails closed when:

- a source file is missing;
- a path escapes the repository root;
- a track contains overlapping placements;
- the materialized OTIO loses a planned media reference during round-trip;
- project settings are rejected;
- a project exists and `--reuse-project` was not supplied;
- the target timeline already exists;
- Resolve cannot import the materialized OTIO.

Even after successful execution, `final_edit_ready=false` because real A-roll has not been ingested/aligned.

## What CI proves vs what still needs the local Resolve machine

CI proves:

- all planned media paths exist;
- every V1/V2 planned clip can be materialized as an OTIO ExternalReference;
- the materialized OTIO survives a read-back;
- track/frame/marker contracts remain internally consistent;
- a fake Resolve API accepts the expected call sequence.

CI cannot prove how a specific installed Resolve build decodes every still/video codec or renders the imported timeline. The first real local execution remains an explicit acceptance test rather than a hidden assumption.
