# Windows 11 setup

Keep the repo's core `.venv` unchanged. Kokoro 0.9.4 requires Python
`>=3.10,<3.13`; Python 3.12 is the tested target. Create an isolated TTS runtime:

```powershell
py -3.12 -m venv .venv-tts
.\.venv-tts\Scripts\python.exe -m pip install --upgrade pip
.\.venv-tts\Scripts\python.exe -m pip install -r requirements-tts.txt
```

If the Windows Python launcher has no registered 3.12 interpreter but Conda is
already installed, keep a small base interpreter and create the standard venv
from it:

```powershell
conda create -n ai-news-tts-py312 python=3.12 pip -y
conda run -n ai-news-tts-py312 python -m venv .venv-tts
.\.venv-tts\Scripts\python.exe -m pip install -r requirements-tts.txt
```

Keep the Conda base environment: the Windows venv records it as its base
interpreter. Do not point `config/tts.yaml` at a Conda prefix, because Conda
places `python.exe` at the prefix root while the committed runtime contract is
`.venv-tts/Scripts/python.exe`.

Install/verify FFmpeg with `ffmpeg -version`. Kokoro uses espeak-ng for Spanish
G2P. On the accepted Windows setup, `espeakng-loader` is installed inside the
TTS venv even though no standalone `espeak-ng.exe` is on PATH. Treat that doctor
warning as non-blocking only after the Kokoro smoke produces valid Spanish WAV.

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

## Automatic local audio library

Render every approved episode that does not already have current audio:

```powershell
.\.venv\Scripts\python.exe -m pipeline.local tts render-pending
```

The command reuses valid runs with the same script identity, renders only missing
or changed scripts, and writes a local listening page at
`.local\tts\library\index.html`. It does not publish to Pages or enable Edge.

On the dedicated clean TTS checkout, register the daily 09:00 Windows task:

```powershell
.\scripts\local\tts_automation.ps1 -Register
```

The task runs only in the interactive user session, uses the Windows default AC
power restrictions, catches up after a missed start, refuses dirty checkouts,
fast-forwards `main`, and then runs `render-pending`. For a manual offline run
without Git synchronization, use:

```powershell
.\scripts\local\tts_automation.ps1 -NoSync
```
