# Pages

TTS observability lives inside the existing **Script** view, next to the semantic script map. No global Voice navigation item is needed yet.

Pages can consume two deliberately small contracts:

- `scripts/<episode>/tts/narration_web.json`: current narration status, master preview and per-section previews.
- `scripts/<episode>/tts/benchmark_web.json`: common bake-off text, measured technical metrics, manual perceptual fields and candidate preview URLs.

Without those contracts, the panel stays explicitly unavailable and never blocks the editorial pipeline. Every `<audio>` uses `preload="none"`; page load fetches metadata/HTML first and audio only when the user asks to play it.

## Promotion

Heavy audio remains outside Git history. Once preview MP3 files are hosted in a bounded GitHub-native store (recommended next adapter: a rolling GitHub Release), write only the small contracts:

```powershell
.\.venv\Scripts\python.exe -m pipeline.tts publish-web `
  --manifest .local\tts\<episode>\<run>\narration_manifest.json `
  --master-url <https-url> `
  --section-urls-json .local\tts\publish\section_urls.json

.\.venv\Scripts\python.exe -m pipeline.tts publish-benchmark `
  --benchmark .local\tts\benchmarks\latest\benchmark.json `
  --preview-urls-json .local\tts\publish\benchmark_urls.json `
  --script latest
```

The URL maps are local handoff files; they are not secrets and do not contain audio bytes.

## Retention

Keep at most three episode preview sets plus the latest bake-off. Local WAV/native/edit artifacts follow `config/tts.yaml` retention and remain under `.local/tts`. The release-uploader/garbage-collector adapter is intentionally separate from synthesis and is not implemented in this iteration.

The deployed Pages workflow already smoke-checks that the TTS panel exists on the live episode HTML. Actual playback acceptance requires at least one locally rendered and promoted preview asset.
