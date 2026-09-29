# Local-first TTS

TTS convierte el `script_sections.json` canónico en narración por sección sin alterar ni bloquear producción editorial. El código portable vive en `pipeline/tts/`; WAV, modelos, caché y logs viven bajo `.local/tts/` y `.local/models/`.

```powershell
py -3.12 -m venv .venv-tts
.\.venv-tts\Scripts\python.exe -m pip install kokoro==0.9.4 soundfile piper-tts edge-tts
.\.venv\Scripts\python.exe -m pipeline.tts render --script latest
.\.venv\Scripts\python.exe -m pipeline.tts benchmark
.\.venv\Scripts\python.exe -m pipeline.tts validate .local\tts\<episode>\<run>\narration_manifest.json
```

Kokoro es el candidato local principal; Piper es fallback local; Edge-TTS sólo benchmark online. FFmpeg es obligatorio para el derivado PCM 48 kHz y el preview web.
