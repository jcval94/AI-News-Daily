# Pages

TTS observability lives inside the existing **Script** view, next to the semantic script map. No global Voice navigation item is needed yet.

Pages consumes two deliberately small contracts:

- `scripts/<episode>/tts/narration_web.json`: current narration status, master preview and per-section previews.
- `scripts/<episode>/tts/benchmark_web.json`: common bake-off text, measured technical metrics, manual perceptual fields and candidate preview URLs.

Without those contracts, the panel stays explicitly unavailable and never blocks the editorial pipeline. Every `<audio>` uses `preload="none"`; page load fetches metadata/HTML first and audio only when the user asks to play it.

## Promotion

Heavy audio remains outside Git history.

The local harness now provides the complete promotion adapter:

```powershell
.\.venv\Scripts\python.exe -m pipeline.local tts promote --script latest
```

It:

1. resolves the latest local narration manifest for the selected episode;
2. uploads the master MP3 and per-section MP3 previews to a GitHub Release;
3. creates a lightweight `narration_web.json`;
4. deletes superseded `tts-preview-*` releases beyond the configured retention bound.

The current default is three narration preview releases.

The high-quality native/edit WAV files stay local.

The bake-off uses a single rolling bounded release:

```powershell
.\.venv\Scripts\python.exe -m pipeline.local tts promote-benchmark --script latest
```

To push only the small contract to the configured branch and let the normal Pages workflow pick it up, add:

```powershell
--push-contract
```

For example:

```powershell
.\.venv\Scripts\python.exe -m pipeline.local tts promote --script latest --push-contract
```

The GitHub Release URLs are then the only remote audio references stored in the Pages contract.

## Retention

`config/tts.yaml` owns the retention and release policy.

Default behavior:

- local high-quality runs remain under `.local/tts`;
- only three narration preview releases are retained;
- the voice bake-off reuses `tts-benchmark-latest`;
- no WAV or MP3 bytes are committed to Git;
- Pages receives metadata and URLs only.

The deployed Pages workflow already smoke-checks that the TTS panel exists on the live episode HTML. Actual playback acceptance still requires a physical local render and promotion, because CI intentionally does not download or run the heavy speech models.
