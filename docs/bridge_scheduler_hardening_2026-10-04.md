# Verified Drive consumption and bounded native wakeups

## Incident and scope

On 2026-10-04 the daily handoff was frozen at 08:36:40 America/Mexico_City,
created at 08:37:20 and verified in the inbox. The last visible daily scheduled
run started at 07:22:48 and correctly exited idle before the handoff existed.
At the 10:22 audit cutoff there were no later repository runs. All three Drive
bridges had a five-minute cron but visible scheduled runs were hours apart.
The internal scheduler cause remains unconfirmed; a valid payload cannot
explain the absence of a workflow run.

The 2026-10-03 successful consumption was triggered by a workflow-file push,
not schedule. It established consumer correctness for that input, not a cron
latency guarantee. The original 2026-10-04 Sheet is
`1l2_uM81KB8cCH4eo3sigI75fmLa5-623TYvufru2L-Q`, message
`ai-news-daily.news.2026-10-04.083640`, target
`news/2026-10-04-08-36-40.txt`.

Repair Watch had already created a second handoff at 10:35 before its pending
transport guard was added. Neither handoff is manually copied, rewritten or
deleted. The canonical daily validator still accepts at most one healthy digest
per day; subsequent valid day-level duplicates are acknowledged idempotently.

## Shared transport controls

`pipeline.gdrive_bridge_io` provides the same discovery and move logic to Daily,
Weekly and Narrative Memory:

- Follow `nextPageToken`, including empty intermediate pages; deduplicate IDs.
  Reject incomplete searches, repeated tokens, malformed responses and an
  exhausted page budget. An inspection error is never an empty queue.
- Use exact lane-specific Sheet title patterns. Daily retains its text/plain
  production-envelope compatibility, without selecting Weekly or Narrative.
- `workflow_dispatch.handoff_id` optionally selects that exact eligible inbox
  file. If it has already left the inbox, exit idle rather than select another
  file. Empty input preserves oldest-eligible-first polling.
- Before a move, read the same file's metadata and require its original name
  and sole inbox parent. PATCH only that file. Read its metadata again and require
  its sole destination parent and expected processed/failed name. HTTP success
  alone is insufficient. A repeat after an already verified move performs no
  second write. An ambiguous failed PATCH is not retried blindly in-process.

The existing lane validators and publication authority are unchanged. Daily
publication now retries main-write races at most three times, resetting to and
revalidating against fresh main before every attempt, staging only its digest.
Neither generation nor editorial recovery is performed by these modules.

## Existing watchdog as reconciliation entry point

The existing News Ingestion Watchdog retains its two daily schedules. No new
periodic workflow or scheduled ChatGPT task is added. Its new reconciliation job
can also wake after the three bridges, CI or Production Preflight finish on
main in this same repository. It always checks out trusted main and never
consumes upstream PR artifacts. The watchdog is excluded from its own upstream
list; workflow_run wakeups skip the unrelated incident-reporting health job.
Dated health checks dispatched by Daily retain their original behavior.

The reconciliation job uses Drive **read-only** scope plus GitHub Actions write
permission to call the existing consumer workflows. It lists the inbox and
handles at most one eligible file per lane per wake. It does not mutate Sheets,
move files, publish content, research, backfill or access an arbitrary repo
provided by the handoff. Repo comes from `GITHUB_REPOSITORY`; workflows come from
the fixed lane registry.

For every pending file it inspects the relevant main-branch runs:

- An active run younger than 20 minutes suppresses another wakeup. Older active
  runs do not block recovery forever; each consumer has a 10-minute timeout.
- A completed successful idle poll does **not** suppress pending work.
- Dispatches identified by the exact file ID in the consumer run title have a
  10-minute cooldown and a maximum of three observed attempts per handoff in the
  inspected history, across watchdog wakeups.
- Run inspection is paginated within a bounded window beginning at the earlier
  of file creation and the active grace cutoff. Incomplete inspection fails
  closed. A timeout during dispatch is ambiguous and is not immediately retried.
- A dispatch response retains run ID when returned, but is only `dispatched`.
  `drive-reconcile-report.json` explicitly sets `publication_verified=false`.
  Actual publication and final Drive parents require independent verification.

The report is summarized and preserved as a workflow artifact. Budget exhaustion
or inspection/dispatch failure makes reconciliation fail visibly. These limits
bound the reconciler's observed API dispatches; they do not disable the separate
consumer crons or prove delivery when GitHub's run listing itself is unavailable.

As of 2026-10-06, consumer crons are staggered away from minute zero and run
once per hour: Daily `2 * * * *`, Weekly `3 * * * *`, Narrative
`4 * * * *` (UTC). The hourly polls are a low-frequency safety net; the
existing reconciliation mesh can still request exact-file `workflow_dispatch`
wakeups from other native repository events. This reduces idle polling and queue
pressure without changing publication authority, validation, or idempotency.
It remains a scheduling mitigation, not evidence of a proven platform root cause
or a fixed-latency SLA.

## Producer and Repair Watch boundary

Daily research remains TODAY-only and GitHub read-only. The producer still ends
after exact Sheet readback and the verified move into the shared inbox.

The existing Repair Watch prompt now checks pending transport before researching
a missing canonical date. It checks both canonical GitHub output and the inbox,
using complete discovery and the existing Sheet contract. A single valid pending
handoff yields `pending_transport` and its existing identifiers. Contradictory
candidates or incomplete inspection yield `pending_conflict`/`check_failed`.
None of those states creates a replacement Sheet. Its TODAY→YESTERDAY scope,
10:30 America/Mexico_City schedule, and other producers/tasks remain unchanged.

## Verification and extension

Required local checks are compileall, the complete unit suite and YAML/shell
syntax checks. Regression coverage includes page-two discovery, cross-lane
isolation, duplicate wakeups, exact-file targeting, failed move readback, HTTP
success without the expected parent, missing inspection, stale-active grace,
per-file cooldown/attempt budget and timeout without blind retry.

After deployment, verify the original 2026-10-04 file in main, the canonical day
health, the same Sheet's processed parent, the bridge step results, subsequent
health/Pages results, and the Narrative handoff independently. Preserve live run
IDs and commit evidence in this document; never substitute a green idle run for
that evidence. Weekly still needs its own real accepted-payload E2E.

The modules are reusable across the three lanes; their schemas and canonical
output checks remain distinct. Repair Watch reuses the queue/outcome distinction.
FLOOR keeps its existing GitHub-native market-session architecture and is not
modified by this change. CV fit is excluded.

## Remaining availability limit

The native recovery mesh reduces dependency on one workflow's cron. It cannot
guarantee a fixed publication latency if **all** GitHub Actions wakeups stop.
GitHub also limits workflow_run chain depth, so this mesh is not an unbounded
queue-draining loop. Consumer polling and subsequent independent wakes remain
necessary for larger queues.

An independent Drive event relay remains a separate, undeployed integration.
The consumers' exact-file workflow_dispatch interface is ready for it, but the
relay requires a deployed receiver, an authorized Drive identity, durable cursor/
outbox state, an Actions-write GitHub identity, channel renewal and a result
monitor. Those credentials/infrastructure were not supplied and are not extracted
from GitHub secrets. No external relay, Apps Script, second publishing authority
or new periodic producer is claimed to exist. Before promising an SLA, test
loss/duplication of events, ambiguous dispatches, channel expiry, queue growth,
canonical outcomes and final parents for each lane.

References:
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
- https://developers.google.com/workspace/drive/api/guides/push


## Observed production acceptance — 2026-10-04

The fix was merged in PR #87 (`b214b6242e608d5a9760ee71168af4a65510dfbc`).
Its Linux and Windows deterministic CI passed in run `37219868347`.
The real handoffs below were consumed automatically; no new producer Sheet or
replacement payload was created by this maintenance work.

| Evidence | Observed outcome |
| --- | --- |
| Original daily Sheet `1l2_uM81KB8cCH4eo3sigI75fmLa5-623TYvufru2L-Q` | Run `37219986795` published `news/2026-10-04-08-36-40.txt`; its content equals the frozen original after the validator's canonical trailing-newline normalization. Fresh Drive metadata showed the same ID with the sole processed parent `1o-2WPz514dFJDg7seGz2dZ4X87doPkdK`. |
| Canonical daily health | Artifact from run `37220059001` reports `healthy=true`, `candidate_count=1`, `item_count=5`, selected original file. |
| Narrative Sheet `112p6Wl7mwQn2TNQgMRxoKGCqm2mWdrAr8PrJBXkcCPM` | Run `37219986731` accepted four new IDs (Apollo 11 scheduling, ARPANET packet storm, Braess and Jevons); all four were independently found in canonical memory, now 13 rows. Same Sheet's sole processed parent was verified. |
| Pre-existing Repair Watch duplicate `1Ud3QXnho5Yj97MYH4FQivMzsWCGT6CoTKqKRumYkzU8` | Reconcile report from run `37220011727` dispatched exact ID to run `37220041876`. Consumer validation succeeded, commit was skipped because the original day already existed, and the same Sheet's processed parent was verified. Canonical discovery still found exactly one daily file. |

The original freeze was 08:36:40 America/Mexico_City; the Sheet reached the inbox
at 08:37:35.619. Merge-triggered consumers started at 11:18:11 and subsequently
completed publication. These timestamps demonstrate this incident's resolution,
not a five-minute polling SLA. GitHub's internal cause for absent earlier cron
wakeups remains unproven; the deployment does not claim that the platform
scheduler was repaired.

### Downstream test dependency discovered during acceptance

Editorial Review Hub run `37220108507` failed its deterministic contract gate
before deployment. Two failure-path tests selected a fixed memory ID from the
live library; today's four accepted rows changed the ranked retrieval set and
excluded that ID. This was a test-input isolation defect, not invalid newly
accepted memory. The fix gives those three failure-path tests an explicit,
versioned one-record fixture and temporary editorial profiles. Production ranking,
selection validation, memory content and the contract gate remain unchanged.
The Hub push paths include the tests and fixture so this repair receives a fresh
end-to-end build/deploy, rather than rerunning an obsolete source snapshot.

Weekly's real accepted-payload publication E2E is still pending. The common
pagination/routing/move/dispatch and race behavior is covered deterministically;
that coverage must not be presented as a live Weekly delivery demonstration.


### Pages cancellation boundary

PR #89 (`b00b07704cd37cea5e709b00537c8b01c642a860`) restored the isolated
failure-path tests; Linux and Windows CI passed in run `37220822825` and main CI
passed in `37220940514`. A subsequent live check exposed a second coupling:
reconciliation-only Watchdog completions woke Review Hub and canceled an active
push build (`37220940494`). At normal three-lane polling frequency this could
starve publication even when consumers and validators are healthy.

Review Hub therefore skips its build for Watchdog completions whose originating
event is itself `workflow_run` (the reconciliation-only branch). Those no-op
runs receive a unique concurrency group, so skipping a job cannot still cancel
a genuine build at workflow admission. Canonical Daily/Narrative pushes and
normal scheduled or explicitly dispatched Watchdog health checks retain the
shared main build/deploy group and their existing publication behavior. Regression
cases evaluate the actual YAML condition and group across both event families;
no-op runs must neither build nor contend with real Pages publication.


Review Hub subsequently completed run `37221046231` successfully on #89 main
SHA `b00b07704cd37cea5e709b00537c8b01c642a860`: build job `111491325061`
and Pages deploy job `111491906517` both passed. This verifies restoration of
the downstream deterministic gate and deployment on the corrected memory fixture.
The cancellation boundary above is an additional prevention for frequent idle
consumer wakes; it does not change content generation or deployment permissions.

No-op completions use the distinct display name `Drive reconciliation acknowledged
(no Pages build)`; genuine publication retains `Editorial Review Hub`. This keeps
repository health's latest-run view from mistaking a successful skipped workflow
for a successful deployment. A failed real Hub run must remain visible even when
a newer reconciliation acknowledgement is green.
