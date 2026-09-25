# DaVinci Resolve Bridge v0

The Resolve bridge is intentionally split into two layers:

1. `resolve_bridge_plan.json` is deterministic and CI-testable on any machine.
2. `--execute` talks to the local DaVinci Resolve scripting API.

GitHub Actions never pretends to execute Resolve.

## Inputs

The bridge consumes:

- `virtual_timeline.json`;
- `placeholder_media/placeholder_manifest.json`;
- resolved multimedia under `multimedia/<date>/...`.

## Project layout

v0 creates a fresh project and a non-destructive rough-cut timeline:

- V1 — JC A-Roll placeholders
- V2 — B-roll / evidence
- V3 — Graphics
- V4 — Titles
- A1 — JC Dialogue

Media Pool bins:

- `01_A-Roll_Placeholders`
- `02_B-Roll`
- `03_Graphics`
- `99_Missing_B-Roll`

The bridge refuses to overwrite an existing timeline with the same name.

## Placeholder behavior

Every V1 take gets a lightweight PNG slate with its stable `take_id`.

Unresolved V2 cues get a separate missing-media slate. Resolved B-roll always uses the real asset and is never replaced by a placeholder.

The PNGs are proxies, not final media. Their manifest carries the intended timeline duration; the bridge places them using frame-accurate record positions from the estimated virtual timeline.

## Local execution

With DaVinci Resolve running and its scripting module available:

```bash
python -m pipeline.resolve_bridge --target-date YYYY-MM-DD --execute
```

For plan-only validation:

```bash
python -m pipeline.resolve_bridge --target-date YYYY-MM-DD
```

The module first tries `DaVinciResolveScript` directly, then the standard Developer/Scripting module locations and `RESOLVE_SCRIPT_API`.

## Safety

v0 fails closed when:

- a source file is missing;
- a path escapes the repository root;
- a track contains overlapping placements;
- project settings are rejected;
- a project exists and `--reuse-project` was not supplied;
- the target timeline already exists.

Even after successful execution, `final_edit_ready=false` because real A-roll has not been ingested/aligned.
