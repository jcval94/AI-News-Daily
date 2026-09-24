# Real OTIO export replay — 2026-09-04

The repository regression suite exports the real 2026-09-04 virtual timeline to native OpenTimelineIO 0.18.1, serializes it with the core `otio_json` adapter, reads it back, and validates the production contract.

Expected round-trip:

- duration: **917.6 s**
- tracks: **V4, V3, V2, V1, A1**
- clips: **65**
  - V1 virtual A-roll: 25
  - A1 dialogue placeholders: 25
  - V2 media cues: 15
- markers: **36**
- V2 resolved historical assets: **0**
- V2 MissingReference placeholders: **15**

The native `.otio` file is intentionally treated as a generated artifact rather than duplicated in repository history. `virtual_timeline.json` remains the source contract; CI proves that it can be losslessly mapped to the OTIO fields we depend on.

This replay remains pre-recording. It validates interchange structure, not real camera timecode.
