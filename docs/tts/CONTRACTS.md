# Contracts

`config/tts/narration_manifest.schema.json` is the full local run contract. It records script identity, engine requested/used, voice, per-section source/spoken text hashes, native/edit files, exact cumulative timestamps, technical QA, generation time and RTF.

`config/tts/narration_web.schema.json` is deliberately smaller. It contains only information needed by Pages plus remote/light preview URLs. Pages does not need local filesystem paths or full text.

Audio filenames derive deterministically from semantic `section_key`: `00_opening.wav`, `01_beat-...wav`. Internal metadata, evidence IDs and Narrative Memory IDs remain metadata and are never synthesized.

Future SRT/VTT and Resolve Bridge must consume these contracts; they must not reverse-engineer filenames.
