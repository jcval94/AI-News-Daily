# Placeholder media

`pipeline.placeholder_media` materializes lightweight PNG slates so the abstract timeline can become a real NLE timeline before recording.

It creates:

```
scripts/<date>/placeholder_media/
├── placeholder_manifest.json
├── v1/
│   └── <take_id>.png
└── v2/
    └── <cue_id>.png
```

Policy:

- every V1 take gets a presenter slate;
- only unresolved V2 cues get a B-roll slate;
- resolved media is never replaced;
- placeholders are explicitly non-publishable;
- default canvas is 1280x720 to keep artifacts small while remaining readable in a 4K timeline.

The manifest keeps stable take/cue identities, intended timeline timing, logical repository paths and SHA-256 hashes.
