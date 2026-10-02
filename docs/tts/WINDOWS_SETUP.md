# Windows 11 setup

Keep the repo's core `.venv` unchanged. Create an isolated TTS runtime:

```powershell
py -3.12 -m venv .venv-tts
.\.venv-tts\Scripts\python.exe -m pip install --upgrade pip
.\.venv-tts\Scripts\python.exe -m pip install kokoro==0.9.4 soundfile
.\.venv-tts\Scripts\python.exe -m pip install piper-tts edge-tts
```

Install/verify FFmpeg with `ffmpeg -version`. Kokoro uses espeak-ng for Spanish G2P; verify the current Kokoro Windows installation on the Zenbook before calling it production-ready.

Piper voice download:

```powershell
New-Item -ItemType Directory -Force .local\models\piper | Out-Null
.\.venv-tts\Scripts\python.exe -m piper.download_voices --data-dir .local\models\piper es_MX-claude-high es_MX-ald-medium
```

No model download is required by CI. Edge-TTS needs internet and is never part of the automatic local fallback path.

## Local acceptance harness

The committed Windows/local harness now owns the operational entrypoint. The normal repo Python launches orchestration; the actual TTS engine remains isolated in `.venv-tts`.

```powershell
.\.venv\Scripts\python.exe -m pipeline.local tts doctor
.\.venv\Scripts\python.exe -m pipeline.local tts smoke
.\.venv\Scripts\python.exe -m pipeline.local tts benchmark
.\.venv\Scripts\python.exe -m pipeline.local tts render --script latest
```

For a complete physical acceptance pass:

```powershell
.\.venv\Scripts\python.exe -m pipeline.local tts accept --script latest
```

`accept` runs, in order:

1. runtime/tool/model doctor;
2. short Kokoro + Piper smoke synthesis;
3. full render of the selected approved script;
4. reproducible voice bake-off;
5. a machine-readable report at `.local/tts/acceptance.latest.json`.

Use `--include-edge` only when deliberately benchmarking the online challenger.

The doctor treats the primary/fallback local engines, the isolated Python runtime and FFmpeg as required. GitHub CLI and espeak-ng are reported separately so a missing publishing tool does not make synthesis itself look broken.

## Promotion

After listening and accepting a render:

```powershell
.\.venv\Scripts\python.exe -m pipeline.local tts promote --script latest
```

This uploads only compressed previews to a bounded GitHub Release and writes the small `narration_web.json` contract locally.

To close the loop and trigger the configured Pages branch with only that lightweight contract:

```powershell
.\.venv\Scripts\python.exe -m pipeline.local tts promote --script latest --push-contract
```

The same pattern is available for the bake-off:

```powershell
.\.venv\Scripts\python.exe -m pipeline.local tts promote-benchmark --script latest --push-contract
```

High-quality WAV, native engine output, models and local logs remain under `.local/` and are never committed.
