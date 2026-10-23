# Shared multisource acquisition

This change follows the source audit merged in PR #97. Production used mode `off`; Pages rebuilt review media on a separate path, and only exact documentary slots could consume the pool. Baseline video came exclusively from Pexels.

## Behavior

- Production and backfill use the same bounded pool, only after script approval.
- Pages first reuses validated canonical media. A reconstruction runs inside `.pipeline-runs/<date>/review-<run>/`, keeps the original approval state, and is explicitly labeled review-only.
- Context slots may use catalogued contextual material. Named people and historical evidence retain exact-match requirements. Context never resolves a critical exact cue.
- Selection gives underrepresented eligible providers priority within a usable resolution tier. Unusable rights or unrelated media never qualify to meet a source target.
- The five initial targets are Pexels, Wikimedia Commons, Internet Archive, PeerTube and NASA. Museum/Openverse routes remain additional candidates. Wikipedia discovery of Commons files counts as Commons.
- Short video preference, source/output byte limits and transcript-off remain in force. Unknown or incompatible licenses are rejected.
- Catalogue GETs have bounded retries, Retry-After handling, host pacing, a circuit after denial/repeated failures, and a 24-hour cache. Credentials and model requests never enter this cache.
- The image fallback tries the next ranked provider after a failed download before creating local media.
- Pages reports found, downloaded, eligible and assigned counts. Only assigned external files count toward five-source coverage; zero-result providers include reasons.
- Review bundle caching uses input/state/code fingerprints plus per-file hashes and physical/license validation. A cached review bundle cannot enter canonical reuse.

## NASA and PeerTube

NASA's official [media usage guidance](https://www.nasa.gov/nasa-brand-center/images-and-media/) permits factual editorial use with attribution, excluding third-party copyrighted material and endorsement. The adapter requires a known government centre and rejects third-party/copyright markers or external creator credits; JPL/Caltech and unknown centres remain ineligible. It records the catalogue metadata and policy URL. This is a restricted editorial-use label, not a blanket public-domain conversion.

PeerTube index records may omit the license. The adapter checks the selected public video's authoritative metadata and download-enabled flag before download, and checks the returned license again before assignment.

## Activation and rollback

The workflow default is `integrated`. Repository variable `MEDIA_RETRIEVAL_MODE=off` restores the prior acquisition path for scheduled production, backfill and Pages. Manual production input takes precedence. `shadow` acquires a comparison pool without changing selected assets. Pages also provides an explicit refresh input; ordinary rebuilds reuse valid canonical/cache media.

No new paid API or secret. Retrieval reuses the existing model configuration with a 32-call, 600-second, 128-MiB, 24-asset cap. There is no automatic ASR.

## Validation

`Multisource Media Validation` runs deterministic contracts, five independent live connectivity/rights/decoder controls, the twelve historical cases for both image and video, and a real portable editing handoff. It retains negative results. Workflow completion alone is not success at finding an exact referent.

Results and rollout status are recorded separately after the run. Do not infer five-source success from the configured target list. Production activation must be reviewed against the run evidence before merge.
