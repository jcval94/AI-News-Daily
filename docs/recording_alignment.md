# Recording Alignment + DaVinci Resolve

This layer decides which recorded retake should become the real A-roll and converts speech timing into an auditable contract.

DaVinci Resolve is the primary local post-production host. WhisperX is an optional local timing engine, not a repository dependency.

## Why the responsibilities are split

Use each tool for the job it is good at:

```
camera scratch audio
        ↓
WhisperX
        ↓
word timestamps + transcript fidelity
        ↓
recording_alignment.json
        ↓
Resolve
        ├── waveform-sync external lav audio
        └── later build/import the aligned rough cut
```

The Python contract decides which retake best matches the approved `spoken_text`.

Resolve executes media synchronization and timeline work.

## Before recording

Production automatically generates:

```
scripts/<date>/recording_alignment_contract.json
```

It explicitly remains:

```
ready_for_transcription = false
ready_for_alignment = false
blocker = recording_ingest_manifest_required
```

No recording is invented.

## Keep camera scratch audio enabled

Even when recording a separate lavalier or microphone, keep camera scratch audio enabled.

This gives two independent benefits:

1. WhisperX can transcribe the video itself, so word timestamps share the video's timebase.
2. Resolve can sync the external lav track to the camera clip by waveform.

Without camera scratch audio, an external transcript can still judge whether the words are correct, but its timestamps belong to the external recorder clock. The pipeline therefore refuses to treat those times as video trims.

## Local sequence after recording

### 1. Scan camera/audio

```bash
python -m pipeline.recording_ingest \
  --target-date YYYY-MM-DD \
  --input-dir "recordings/YYYY-MM-DD/inbox" \
  --enforce
```

This writes `recording_ingest_manifest.json`.

### 2. Run WhisperX locally

WhisperX is deliberately not installed in the project dependency lock because it brings a large PyTorch/GPU stack.

Install it in the local editing environment separately, then run:

```bash
python -m pipeline.whisperx_adapter \
  --ingest-manifest scripts/YYYY-MM-DD/recording_ingest_manifest.json \
  --recordings-root recordings/YYYY-MM-DD/inbox \
  --output recordings/YYYY-MM-DD/transcripts/recording_transcript_bundle.json \
  --model large-v3 \
  --language es
```

The adapter keeps forced alignment enabled and asks WhisperX for JSON word timestamps.

When camera scratch audio exists, the adapter transcribes the camera video even if an external lav file exists. The lav remains the preferred post-production audio, but video-relative timing stays trustworthy.

### 3. Select retakes and calculate trims

```bash
python -m pipeline.recording_alignment \
  --target-date YYYY-MM-DD \
  --transcript-bundle recordings/YYYY-MM-DD/transcripts/recording_transcript_bundle.json \
  --enforce
```

This writes:

```
scripts/YYYY-MM-DD/recording_alignment.json
```

For every retake it measures:

- word error rate;
- expected-word coverage;
- mean word confidence when available;
- provisional technical ingest score;
- video-relative first/last spoken word;
- source trim in/out.

Transcript fidelity deliberately outweighs the technical ingest score.

## Auto-selection policy

Default thresholds:

- WER <= 12%;
- expected-word coverage >= 94%;
- word confidence >= 0.55 when supplied;
- two near-equal candidates within 0.03 selection score trigger human review.

A technically excellent retake does not win automatically if it skipped or changed the script.

## Resolve waveform-sync bridge

After alignment:

```bash
python -m pipeline.resolve_alignment_bridge \
  --alignment scripts/YYYY-MM-DD/recording_alignment.json \
  --recordings-root recordings/YYYY-MM-DD/inbox \
  --execute
```

The bridge:

- loads or creates the episode Resolve project;
- imports selected camera clips into `04_A-Roll_Recorded`;
- imports selected external audio into `05_Audio_Recorded`;
- calls `MediaPool.AutoSyncAudio` in waveform mode;
- uses enum constants obtained from the live Resolve handle;
- retains embedded camera audio;
- reads sync-related clip properties after the call;
- fails closed if required sync cannot be verified.

The boolean returned by the API is not accepted as sufficient proof by itself.

## Resolve-native transcription

Resolve can run native transcription, but this pipeline treats it as optional diagnostic context.

It is not alignment authority because the durable contract requires complete, machine-readable word timestamps. The pipeline therefore remains usable across Resolve versions/editions without coupling retake selection to one proprietary transcript representation.

## Current stopping point

This phase ends with:

```
recording_alignment.json
        +
Resolve-synced selected media
```

The next layer will build the real-duration aligned timeline:

- replace V1 virtual takes with selected camera clips;
- use video-relative trim windows;
- retime V2 cues against actual spoken duration;
- export a new aligned OTIO;
- import it into Resolve under a new non-destructive timeline name.

The pre-recording rough cut is never overwritten.
