# Local Media Forensics Worker

This directory is the local-compute extension of the killer multimedia experiment.

The repository remains the **control plane**. Large media stays on the workstation.

## Why local changes the architecture

A cloud-only retriever is forced to decide from URLs, titles, thumbnails and limited previews.
A local worker can instead:

1. open the real page in a browser;
2. preserve source metadata;
3. inspect authenticated pages when the user is already legitimately signed in;
4. probe video metadata without downloading the full binary;
5. download only when the job policy and rights state allow it;
6. sample frames with FFmpeg;
7. OCR screenshots/frames;
8. inspect transcripts/subtitles;
9. run local image-text similarity or a VLM reranker;
10. locate scene intervals;
11. create a clip or Resolve manifest.

It must **not** bypass DRM, paywalls, access controls or licensing restrictions.

## Control plane vs data plane

```text
GitHub / ChatGPT
  killer case
      ↓
  exact reference
      ↓
  local_job.json
      ↓
──────────────────────── machine boundary ────────────────────────
      ↓
Local Media Forensics Worker
  browser probe
  metadata / transcript probe
  optional acquisition
  frame sampler
  OCR / semantic rerank
  scene scout
  rights gate
      ↓
  local_result.json
  resolve_manifest.json
  local media cache
──────────────────────────────────────────────────────────────────
      ↓
GitHub receives JSON evidence only
Large binaries remain local
```

## Local storage

Default recommendation on Windows:

```text
%LOCALAPPDATA%\AI-News-Daily\media-lab\
  cache\
  jobs\
  results\
  clips\
  logs\
```

The location is configurable through `AI_NEWS_MEDIA_LAB_HOME`.

Use content-addressed filenames where possible:

```text
cache/<sha256-prefix>/<sha256>.<ext>
```

This makes duplicate downloads naturally collapse.

## Acquisition policy

The job's `rights_status` drives what the worker may do.

| Rights state | Browser/metadata | Download | Clip/export |
|---|---:|---:|---:|
| usable | yes | if allowed | yes |
| reference_only | yes | no by default | no |
| review_required | yes | no by default | no |
| blocked | metadata only | no | no |

A local browser session is a discovery capability, **not** a rights override.

## Recommended Windows stack

- Python 3.11+
- Playwright + Chromium for deterministic browser inspection
- yt-dlp for metadata/subtitle probing and permitted video acquisition
- FFmpeg/ffprobe for technical inspection, frames and clips
- optional local OCR
- optional CLIP/SigLIP-style embedding model or local VLM
- DaVinci Resolve bridge for final clip handoff

Playwright supports explicit download persistence, while yt-dlp supports browser-cookie access for
legitimately authenticated sessions. Cookie files must never be committed to the repository.

## Killer cases with local execution

### Time Wizard

Local goal is **not** to scrape copyrighted card art into production.

Use browser inspection to:
- verify exact official identity;
- capture source metadata;
- optionally compare visual fingerprints/thumbnails;
- retain as `REFERENCE_ONLY`.

Then search separately for a reusable exact or editorially acceptable depiction.

### Lake Nyos

Because the USGS asset is public domain:
- fetch the exact source;
- hash it;
- inspect dimensions;
- retain the strongest version;
- generate a Resolve-ready manifest.

### Plato

Fetch the Commons asset with attribution metadata:
- original resolution;
- author;
- license;
- source URL;
- SHA-256.

### AlphaFold

Browser + page inspection is particularly valuable:
- identify the exact UI screenshot;
- verify that image pixels actually contain the structure viewer;
- OCR/interface-label check;
- preserve CC BY attribution;
- avoid irrelevant talking-head videos.

### iPhone 2007 keynote

This is where local execution adds the most value.

Use source metadata/transcript first. If acquisition is permitted for the selected source:

```text
timestamp hints
      ↓
download / permitted local source
      ↓
ffmpeg coarse sampling around hints
      ↓
visual/text scoring
      ↓
fine search around top intervals
      ↓
best 8–15 s clip
      ↓
Resolve manifest
```

If rights remain reference-only, retain timestamps and source reference but do not export the footage.

## The non-obvious advantage

The local worker lets the pipeline distinguish **search failure** from **production eligibility**.

A commercial asset can be:
- discovered exactly;
- visually verified exactly;
- scene-addressed exactly;
- and still remain reference-only.

That is a successful retrieval experiment, not a reason to corrupt identity with generic B-roll.
