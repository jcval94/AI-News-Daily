# Multimedia source audit — 2026-10-16 (America/Mexico_City)

Baseline: `main` at `6bc0941a122b4efbfd198b79ac6b1d07d75fbb10`.
Read-only observation captured on 2026-10-17 UTC. Counts describe the **published review packages**, not canonical production multimedia. These mutable URLs may change on a later Pages build.

## Finding

The impression is partly correct: recent packages are dominated by Pexels, with few Wikimedia files and no assigned documentary-pool assets. They do contain external media: Pexels is itself external. Local fallback cards must not be counted as external downloads.

| Episode | Pexels | Wikimedia Commons | Local fallback | Total | Recorded pool assets | Rows with Wikimedia HTTP 429 |
|---|---:|---:|---:|---:|---:|---:|
| 2026-10-16 | 43 | 0 | 11 | 54 | 0 | 15 |
| 2026-10-09 | 41 | 1 | 12 | 54 | 0 | 12 |
| 2026-10-06 | 46 | 3 | 5 | 54 | 0 | 8 |
| 2026-09-25 (approved baseline) | 45 | 1 | 7 | 53 | 0 | — |

The three October packages contain 130 Pexels files, 4 Wikimedia files and 28 local cards. All 69 videos are from Pexels. The 429 counts are rows whose persisted `errors` mention Wikimedia rate limiting, **not** counts of all network attempts. 8, 7 and 3 of the local cards respectively have such an error; this does not establish that every fallback has the same cause.

Evidence: [Oct 16 manifest](https://jcval94.github.io/AI-News-Daily/episodes/2026-10-16/artifacts/media-manifest.json), [Oct 9 manifest](https://jcval94.github.io/AI-News-Daily/episodes/2026-10-09/artifacts/media-manifest.json), [Oct 6 manifest](https://jcval94.github.io/AI-News-Daily/episodes/2026-10-06/artifacts/media-manifest.json), [Sep 25 manifest](https://jcval94.github.io/AI-News-Daily/episodes/2026-09-25/artifacts/media-manifest.json).

## Why

1. **Editorial gate:** all three recent production runs persisted `script_not_approved`. Their Actions job succeeded as a controlled editorial outcome, but `Build canonical dense multimedia package` was skipped. Changing a retrieval flag would not bypass this gate.
   - [Oct 16 run 38947788782](https://github.com/jcval94/AI-News-Daily/actions/runs/38947788782), job `117131218281`.
   - [Oct 9 run 37983192414](https://github.com/jcval94/AI-News-Daily/actions/runs/37983192414), job `113998565327`.
   - [Oct 6 episode / run 37640109839](https://github.com/jcval94/AI-News-Daily/actions/runs/37640109839), job `112856487875` (executed Oct 7).
2. **Documentary retrieval remains opt-in:** all three production logs show `MEDIA_RETRIEVAL_MODE: off`. `.github/workflows/build-video-kit.yml` defaults manual and scheduled executions to `off`; `pipeline.media_pool.prepare_pool` immediately returns in this mode. Archive, NASA, PeerTube and the other documentary adapters are not automatically part of ordinary acquisition.
3. **Pages has a separate review path:** `.github/workflows/editorial-review-hub.yml` may construct review multimedia for an unapproved script. Its acquisition environment does not enable the pool. `pipeline.review_media_reuse` requires approved, validated media before reuse; otherwise Pages builds review media. A visible Pages library is not evidence of canonical production.
4. **Baseline providers are narrow:** `pipeline.media.download_video_shot_asset` uses Pexels; `download_shot_asset` queries Pexels and Wikimedia, selects a candidate by relevance, and can generate a local fallback on failure. It does not fan out over the documentary providers. Wikimedia search/download HTTP 429 errors are present in the published metadata. This is evidence of rate limiting, not proof that Wikimedia is permanently inaccessible from Actions.

## PR scope

- Keep raw `provider` and `source_url`; add deterministic `source_origin` to new download manifests, reused bundle copies and exported Pages manifests.
- `source_origin` v1 records normalized `provider`, display `label`, `kind` (`external`, `local`, `unknown`), acquisition path, and labeling basis. It does not attest semantic relevance, rights or production approval.
- Replace the inconspicuous source select with one-click provider buttons and external/local/unknown buttons. Each card carries a visible badge and machine-readable `data-origin-*` tags. Existing type, license, relationship and text filters intersect with them.
- Upgrade recovered historical episode HTML and its exported manifest without downloading media or calling a model. Never change canonical episode metadata during history recovery.
- Preserve approval gates, retrieval defaults and budgets. No new API or paid service is introduced. This PR diagnoses and labels the current behavior; it does not claim to solve rate limiting or activate documentary retrieval.

## Follow-up for acquisition

For an **approved** isolated episode, use `media_retrieval_mode=integrated` and verify assigned pool assets and unresolved needs. A permanent scheduled rollout needs an explicit bounded configuration decision. Separately, Wikimedia needs an experiment with pacing/cache and retrying an alternate valid candidate after download failure; success should be measured by exact subject matches, not merely provider diversity. Neither a disabled pool nor rejected scripts can be fixed by changing the Pages filter.

## Validation

Python compilation and **540 repository tests passed**; focused source normalization, unknown provenance, escaped metadata, file-identity mapping and idempotent history recovery tests. Interactive DOM replay uses the three published October packages to check provider/kind/type intersections, reset, text search, empty results and counts without new downloads. All three DOM replays passed with the expected 54 resources and no JavaScript execution errors. No new acquisition or live deployment was triggered for this PR.
