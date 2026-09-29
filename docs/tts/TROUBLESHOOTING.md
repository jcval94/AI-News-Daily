# Troubleshooting

- `TTS runtime not found`: create `.venv-tts` as documented in `WINDOWS_SETUP.md`.
- Kokoro import/G2P error: verify the current Kokoro Windows/espeak-ng installation; do not fall back to Edge automatically.
- Piper voice missing: run `python -m piper.download_voices --data-dir .local/models/piper <voice>` from `.venv-tts`.
- `ffmpeg is required`: install FFmpeg and expose it on PATH; original native WAV is preserved even when derivative conversion fails.
- sample-rate warning: the edit derivative must be mono PCM s16le at 48 kHz. Native Kokoro/Piper files remain at their model-native rate.
- clipping/silence warning: inspect the untouched native WAV first. QA never destructively normalizes the only copy.
- Pages says unavailable: `narration_web.json` has not been published for that episode; editorial production is still valid.
