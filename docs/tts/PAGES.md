# Pages

TTS observability is intentionally inside the existing **Script** view, next to the semantic script map. Adding a global Voice navigation item would be unnecessary at this stage.

Pages reads `scripts/<episode>/tts/narration_web.json` when it exists. Without it, the panel clearly says TTS is unavailable and remains non-blocking. With it, the panel shows engine, voice, total duration, section count, QA status, full preview and section previews. Every `<audio>` uses `preload="none"`; metadata renders without fetching audio.

Audio must not be committed to Git. The publish phase will upload bounded web derivatives as GitHub Release assets (or an equivalently bounded GitHub-native asset store) and commit only the small web contract. Keep at most three episode audio sets plus the latest bake-off; delete superseded web assets. Local high-quality WAV remains under `.local/tts`.
