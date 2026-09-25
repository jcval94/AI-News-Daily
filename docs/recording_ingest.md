# Recording Ingest Contract

This layer bridges the pre-recording take plan with future real camera/audio files.

It is intentionally split into two moments:

1. **prepare** — generated automatically now, even before JC records;
2. **scan** — run locally later, when real recordings exist.

## Canonical outputs before recording

Every approved episode gets:

```
scripts/<date>/
├── recording_ingest_contract.json
└── recording_ingest_instructions.md
```

These files are small and safe to keep in Git.

Raw recordings live outside canonical history under a local folder such as:

```
recordings/<date>/inbox/
```

The repository ignores `recordings/` entirely.

## Naming grammar

Use the stable `take_id` from `recording_pack.json`:

```
<take_id>__r<NN>__<label>.<ext>
```

Examples:

```
opening_t01__r01__camA.mov
opening_t01__r02__camA.mov
opening_t01__r02__audio.wav
b03_human_stakes_t01__r01__lav.wav
```

Rules:

- retakes start at `r01`;
- increment `r02`, `r03`, etc. for full repeated takes;
- camera labels such as `camA`, `camB`, `cam1`, `main` are supported;
- audio labels such as `audio`, `lav`, `mic`, `micA` are supported;
- take IDs are case-sensitive and must match the Recording Pack exactly.

## Camera scratch audio

Keep the camera microphone/scratch audio enabled even when the external lavalier is the audio you intend to publish.

The automated local flow needs that scratch waveform for two reasons:

- WhisperX can produce word timestamps in the camera video's own timebase;
- DaVinci Resolve can use `AutoSyncAudio` in waveform mode to attach the external lav track.

If the video has no scratch audio, the external recording can still be transcribed for script fidelity, but the pipeline will not pretend those timestamps are valid video trim points.

## Audio

A candidate is ready for future alignment when it has:

- one technically healthy video; and
- either healthy embedded audio or a healthy paired external audio file.

External audio must use the same `take_id` and retake number as the camera file.

## Scanner

Later, when real files exist:

```bash
python -m pipeline.recording_ingest \
  --target-date YYYY-MM-DD \
  --input-dir "/path/to/recordings/YYYY-MM-DD/inbox" \
  --enforce
```

The scanner:

- recursively reads supported video/audio files;
- parses `take_id` and retake identity;
- probes/decode-checks media with FFmpeg/ffprobe;
- verifies video duration, resolution and frame-rate recommendations;
- verifies audio decode and sample rate;
- groups camera/audio by take + retake;
- preserves every retake;
- marks one `technical_preferred` candidate per take when possible;
- writes `recording_ingest_manifest.json`.

It never moves or deletes source files.

## Technical preferred is not best performance

The provisional selector considers technical properties only:

- healthy decode;
- duration plausibility;
- resolution;
- preferred camera label;
- embedded or external audio availability.

It does **not** judge:

- delivery;
- facial expression;
- pronunciation;
- whether a sentence matches the approved script;
- whether a later retake sounds more natural.

That decision belongs to the later transcription/alignment phase.

Therefore:

```
technical_preferred != final_selected_take
```

## Privacy and portability

`recording_ingest_manifest.json` stores:

- relative file paths;
- sizes;
- SHA-256 hashes;
- codec/resolution/audio metadata;
- retake grouping.

It does not persist the absolute path of the user's machine.

## Fail-closed cases

The scanner blocks `ready_for_alignment` when:

- an expected take is missing;
- no technically usable candidate exists;
- a compliant filename references an unknown take ID;
- duplicate capture identities exist;
- a take has no healthy video;
- a take has neither embedded nor paired external audio;
- the selected candidate is implausibly short.

Unmatched camera dumps are reported as warnings instead of being silently assigned.

## Future WhisperX handoff

The next layer will consume:

- `recording_pack.json`;
- `recording_ingest_manifest.json`;
- the selected technical candidate and all alternates.

It will transcribe every candidate that matters, compare it with the expected `spoken_text`, align words/timestamps and may replace the technical preference with another retake.

The stable join key across the whole process is `take_id`.
