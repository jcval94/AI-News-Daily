# Engines — evidence checked 2026-09-28

## Kokoro

Primary candidate. Official `hexgrad/kokoro` package is 0.9.4, Python >=3.10,<3.14, Apache-2.0; official usage emits 24 kHz audio. `hexgrad/Kokoro-82M` is ~363 MB total with a 327 MB main weight and Apache-2.0 metadata. Official voice documentation lists Spanish `lang_code=e`, espeak-ng `es`, with `ef_dora`, `em_alex`, `em_santa`. The same documentation warns non-English support can be thinner, so Spanish quality remains an experiment rather than an assumption.

Sources: https://github.com/hexgrad/kokoro ; https://huggingface.co/hexgrad/Kokoro-82M ; https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md

## Piper

Local fallback. The old `rhasspy/piper` repository was archived 2025-10-06 and points to `OHF-Voice/piper1-gpl`. Current `piper-tts` identifies as fast/local and is GPL-3.0-or-later. Voice docs include `es_MX`. `es_MX-claude-high` is 22,050 Hz, ~63 MB, and its model card cites an Apache-2.0 dataset; `es_MX-ald-medium` is 22,050 Hz, ~63 MB and cites an Unlicense dataset. Voice/model provenance must be reviewed per voice; repository-level metadata is not sufficient.

Sources: https://github.com/OHF-Voice/piper1-gpl ; https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_MX

## Edge-TTS

Benchmark only. `edge-tts` 7.2.8 uses Microsoft Edge's **online** TTS service without an API key and is LGPLv3. It therefore violates the primary local-first requirement and can change when the upstream service changes. Voice discovery should use `edge-tts --list-voices`; current Microsoft documentation includes multiple `es-MX` neural voices.

Sources: https://github.com/rany2/edge-tts ; https://pypi.org/project/edge-tts/ ; https://learn.microsoft.com/azure/ai-services/speech-service/language-support
