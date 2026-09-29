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

No model download is required by CI. Edge-TTS needs internet and is never part of the local fallback path.
