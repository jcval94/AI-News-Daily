# Scheduled ChatGPT → Google Drive → GitHub publication architecture

This document is the source of truth for scheduled ChatGPT tasks that research or generate candidate content and then hand publication authority to GitHub Actions through Google Drive.

It complements the lane-specific contracts:

- Daily news: `docs/news_ingestion_drive_bridge.md`
- Narrative Memory: `docs/narrative_memory_contract.md`
- Weekly Applied GenAI research: `research/README.md`

## Core principle

The architecture separates two kinds of work:

```text
probabilistic work                         deterministic authority
──────────────────────────────────────    ──────────────────────────────────────
research                                  validate transport
source selection                          validate schema/contracts
editorial synthesis                       re-read latest main
candidate generation                      detect duplicates/races
self-check                                decide whether mutation is allowed
prepare handoff                           commit canonical repository artifacts
```

ChatGPT may propose content. GitHub decides whether that content is allowed to become canonical repository state.

A successful task-side handoff means **queued in Drive**, never "published".

## Common production route

```text
ChatGPT scheduled task
    │
    │ research / select / write / self-check
    ▼
native Google Sheet
    │ exact A1:B8 contract
    │ task performs readback
    ▼
shared Drive inbox
    │
    │ GitHub service account reads via Drive API
    ▼
lane-specific GitHub Actions bridge
    │ export Sheet as CSV
    │ reconstruct internal hash-verified envelope
    ▼
lane-specific deterministic Python validator
    │
    │ re-read latest main
    │ enforce contract / history / dedup / race rules
    ▼
canonical repository mutation
    │
    ├── success or idempotent ──► Drive processed/
    └── invalid / rejected     ──► Drive failed/
```

Apps Script and GitHub Issues are **not required in the production route**.

## Shared A1:B8 handoff contract

Every production lane uses exactly eight key/value rows on the first sheet.

| Row | Column A | Column B |
| --- | --- | --- |
| 1 | `format` | `bridge-sheet-v1` |
| 2 | `message_id` | lane-specific durable message ID |
| 3 | `namespace` | `AI-News-Daily` |
| 4 | `target_repo` | `jcval94/AI-News-Daily` |
| 5 | `target_path` | lane-specific canonical target |
| 6 | `content_type` | `text/plain` or `application/json` |
| 7 | `status` | `ready` |
| 8 | `payload` | complete candidate content |

The task must:

1. freeze the candidate payload and identifiers, create exactly one Sheet per target per execution, and immediately retain its ID;
2. read metadata to resolve the first tab and its real numeric sheetId; write A1:B8 with exactly one structured updateCells request, a precise userEnteredValue field mask, and stringValue for all 16 cells;
3. read back the resolved tab's A1:B8 using unformatted values;
4. verify all eight keys and values;
5. verify that the full multiline payload survived intact;
6. move the same Sheet into the shared inbox;
7. verify the inbox parent;
8. stop; after any write/readback failure, retain the Sheet ID, report the failed phase, do not enqueue or create a replacement Sheet within that execution.

On 2026-10-03, the saved prompts for **GenAI Applied Weekly**, **Narrative Memory Builder** and **AI News Repair Watch** were updated and read back exactly. Schedules, enabled states and all other tasks (including CV_fit) were preserved.

| Task | Configuration verified | Execution evidence |
| --- | --- | --- |
| AI News Daily | Existing hardened contract | Real 2026-10-03 Sheet → inbox → main → processed → Pages proof |
| GenAI Applied Weekly | Frozen canonical JSON, pre-transport validation, real sheetId, one structured updateCells, exact readback, same-file move, no replacement/retry after failure | New prompt has not yet completed a lane-specific real handoff in this audit |
| Narrative Memory Builder | Same transport protections; zero-approved stop, JSONL gates, semantic dedup and append-only preserved | New prompt has not yet completed a lane-specific real handoff in this audit |
| AI News Repair Watch | Freeze before canonical-header validation; explicit metadata/write/read/move failure handling and sole-parent checks; independent TODAY/YESTERDAY processing preserved | Revised recovery path has not yet been exercised with a missing target in this audit |

Prompt readback proves configuration adoption, not end-to-end execution. No synthetic production handoffs were created for this update. See [the daily verified baseline and applicability audit](daily_bridge_verified_2026-10-03.md).

It must not export the Sheet, create repository files, create commits, create production GitHub staging issues, or claim publication.

## Current production lanes

### 1. Daily AI News

Task: **AI News Daily**

Sheet name must match the complete daily form:

```text
^__bridge_inbox_AI-News-Daily__\d{4}-\d{2}-\d{2}_\d{6}$
```

Do not use only a startswith match: it also matches the weekly and Narrative Memory lanes.

Message ID:

```text
ai-news-daily.news.YYYY-MM-DD.HHMMSS
```

Target:

```text
news/YYYY-MM-DD-HH-MM-SS.txt
```

Workflow:

```text
.github/workflows/gdrive-raw-bridge-probe.yml
Google Drive AI News Bridge
```

Validator chain:

```text
pipeline.gdrive_news_bridge
    ↓
pipeline.staged_news_issue
```

Special rules:

- the normal producer handles TODAY only;
- a separate Repair Watch checks TODAY then YESTERDAY, only if missing; never automatic older backfill;
- 5–10 parseable stories;
- editorial depth and allowed categories;
- recent semantic deduplication;
- one canonical digest per target day;
- race-safe publication.

The workflow filename contains the historical word `probe`; the workflow itself is production.

### 2. Narrative Memory

Task: **Narrative Memory Builder**

Sheet prefix:

```text
__bridge_inbox_AI-News-Daily__narrative-memory__
```

Message ID:

```text
ai-news-daily.narrative-memory.YYYY-MM-DD.HHMMSS
```

Target:

```text
editorial/narrative_memory.jsonl
```

Workflow:

```text
.github/workflows/gdrive-narrative-memory-bridge.yml
Google Drive Narrative Memory Bridge
```

Validator chain:

```text
pipeline.gdrive_narrative_memory_bridge
    ↓
pipeline.staged_narrative_memory_issue
    ↓
pipeline.narrative_memory
```

Special rules:

- payload begins with the canonical Narrative Memory staging header;
- 1–4 raw JSONL records;
- append-only canonical store;
- gate thresholds remain authoritative;
- ID conflicts and semantic duplicates fail closed;
- latest `main` is re-read before append;
- push races are retried.

The historical issue-based staging workflow may remain for compatibility, but scheduled production uses Drive.

### 3. Weekly Applied GenAI research

Task: **GenAI Applied Weekly**

Sheet prefix:

```text
__bridge_inbox_AI-News-Daily__research-weekly__
```

Message ID:

```text
ai-news-daily.research-weekly.YYYY-MM-DD.HHMMSS
```

Target:

```text
research/weekly/YYYY-MM-DD.json
```

Workflow:

```text
.github/workflows/gdrive-weekly-research-bridge.yml
Google Drive Weekly Research Bridge
```

Validator / renderer:

```text
pipeline.gdrive_weekly_research_bridge
```

Special rules:

- ChatGPT transports only canonical JSON;
- `research/weekly_digest.schema.json` is authoritative;
- historical IDs must preserve `new_publication` / `material_update` semantics;
- GitHub derives Markdown deterministically from accepted JSON;
- exactly the JSON + Markdown sibling pair may be staged;
- `Weekly Applied GenAI Research Contract` remains an independent post-publication watchdog.

## Internal envelope

GitHub converts an accepted Sheet into this internal transport representation:

```text
format=base64-payload-v1
schema_version=1.0
message_id=...
target_repo=jcval94/AI-News-Daily
target_path=...
content_type=...
sha256=...
payload_b64=...
```

The SHA-256 is calculated on the GitHub side after Drive export.

`pipeline/gdrive_envelope.py` contains the shared envelope parser and payload-integrity verification used by the migrated lanes.

Lane-specific validators remain responsible for semantic meaning and canonical mutation.

## Why Drive CSV export is the read path

GitHub Actions reads native Sheets using the Google Drive export endpoint with `text/csv`.

This is intentional:

- the service account already has stable Drive access;
- it avoids depending on a separate Sheets API permission boundary;
- CSV preserves the two-column A1:B8 contract, including quoted multiline payloads;
- the workflow still verifies exact row count, column count, key order, metadata and payload.

Do not switch a lane to direct Sheets API reads without an end-to-end service-account test.

## Drive lifecycle

The shared logical structure is:

```text
ChatGPT-GitHub-Bridge/
└── AI-News-Daily/
    ├── inbox/
    ├── processed/
    └── failed/
```

The producer moves a verified Sheet into `inbox/`.

GitHub owns the transition out of `inbox/`.

### processed

A handoff goes to `processed/` when:

- publication succeeded;
- the canonical state was already identical / already present;
- a safe race outcome made a second publication unnecessary.

The file is renamed with a `processed__` prefix.

### failed

A handoff goes to `failed/` when deterministic validation rejects it.

The file is renamed with a `failed__` prefix.

A failed handoff should be inspected before regenerating content. Repeated regeneration without understanding a deterministic rejection creates noise and can hide contract regressions.

## Publication invariants

These rules apply to every lane:

1. ChatGPT never writes canonical repository artifacts directly.
2. GitHub is the final publication authority.
3. The task must read back its Sheet before enqueueing it.
4. A queued handoff is not proof of publication.
5. The GitHub consumer must re-read latest `main` immediately before mutation.
6. Validation must fail closed.
7. A lane may mutate only its declared canonical path(s).
8. A lane-specific validator may not be weakened merely to accept generated content.
9. Every consumed handoff must leave `inbox/`.
10. GitHub Actions must not use an LLM to decide whether mutation is valid.

## Scheduled-task status vocabulary

Task-side status should use narrow, truthful states.

Recommended:

```text
already_present
queued_in_drive
failed_validation
failed_to_sheet
failed_to_inbox
bridge_unavailable
```

A task should report `published` only if it independently verifies repository evidence during the same execution.

GitHub-side status may additionally include lane-specific values such as:

```text
created
updated
applied
already_exists
race_existing
published
```

## Monitoring

Primary health signals:

| Lane | Primary workflow | Independent watchdog |
| --- | --- | --- |
| Daily news | Google Drive AI News Bridge | News Ingestion Watchdog |
| Narrative Memory | Google Drive Narrative Memory Bridge | CI + runtime Narrative Memory validation |
| Weekly research | Google Drive Weekly Research Bridge | Weekly Applied GenAI Research Contract |

An idle bridge run is healthy when no eligible handoff exists.

A green producer task plus a missing repository artifact is **not** healthy; inspect the bridge.

## Troubleshooting sequence

When a scheduled publication appears missing:

1. Verify the task actually ran.
2. Verify its final status was `queued_in_drive`.
3. Confirm the Sheet is/was in `inbox/`.
4. Open the correct lane-specific GitHub bridge.
5. Identify the first failing step.
6. Inspect whether the handoff was moved to `failed/`.
7. Read the validator error before modifying prompts or data.
8. Verify canonical state in `main`.
9. Verify the handoff ended in `processed/` after success.
10. Only then retry or repair.

Do not bypass a failing deterministic validator by direct repository writes.

## Legacy paths

The following paths may remain present because they are useful for compatibility or historical evidence, but they are not the scheduled production route:

- direct ChatGPT → GitHub file writes;
- `AI_NEWS_STAGING` issues;
- `NARRATIVE_MEMORY_STAGING` issues;
- Apps Script as a transport hop;
- temporary Apps Script probe workflows/artifacts.

Do not reactivate these paths without an explicit migration decision and a new end-to-end test.

## Secrets and permissions

GitHub requires:

```text
GDRIVE_SERVICE_ACCOUNT_JSON
```

The credential must be able to read and move files in the bridge folders.

Never commit the service-account JSON.

The ChatGPT-side Google Drive connection and the GitHub-side service account are deliberately different trust boundaries.

## Test strategy

Shared and lane-specific tests include:

```text
tests/test_gdrive_news_bridge.py
tests/test_gdrive_narrative_memory_bridge.py
tests/test_gdrive_weekly_research_bridge.py
tests/test_staged_news_issue.py
tests/test_staged_narrative_memory_issue.py
tests/test_narrative_memory.py
tests/test_news_ingestion_health.py
```

Normal CI should remain green before a bridge change is considered safe.

For transport changes, unit tests are necessary but not sufficient: at least one real Sheet → Drive → GitHub → canonical artifact test must be performed for the affected lane.

## Adding another scheduled publication lane

Do not copy an existing workflow blindly.

A new lane must define:

1. a unique Sheet prefix;
2. a unique `message_id` prefix;
3. its canonical target path(s);
4. its MIME/content type;
5. a deterministic validator;
6. idempotency semantics;
7. race behavior;
8. exact allowed Git paths;
9. processed/failed lifecycle behavior;
10. an independent health signal;
11. tests;
12. one real E2E proof before production activation.

Prefer reusing `pipeline/gdrive_envelope.py` for transport integrity and adding only lane-specific semantic logic.

## Operational cleanup

Processed Sheets are intentionally retained temporarily as audit evidence rather than deleted immediately.

A retention policy should eventually prune:

- `processed/` after a short audit window;
- `failed/` after a longer diagnostic window.

Until retention automation exists, deletion is a manual operational task and must not be confused with successful consumption.

Apps Script is not part of this production architecture. Its periodic trigger should remain disabled once the Drive-native route is confirmed for all active lanes.

## Verified consumption and scheduler resilience

See [the 2026-10-04 hardening runbook](bridge_scheduler_hardening_2026-10-04.md)
for shared paginated discovery, exact-file dispatches, verified same-file moves,
bounded reconciliation, and the remaining platform-wide availability limit. As
of 2026-10-06, the three production consumer crons are hourly and staggered at
minutes 02, 03 and 04 UTC for Daily, Weekly and Narrative respectively. The
News Ingestion Watchdog reconciles at 10:30 and 14:00 America/Mexico_City;
`workflow_run` wakeups are intentionally disabled, and manual dispatch remains
available. A pending transport is not missing editorial content: Repair Watch
must inspect the inbox before generating a replacement handoff.
