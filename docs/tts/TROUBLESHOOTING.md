# Troubleshooting

- `TTS runtime not found`: create `.venv-tts` as documented in `WINDOWS_SETUP.md`.
- Conda prefix exists but doctor still says runtime missing: a Conda environment
  has `.venv-tts/python.exe`, not the committed `.venv-tts/Scripts/python.exe`.
  Use the Conda interpreter to create a standard venv as documented above.
- Kokoro import/G2P error: verify the current Kokoro Windows/espeak-ng installation; do not fall back to Edge automatically.
- Kokoro `UnicodeDecodeError` on Windows: run it through `pipeline.local`; the
  harness forces UTF-8 for engine subprocesses so the host code page cannot
  corrupt the narration text.
- A cold Kokoro/Torch import can take tens of seconds on Windows. The doctor
  allows 90 seconds for engine imports; a timeout beyond that remains blocking.
- Piper voice missing: run `python -m piper.download_voices --data-dir .local/models/piper <voice>` from `.venv-tts`.
- `ffmpeg is required`: install FFmpeg and expose it on PATH; original native WAV is preserved even when derivative conversion fails.
- sample-rate warning: the edit derivative must be mono PCM s16le at 48 kHz. Native Kokoro/Piper files remain at their model-native rate.
- clipping/silence warning: inspect the untouched native WAV first. QA never destructively normalizes the only copy.
- Pages says unavailable: `narration_web.json` has not been published for that episode; editorial production is still valid.
- `gh auth status` reports an invalid token: synthesis remains available, but
  Release promotion and PR creation require `gh auth login -h github.com`.
