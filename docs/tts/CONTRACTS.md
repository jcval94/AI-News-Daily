# Contracts

`config/tts/narration_manifest.schema.json` is the full local run contract. It records script identity, engine requested/used, voice, per-section source/spoken text hashes, native/edit files, technical QA, generation time and RTF.

Manifest schema `1.1` makes editorial pauses explicit instead of hiding them inside audio:

- `start_seconds`: start of spoken audio on the master timeline;
- `end_seconds`: end of spoken audio;
- `duration_seconds`: spoken duration only;
- `pause_after_seconds`: intentional semantic silence after that section;
- `timeline_end_seconds`: end of the section plus its following pause.

The next section must start at the previous `timeline_end_seconds`. The rendered master physically contains the same silence, so future Resolve/SRT/VTT consumers can trust the manifest without reverse-engineering waveform gaps.

Schema `1.0` manifests remain readable as a backward-compatible zero-pause contract.

`config/tts/narration_web.schema.json` is deliberately smaller. It contains only information needed by Pages plus remote/light preview URLs. Pages does not need local filesystem paths or full text.

Audio filenames derive deterministically from semantic `section_key`: `00_opening.wav`, `01_beat-...wav`. Internal metadata, evidence IDs and Narrative Memory IDs remain metadata and are never synthesized.

Future SRT/VTT and Resolve Bridge must consume these contracts; they must not reverse-engineer filenames or infer pauses from audio.
