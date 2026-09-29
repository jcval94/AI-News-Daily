# Architecture

```text
script.txt + script_sections.json (authority)
        ↓
pipeline.tts.sections (spoken text only)
        ↓
engine adapter: Kokoro → Piper fallback | Edge benchmark only
        ↓
native WAV (preserved) → FFmpeg → mono PCM s16le / 48 kHz
        ↓
section QA → master concat → narration_manifest.json
        ↓
web derivative + narration_web.json (small publish contract)
        ↓
Review Hub Script tab (metadata first, audio preload=none)
        ↓ [future contract consumer]
Resolve Bridge / markers / SRT-VTT
```

TTS is optional. Failure never changes `run_state.json`, approval, script generation, multimedia generation or Pages publication. `script_sections.json.sections[*].spoken_text` is authoritative; hidden writer markers are already removed upstream. `normalize_spoken_text` strips presentation markup defensively and applies an optional pronunciation dictionary.

Do not place engine packages in the core lock: the separate `.venv-tts` keeps Torch/ONNX/online challenger dependencies out of normal CI.
