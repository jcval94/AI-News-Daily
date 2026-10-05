# Voice Bake-off

Fixture: `evals/tts/voice_bakeoff_es.txt`. It intentionally covers natural Spanish, OpenAI/NVIDIA/Gemini/Claude/GitHub, AI/IA/LLM/GPT-5/API, 127, 18.7 %, emotional emphasis, a fast sentence and an explanatory sentence.

`python -m pipeline.tts benchmark` renders the same fixture for configured candidates and records only measurable technical facts: generation seconds, output duration, real-time factor, file size, failures and audio format. Perceptual fields — naturalness, pronunciation, prosody, energy, clarity, pace and stability — are left `null` for human listening. No automatic "naturalness" score is treated as truth.

Initial matrix: Kokoro `ef_dora`, `em_alex`, `em_santa`; Piper `es_MX-claude-high`, `es_MX-ald-medium`; Edge benchmark voices `es-MX-DaliaNeural`, `es-MX-JorgeNeural`. Reconfirm dynamic voice availability before a definitive bake-off.

`benchmark` is local-only by default. Add `--include-edge` explicitly to call
the online challenger. Every run also writes `.local/tts/benchmarks/latest/index.html`
with lazy audio players for immediate local listening.


## Pages handoff

After listening assets are hosted, create a local JSON object whose keys are `engine::voice` and values are preview URLs, then run `python -m pipeline.tts publish-benchmark --preview-urls-json <file> --script latest`. The resulting `benchmark_web.json` is safe to commit: it contains the shared text, technical measurements, optional manual ratings and URLs, but no audio bytes.

The Script view renders these candidates side-by-side with `preload="none"`. Manual fields remain nullable until a human has listened; the UI labels them as pending rather than inventing a quality score.
