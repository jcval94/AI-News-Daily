# YouTube clips as GitHub Actions artifacts

This is an isolated feasibility experiment. It downloads the opening seconds of ten
rights-curated YouTube videos, validates the resulting media, and retains the clips
only in a short-lived GitHub Actions artifact.

It does **not** change `pipeline.footage`, feed canonical multimedia, publish an
episode, or establish that a discovered YouTube link is reusable. The production
contract remains metadata-only until a separate rights and architecture decision is
made.

## Sample

The catalog is fixed so repeated runs are comparable:

| Cohort | Count | Coverage |
|---|---:|---|
| `famous_open_movie` | 5 | Big Buck Bunny, Sintel, Tears of Steel, Cosmos Laundromat, Spring |
| `random_cc` | 5 | Waterfall, robotics, coding, city timelapse, science experiment |

Every entry has explicit Creative Commons Attribution evidence. Entries whose
license comes from YouTube metadata fail closed if the live metadata no longer says
`Creative Commons Attribution license (reuse allowed)`. Publisher-licensed Blender
films are pinned to the expected official channel and link to the publisher's license
page.

## Run contract

The workflow `.github/workflows/youtube-artifact-experiment.yml`:

1. installs the pinned `yt-dlp` release and Node.js runtime;
2. uses YouTube's unauthenticated embedded-player client, which all ten curated
   videos permit;
3. downloads at most the first 15 seconds at 360p with two workers;
4. rejects live content, channel drift, unexpected licensing, oversized files, and
   malformed media;
5. requires 10/10 successful clips;
6. uploads results even when the gate fails, so anti-bot, format, or network failures
   remain inspectable;
7. retains the artifact for seven days and never commits MP4 files.

Run it from **Actions → Experiment — YouTube clips as artifacts → Run workflow**.
The manual inputs can vary clip duration (1–60 seconds), concurrency (1–4), and the
runner fleet without changing the ten-video catalog. The default is `macos-15` because
the shared Ubuntu Actions egress range currently receives YouTube's pre-authentication
bot challenge; `ubuntu-latest` remains selectable to reproduce that failure mode.

The artifact contains:

```text
catalog.json        exact catalog snapshot used by the run
manifest.json       machine-readable results and environment versions
SUMMARY.md          human-readable 10-row outcome table
ATTRIBUTION.md      source, creator, license, evidence, and modification notes
SHA256SUMS          integrity hashes
videos/
  01_<video-id>/
    <video-id>.mp4
    metadata.json   sanitized metadata; signed media URLs are removed
```

## Local deterministic checks

The unit tests do not contact YouTube:

```bash
python -m unittest tests.test_youtube_artifact_experiment -v
```

A live run requires `yt-dlp`, `ffmpeg`, `ffprobe`, and Node.js:

```bash
python -m experiments.youtube_artifacts.download \
  --output youtube-artifact-output \
  --clip-seconds 15 \
  --workers 2 \
  --required-successes 10
```

Use only material you are authorized to download and follow the platform terms that
apply to the operator. Creative Commons licensing still requires attribution and may
not resolve privacy, trademark, publicity, or third-party-content issues.
