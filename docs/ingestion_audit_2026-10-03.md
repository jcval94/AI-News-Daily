# AI News ingestion audit — 2026-10-03

Baseline: `6772215564d3ce9eea4cb4eabd2e3210459335ec` (main).

## Verified state

| Target | Canonical result | Incident |
| --- | --- | --- |
| 2026-09-29 | Missing; no recoverable dated daily handoff found in Drive | #79 remains a real data gap |
| 2026-09-30 | `news/2026-09-30-18-54-17.txt`, 5 parseable items | #81 is stale |
| 2026-10-01 | `news/2026-10-01-18-44-43.txt`, 5 parseable items | Published by Drive bridge |
| 2026-10-02 | `news/2026-10-02-12-20-07.txt`, 7 parseable items | Published by Drive bridge |
| 2026-10-03 | Verified A1:B8 handoff in shared inbox, Sheet `19ebZfXs62XmC_HLMhdhkmSicr4Q9VyG7N3dB_HHiIJ8`; not yet canonical at audit baseline | Queued, not claimed as published |

Production target 2026-10-02 expects September 29–October 1. September 30 and
October 1 are present, so coverage is 2/3 (66.7%), below 0.75. #83 therefore
remains valid. October 2's daily digest belongs to the next Tuesday window and
cannot replace September 29 in this window.

The active external tasks are separate: **AI News Daily** at 08:30 and
**AI News Repair Watch** at 10:30, America/Mexico_City. The daily task handles
TODAY only; Repair Watch handles TODAY then YESTERDAY independently. Both use
one native Sheet per missing target, exact readback, and a verified move to the
shared inbox. Their current prompts preserve GitHub as read-only. On October 3
neither automatic lane may reconstruct September 29. No duplicate scheduler or
automatic historical backfill was introduced.

## Evidence and diagnosis

- [#79](https://github.com/jcval94/AI-News-Daily/issues/79),
  [#81](https://github.com/jcval94/AI-News-Daily/issues/81),
  [#83](https://github.com/jcval94/AI-News-Daily/issues/83).
- [Preflight 36953934582](https://github.com/jcval94/AI-News-Daily/actions/runs/36953934582)
  failed for source coverage; the model probe passed.
- [Bridge 37123468105](https://github.com/jcval94/AI-News-Daily/actions/runs/37123468105)
  passed but was idle; conversion, validation, and publication were skipped.
  A green idle run is not evidence that a particular digest was published.
- The legacy issue staging workflow only listens for `AI_NEWS_STAGING` issues
  authored by the repository owner. Its September 30 run `36672600668` was
  skipped, not a failed digest validator. The active producer now ends in Drive;
  it does not create staging issues. Staging edits/reopens previously could not
  retry the same issue despite the failure message suggesting a retry.
- Both ingest lanes commit using `GITHUB_TOKEN`. GitHub suppresses downstream
  `push` workflows for those commits. This left ingestion incidents stale and
  prevented immediate preflight/Pages refresh. The existing scheduled checks
  only recheck their current date/next target, so historical incidents can remain
  open after successful recovery.
- [Build 37055421164](https://github.com/jcval94/AI-News-Daily/actions/runs/37055421164)
  failed first at a deterministic test (`test_repo_health`, info vs warn), before
  source coverage or model calls. Its subsequent report failed with an empty
  `NEWS_LOOKBACK_DAYS`; artifact upload then attempted `/` and failed at
  `/boot/efi`. Current main's suite already passes that original test; the patch
  prevents these secondary failures when workspace initialization was skipped.
- [Review Hub 37078786873](https://github.com/jcval94/AI-News-Daily/actions/runs/37078786873)
  built and deployed Pages successfully, including its deployed catalog/episode
  smoke check. Pages publication itself is not the missing-source root cause;
  deployment does not prove the October 2 episode was generated.

## Minimal correction

1. After a confirmed publication/idempotent result, dispatch the existing
   watchdog for the **digest's date**. It can close that date's recovered incident.
2. Dispatch the existing preflight for the first scheduled Tuesday/Friday
   strictly after the digest date, only once the window's last source day has
   arrived. This supports historical verification without false future-day gaps.
3. Reuse the existing Review Hub `workflow_run` triggers from watchdog/preflight
   for Pages refresh. Idle bridge runs dispatch nothing; no new periodic job or
   episode/model-generation workflow was added.
4. A failed follow-up dispatch leaves the Drive Sheet in the inbox. Retrying is
   idempotent against the healthy canonical digest and does not regenerate news.
5. Serialize the two daily publication lanes and check a parseable >=5-item
   digest on fresh `origin/main` before declaring a duplicate race. Thin/invalid
   filenames are not treated as healthy recovery. Existing files are preserved.
6. Allow owner-authored open staging issues to retry on edits/reopens. Automatic
   date limits remain TODAY/YESTERDAY. Guard run reporting/artifacts when the
   production workspace was never initialized.

GitHub's token behavior is documented at:
https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow

## Validation and remaining data work

`python -m compileall app pipeline` and the complete deterministic suite passed:
**471 tests**. New regressions cover dated follow-ups, pending future windows,
missing/thin sources, dispatch failure, idle gating, and recovery from a thin
existing candidate. Workflow YAML and embedded shell/Python are also checked.

September 29 still requires an explicitly scoped historical content backfill
with real dated sources and the same editorial/dedup validator. It must not be
replaced by an empty marker, another day's digest, a relaxed coverage threshold,
or expanded automatic Repair Watch responsibilities. Keep #79/#83 open until
the source gap is actually filled and the original target passes preflight.
