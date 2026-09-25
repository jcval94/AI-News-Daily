# Pre-recording Preview Render

This stage turns the pre-recording editing contracts into a lightweight video that can be watched before JC records the real A-roll.

It is a **review artifact**, not a publishable video.

## Visual rule

The renderer flattens the planned visual stack with one simple priority:

```
V2 B-roll / evidence
        ↓ overrides
V1 JC virtual A-roll
```

The underlying timeline remains unchanged. This is only a viewing projection of the current plan.

## Outputs

Canonical, small contracts:

```
scripts/<date>/
├── pre_recording_preview_plan.json
└── pre_recording_preview_validation.json
```

Run-artifact-only media:

```
previews/<date>/
└── pre_recording_preview.mp4
```

The MP4 is intentionally excluded from canonical Git history to avoid repository growth.

## Preview format

Default:

- 960×540
- 15 fps
- H.264 / yuv420p
- silent AAC stereo track
- permanent `PRE-RECORDING PREVIEW | TIMING ESTIMADO | NO PUBLICAR` watermark

The lower resolution/frame rate are deliberate. The purpose is to evaluate rhythm, visual density, missing media and sequence structure, not final image quality.

## Missing or undecodable media

Physical existence is checked when the preview plan is built.

For video files, the renderer also probes and smoke-decodes the source with FFmpeg. If a source exists but FFmpeg cannot decode it, the preview does not silently omit the interval and does not invalidate the editorial contract.

That interval receives a diagnostic slate and the validation report records:

- segment ID;
- placement ID;
- logical media path;
- decode error;
- total fallback count.

This behavior is preview-only. It does not rewrite `edit_manifest.json`, `timeline.otio` or the Resolve plan.

## Validation

After encoding, `ffprobe` verifies:

- output exists and is non-empty;
- expected resolution;
- duration within bounded tolerance;
- video codec presence;
- silent audio track presence.

The validation always declares:

```
publishable = false
frame_accurate = false
```

Real A-roll alignment is still required.

## CLI

Full render:

```bash
python -m pipeline.preview_render \
  --target-date YYYY-MM-DD \
  --repo-root . \
  --scripts-dir scripts \
  --output previews/YYYY-MM-DD/pre_recording_preview.mp4
```

Plan only:

```bash
python -m pipeline.preview_render \
  --target-date YYYY-MM-DD \
  --repo-root . \
  --scripts-dir scripts \
  --plan-only
```

## Production gate

The main workflow and backfill both render this preview before promotion. A promoted episode must therefore have a valid preview plan and successful FFmpeg/ffprobe validation, while the large MP4 itself remains in the isolated run artifact.
