# Voice Bake-off

Fixture: `evals/tts/voice_bakeoff_es.txt`. It intentionally covers natural Spanish, OpenAI/NVIDIA/Gemini/Claude, AI/LLM/GPT-5/API, 127, 18.7 %, emotional emphasis, a fast sentence and an explanatory sentence.

`python -m pipeline.tts benchmark` renders the same fixture for configured candidates and records only measurable technical facts: generation seconds, output duration, real-time factor, file size, failures and audio format. Perceptual fields — naturalness, pronunciation, prosody, energy, clarity, pace and stability — are left `null` for human listening. No automatic "naturalness" score is treated as truth.

Initial matrix: Kokoro `ef_dora`, `em_alex`, `em_santa`; Piper `es_MX-claude-high`, `es_MX-ald-medium`; Edge benchmark voices `es-MX-DaliaMultilingualNeural`, `es-MX-JorgeNeural`. Reconfirm dynamic voice availability before a definitive bake-off.
