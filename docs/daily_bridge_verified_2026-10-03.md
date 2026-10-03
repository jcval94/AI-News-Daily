# Daily Drive bridge: verified operational baseline — 2026-10-03

## Verdict and scope

The daily ingestion and visibility chain is verified for the 2026-10-03 target:

**scheduled producer → native Google Sheet → exact readback → shared inbox → GitHub validator → canonical digest in main → processed handoff → Pages news catalog.**

This is evidence for an operational ingestion path, not a guarantee of every future run, independent factual accuracy of every generated claim, or approval of a new video episode. A digest, an approved episode, and a Pages deployment are different products with separate gates.

This baseline refines [the shared contract](scheduled_drive_publication.md) and [the daily runbook](news_ingestion_drive_bridge.md). Existing deterministic validators remain authoritative.

## Verified evidence

| Boundary | Evidence observed |
| --- | --- |
| Producer target | Only 2026-10-03; six news items |
| Sheet | `19ebZfXs62XmC_HLMhdhkmSicr4Q9VyG7N3dB_HHiIJ8` |
| Initial title | `__bridge_inbox_AI-News-Daily__2026-10-03_083336` |
| Real first-tab metadata | `Sheet1`, numeric `sheetId=1906368112`; not assumed zero |
| Write | Exactly one structured `updateCells` request; 8 rows × 2 string values |
| Readback | Real `UNFORMATTED_VALUE` read of A1:B8 matched all expected values and the 10,374-character payload |
| Enqueue verification | Sole parent `1bPEr91j4HDGihnDbcCtoBPFWCW2RPYQ_` after moving the same file |
| Message | `ai-news-daily.news.2026-10-03.083336` |
| Canonical path | [news/2026-10-03-08-33-36.txt](../news/2026-10-03-08-33-36.txt) |
| Publication | [commit abf05070261feb7731b55e9619006e40f7455197](https://github.com/jcval94/AI-News-Daily/commit/abf05070261feb7731b55e9619006e40f7455197), at 2026-10-03 15:42:33 UTC |
| Consuming run | [37134183905](https://github.com/jcval94/AI-News-Daily/actions/runs/37134183905): select, convert, validate, commit, health refresh, and move-to-processed steps succeeded; idle branch skipped |
| Final Drive state | Same Sheet renamed `processed____bridge_inbox_AI-News-Daily__2026-10-03_083336`, sole parent `1o-2WPz514dFJDg7seGz2dZ4X87doPkdK` |
| Current CI | [37134431821](https://github.com/jcval94/AI-News-Daily/actions/runs/37134431821): success |
| Current preflight | [37134431860](https://github.com/jcval94/AI-News-Daily/actions/runs/37134431860): success |
| Pages | [37134463574](https://github.com/jcval94/AI-News-Daily/actions/runs/37134463574): build, deploy, and deployed-catalog verification succeeded |
| Live Pages read | [memory/narrative-memory.json](https://jcval94.github.io/AI-News-Daily/memory/narrative-memory.json), generated 2026-10-03T15:50:24.782368+00:00; `news.latest_source_file=2026-10-03-08-33-36.txt` |

Sheet-side write/readback/enqueue evidence comes from the real producer execution in this conversation. Repository, processed metadata, workflow jobs, and live Pages were independently reread during this baseline audit.

The bridge cron is configured every five minutes; this is not a five-minute delivery SLA. This handoff was enqueued around 08:35 CDMX and published at 09:42:33 CDMX. GitHub scheduling and queue latency remain observable operational constraints.

## Roles and actual schedule snapshot

Configuration read on 2026-10-03; all times America/Mexico_City.

| Task | ID | Active | Schedule | Responsibility |
| --- | --- | --- | --- | --- |
| AI News Daily | `6ab57009063c81919ec9fc08da32da69` | Yes | Daily 08:30 | TODAY only; stop when already present or handoff verified |
| AI News Repair Watch | `6abffb093e0c8191b2c6069e0acf56bb` | Yes | Daily 10:30 | TODAY then YESTERDAY, independently, only if missing |

These are the currently observed schedules, superseding earlier 09:30/11:30 and 13:30/15:30 snapshots. This documentation change does not reschedule either task. Historical duplicate/test producers observed in the task inventory are disabled.

The Repair Watch prompt is configured correctly and a last-run timestamp is present. This audit did not inspect its execution transcript or exercise a new missing-day recovery. Do not promote configuration evidence into a claim that every recovery branch was tested today.

## Exact producer transaction

1. Resolve real local time and TODAY; inspect canonical news read-only. If a valid digest exists, report `already_present` and stop.
2. Read recent valid history, especially the three prior valid days; research and edit a single target.
3. Finish drafting, take one local timestamp, and freeze header, payload, message ID and target path together.
4. Validate before creating any Sheet. On failure, `failed_validation`; zero transport files.
5. Create exactly one native Sheet and retain its ID immediately. Never create a replacement Sheet for the target within this execution after any error.
6. Resolve the first tab and its numeric sheet ID from fresh metadata.
7. Write the entire contract with exactly one structured request:

```json
{
  "updateCells": {
    "start": {"sheetId": 1906368112, "rowIndex": 0, "columnIndex": 0},
    "rows": ["eight RowData objects, each with two stringValue CellData values"],
    "fields": "userEnteredValue"
  }
}
```

The example above is a shape illustration, not an executable rows array. Use the metadata-derived sheet ID for each new file. Every actual cell uses `userEnteredValue.stringValue`, including the complete multiline B8 payload.

| Row | A | B |
| --- | --- | --- |
| 1 | format | bridge-sheet-v1 |
| 2 | message_id | ai-news-daily.news.YYYY-MM-DD.HHMMSS |
| 3 | namespace | AI-News-Daily |
| 4 | target_repo | jcval94/AI-News-Daily |
| 5 | target_path | news/YYYY-MM-DD-HH-MM-SS.txt |
| 6 | content_type | text/plain |
| 7 | status | ready |
| 8 | payload | Complete frozen digest |

8. Read the resolved first tab's A1:B8 using unformatted values. Compare exactly: 16 values, row shape, payload length, newlines, header, message ID and path. Any mismatch → `failed_to_sheet`; retain file ID, report exact phase/difference, do not move or retry transport.
9. Read Drive metadata and resolve the single current parent. Move the same file with `addParents=inbox` and `removeParents=current_parent`. Never copy, export or change permissions on the producer side.
10. Reread metadata. Success means exact contract equality **and** the sole final parent equals the inbox. Report `queued_in_drive` with file ID, message and target; stop.

The payload header is exactly `# AI News Daily — YYYY-MM-DD HH:MM:SS America/Mexico_City`. Freeze identifiers once; no research, edits, or timestamp changes afterward.

## Consumer authority and routing

The daily consumer accepts a full Sheet-name match:

```text
^__bridge_inbox_AI-News-Daily__\d{4}-\d{2}-\d{2}_\d{6}$
```

A shared prefix alone is insufficient: weekly and Narrative Memory titles begin similarly. The daily lane also validates the `ai-news-daily.news.` message namespace, canonical news path and `text/plain`.

GitHub exports the Sheet through Drive CSV, reconstructs a SHA-256/Base64 envelope, validates with `pipeline.gdrive_news_bridge` and `pipeline.staged_news_issue`, and rereads latest main before committing only the allowed digest path. Schema/editorial/date/dedup gates must not be weakened to accept a generated candidate.

Success/idempotent completion moves the original handoff to processed. Validation rejection moves it to failed. A green idle run proves no eligible candidate was handled; the consumed-run steps and canonical commit above provide the stronger publication evidence.

Task-local one-Sheet protection is not global exactly-once transport. A later execution can create a new candidate while publication is pending. Canonical date deduplication and the final main recheck are the consumer safeguards. No distributed transaction or global producer lock is claimed.

## Status and troubleshooting

| Status | Meaning |
| --- | --- |
| already_present | Valid canonical target observed; no new handoff needed |
| failed_validation | Candidate rejected before Sheet creation |
| failed_to_sheet | Write/readback failed; report the retained Sheet ID |
| failed_to_inbox | Move or exact parent verification failed |
| queued_in_drive | Verified transport only |
| Published in main | Independently read canonical file and publication evidence |
| Visible in Pages | Successful deploy plus live catalog/content read |

Inspect the first failed boundary before regenerating anything. Empty Sheets with the original parent indicate a write/readback failure, not a move failure. A queued Sheet with missing main output requires bridge inspection. A canonical digest with stale Pages requires build/deploy inspection. Missing historical source coverage is a separate production gate; automatic recovery remains limited to TODAY/YESTERDAY.

A single successful run does not prove long-term scheduling reliability, all failure/race branches, factual correctness of source claims, or video approval. Deterministic parsing does not independently fact-check the web.

## Follow-up applicability

| Process/repository | Evidence | Proposed follow-up |
| --- | --- | --- |
| AI-News-Daily: GenAI Applied Weekly | Prompt upgraded and exact readback verified on 2026-10-03; schedule/state preserved | Transport contract adopted, canonical JSON and stable IDs preserved; lane-specific real execution of the new prompt remains pending |
| AI-News-Daily: Narrative Memory Builder | Prompt upgraded and exact readback verified on 2026-10-03; schedule/state preserved | Transport contract adopted; zero-candidate stop, JSONL gates, semantic dedup and append-only preserved; lane-specific real execution remains pending |
| AI-News-Daily: AI News Repair Watch | Prompt revised and exact readback verified on 2026-10-03 | Freeze precedes canonical-header validation; sole-parent and phase-specific failure checks added; missing-target recovery test remains pending |
| CV_fit: Final Review / vacancy tasks | Related tasks currently disabled; final review prompt writes canonical files directly to main | Consider candidate handoff + deterministic review/publish authority before reactivation; use a separate namespace and validator rather than copying news rules |
| floor | Its intraday pipeline is GitHub-native; this audit does not establish a Drive transport defect | Reuse separation of heartbeat/recovery and outcome verification where useful; a Sheets migration is not justified by the daily-news evidence |
| Other repositories | Inventory alone does not prove a similar integration | Inspect actual writers and consumers before recommending migration |

Follow-up on 2026-10-03 updated only the three task prompts above. All task schedules and enabled states were verified unchanged, as were the other task prompts, including CV_fit. No repository code, validator or workflow was changed. Configuration readback is not a new E2E proof; see the adoption matrix in `docs/scheduled_drive_publication.md`.
