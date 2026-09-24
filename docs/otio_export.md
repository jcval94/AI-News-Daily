# OpenTimelineIO export

The pre-recording timeline is exported to native OpenTimelineIO after `virtual_timeline.json` is validated.

Outputs:

- `timeline.otio` — native OTIO JSON interchange file;
- `timeline_otio_validation.json` — deterministic round-trip report.

## Why OTIO

OpenTimelineIO is the interchange boundary, not the editor.

The repository keeps its own production semantics in `virtual_timeline.json`, then serializes those semantics into an industry-standard editorial model. Resolve-specific behavior belongs to a later bridge.

This keeps:

```
AI News contracts
      ↓
virtual_timeline.json
      ↓
timeline.otio
      ↓
editor-specific bridge
      ↓
DaVinci Resolve / another NLE
```

## Mapping

### V1 / A1 placeholders

Virtual presenter/dialogue clips become OTIO `Clip` objects with:

- an explicit `source_range`;
- `MissingReference`;
- `take_id` and `replace_key` metadata.

The missing reference is intentional: no real A-roll exists yet.

### V2 media

Resolved assets use `ExternalReference`.

Missing assets use `MissingReference` and preserve cue/blocker metadata.

Sparse placement is represented by OTIO `Gap` objects. The export never compresses V2 merely because no media is present between two cues.

### V3 / V4

Reserved empty tracks receive a full-duration Gap. This preserves the intended track layout for downstream tools.

### Markers

Virtual timeline take/section markers are attached to the top-level OTIO Stack with zero-duration `Marker` ranges.

### Time

Seconds from the virtual contract are quantized to integer frames at the configured frame rate.

The default current capture contract is 30 fps. The exporter never claims frame accuracy before recording; quantization only makes the interchange model internally valid.

## Metadata namespace

Custom metadata lives under:

`ai_news_daily`

This includes clip IDs, take IDs, cue IDs, replacement keys, editorial role, style/readiness provenance, and source metadata.

Editor bridges should consume this namespace instead of parsing display names.

## Round-trip gate

After writing `timeline.otio`, production immediately reads it back through the native `otio_json` adapter and verifies:

- timeline duration;
- track order;
- clip count;
- marker count.

If round-trip validation fails, the export fails closed.

## Adapter policy

Only the core `opentimelineio` package is required at this stage.

We intentionally do not install the broader adapter bundle yet. Native `.otio` is the lossless source interchange. FCPXML/Resolve export will be a separate layer because non-native adapters can be lossy and have different maintenance/support levels.
