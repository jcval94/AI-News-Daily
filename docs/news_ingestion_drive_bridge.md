# AI News Daily — Google Drive ingestion bridge

This document is the operational contract and runbook for the production path that moves a daily AI-news digest from a ChatGPT scheduled task into the canonical `news/` directory.

The design deliberately separates **probabilistic editorial work** from **deterministic publication authority**.

## Production path

```text
ChatGPT scheduled task
    │ research + select + write + self-check
    ▼
temporary Google Sheet
    │ exact A1:B8 contract + readback
    ▼
shared Drive inbox
    │ no GitHub write from ChatGPT
    ▼
Google Drive AI News Bridge
    │ Drive CSV export + envelope construction
    ▼
pipeline.gdrive_news_bridge
    │ SHA / repo / path / timestamp validation
    ▼
pipeline.staged_news_issue
    │ parser + editorial/dedup/date gates
    ▼
git recheck against origin/main
    │ exactly one digest staged
    ▼
news/YYYY-MM-DD-HH-MM-SS.txt
    │
    ├── success / idempotent -> Drive processed/
    └── invalid                -> Drive failed/
```

The canonical GitHub workflow is:

- `.github/workflows/gdrive-raw-bridge-probe.yml`
- workflow name: **Google Drive AI News Bridge**
- scheduled every five minutes and manually dispatchable.

The filename is historical; despite the old `probe` name, this workflow is the production consumer.

## Responsibility boundary

### ChatGPT scheduled task owns

The external scheduled task performs the non-deterministic editorial work:

1. resolve local time in `America/Mexico_City`;
2. inspect canonical `news/` read-only;
3. repair at most **YESTERDAY + TODAY**;
4. research recent sources;
5. deduplicate against recent valid digests;
6. select the strongest stories;
7. write the complete digest;
8. self-check the digest against the editorial contract;
9. create one Google Sheet per missing target;
10. write and read back the exact A1:B8 handoff;
11. move the verified Sheet into the shared Drive inbox.

The scheduled task must **not**:

- write repository files directly;
- create a GitHub staging issue;
- bypass the deterministic validator;
- claim GitHub publication merely because the Sheet handoff succeeded.

A successful task-side handoff means only **queued in Drive**.

### GitHub Actions owns

GitHub is publication authority.

The bridge:

1. selects the oldest eligible handoff from the Drive inbox;
2. accepts production Sheets prefixed `__bridge_inbox_AI-News-Daily__`;
3. retains compatibility with legacy raw envelopes prefixed `ai-news-daily.news.`;
4. exports a Sheet through the Google Drive API as CSV;
5. requires exactly eight two-column rows with the expected keys;
6. converts the payload into a hash-verified internal envelope;
7. invokes `pipeline.gdrive_news_bridge`;
8. reuses `pipeline.staged_news_issue` as the canonical digest validator;
9. rechecks `origin/main` immediately before publication;
10. stages exactly one digest;
11. commits and pushes the digest;
12. moves the handoff to `processed/` after success or idempotent completion;
13. moves it to `failed/` when validation fails.

GitHub Actions does not generate news content with an AI model.

## Google Sheet handoff contract

The Sheet title must begin with:

```text
__bridge_inbox_AI-News-Daily__
```

Recommended full form:

```text
__bridge_inbox_AI-News-Daily__YYYY-MM-DD_HHMMSS
```

The first sheet must contain exactly the following values in `A1:B8`:

| Row | Column A | Column B |
| --- | --- | --- |
| 1 | `format` | `bridge-sheet-v1` |
| 2 | `message_id` | `ai-news-daily.news.YYYY-MM-DD.HHMMSS` |
| 3 | `namespace` | `AI-News-Daily` |
| 4 | `target_repo` | `jcval94/AI-News-Daily` |
| 5 | `target_path` | `news/YYYY-MM-DD-HH-MM-SS.txt` |
| 6 | `content_type` | `text/plain` |
| 7 | `status` | `ready` |
| 8 | `payload` | complete multiline digest |

The `message_id` may contain only ASCII letters, digits, period, underscore and hyphen.

The target date/time must agree in all three places:

```text
message_id
target_path
payload first line
```

The payload first line must be exactly:

```text
# AI News Daily — YYYY-MM-DD HH:MM:SS America/Mexico_City
```

The task must read back `A1:B8` before moving the Sheet into the inbox. A failed readback is not a valid handoff.

## Internal envelope

The workflow converts the Sheet to a deterministic internal envelope before Python validation:

```text
format=base64-payload-v1
schema_version=1.0
message_id=...
target_repo=jcval94/AI-News-Daily
target_path=news/YYYY-MM-DD-HH-MM-SS.txt
content_type=text/plain
sha256=...
payload_b64=...
```

SHA-256 and Base64 are produced inside the trusted GitHub side of the transport. `pipeline.gdrive_news_bridge` verifies both before accepting UTF-8 payload text.

## Deterministic validation

`pipeline.gdrive_news_bridge` enforces transport integrity:

- exact envelope keys;
- `base64-payload-v1`;
- schema version `1.0`;
- valid production `message_id`;
- production namespace prefix `ai-news-daily.news.`;
- exact repository match;
- `text/plain`;
- canonical `news/YYYY-MM-DD-HH-MM-SS.txt` target path;
- SHA-256 match;
- valid UTF-8;
- exact timestamp agreement between target path and digest header.

It then delegates digest validation to `pipeline.staged_news_issue`, so the Drive path and the historical issue path do not maintain competing editorial validators.

That validator currently enforces, among other rules:

- only TODAY or YESTERDAY may be materialized;
- 5–10 parseable news items;
- one canonical instance of every required field;
- no duplicate title or URL inside a digest;
- article-level URLs;
- allowed categories only;
- item dates inside the accepted window;
- substantive summaries;
- sufficiently developed `Por qué importa`;
- explicit editorial question;
- `Hipótesis editorial:`;
- `Qué habría que investigar:`;
- recent-title/URL deduplication unless an `actualización material` is explicitly identified.

## Race and idempotency policy

Before commit, the workflow fetches `origin/main` and checks whether another valid candidate for the target date already exists.

Possible outcomes:

- `created` → publish exactly one new digest;
- `already_exists` → do not create another file;
- `race_existing` → another writer won the race after validation; discard the local candidate.

Only the digest path may be staged for publication. If any other path is staged, the workflow fails closed.

## Drive lifecycle

The configured production folders are:

```text
AI-News-Daily/
├── inbox/
├── processed/
└── failed/
```

The workflow consumes only eligible production handoffs from `inbox/`.

After a successful publication or idempotent result, the original handoff is moved to `processed/` and renamed with a `processed__` prefix.

If validation fails, it is moved to `failed/` and renamed with a `failed__` prefix.

This makes the transport auditable without treating the inbox as permanent storage.

## Why Drive CSV export is used

The GitHub service account can read the shared Drive file, but direct Google Sheets API access was not sufficiently reliable for this account boundary. The production workflow therefore exports the native Sheet through the **Google Drive API as `text/csv`**.

This route preserves the exact A1:B8 table, including the multiline payload field, while avoiding a second authorization dependency on the Sheets API.

The workflow still validates:

- exactly eight rows;
- exactly two columns per row;
- exact ordered keys;
- exact namespace/repository/content-type/status values;
- non-empty payload.

Do not switch back to direct Sheets API reads without proving that the service account has stable access in GitHub Actions.

## Recovery contract

The external task repairs only **YESTERDAY and TODAY**.

This is intentional. It prevents a transient scheduling problem from causing an unbounded historical backfill with changing editorial context.

Older gaps require an explicit manual/backfill decision.

A failure for YESTERDAY must not prevent an independent attempt for TODAY.

## Monitoring

### Google Drive AI News Bridge

Primary transport health signal:

```text
Actions → Google Drive AI News Bridge
```

Healthy states include:

- successful consumption and publication;
- successful idempotent handling;
- successful idle runs when no handoff exists.

### News Ingestion Watchdog

`.github/workflows/news-ingestion-watchdog.yml` independently verifies that the local day's digest exists, parses, and contains the minimum expected item count.

It runs twice daily for early detection and same-day recovery verification. A missing or invalid daily digest opens/updates a diagnostic issue pointing operators to the external **AI News Daily** task and **Google Drive AI News Bridge**.

The watchdog does not generate content.

## Troubleshooting

### Task reports `queued_in_drive`, but no digest appears

1. Open **Google Drive AI News Bridge** Actions history.
2. Confirm the handoff was selected from `inbox/`.
3. Inspect the first failing step.
4. Check whether the source handoff was moved to `failed/`.
5. Do not regenerate immediately if the failure is deterministic; fix the contract error first.

### Bridge is green but idle

Check whether the handoff:

- is actually inside the configured inbox;
- is a native Google Sheet;
- starts with `__bridge_inbox_AI-News-Daily__`.

Legacy raw envelopes must be `text/plain` and start with `ai-news-daily.news.`.

### CSV conversion fails

Verify that:

- the service-account secret exists;
- the inbox is shared with the service account;
- the Sheet is a native Google spreadsheet;
- the Drive export endpoint can read it.

### A valid digest is rejected

Run the deterministic tests and inspect `pipeline.staged_news_issue`. Do not weaken validation in the bridge to make one payload pass; the shared validator is intentionally authoritative.

### Duplicate-day race

A `race_existing` result is safe and expected under concurrency. The local candidate is discarded and the handoff may be moved to `processed/`.

## Required secret

GitHub Actions requires:

```text
GDRIVE_SERVICE_ACCOUNT_JSON
```

The credential needs access to the shared bridge folders/files. The workflow does not require a model API key to ingest a prepared digest.

Never commit credential JSON to the repository.

## Tests

The bridge contract is covered by:

```text
tests/test_gdrive_news_bridge.py
tests/test_staged_news_issue.py
tests/test_news_ingestion_health.py
```

Run the complete deterministic suite with:

```bash
python -m unittest discover -s tests -v
```

The normal CI workflow also compiles/import-checks the project before running tests.

## Proven end-to-end evidence

The production path was verified on 2026-10-01 with real Drive handoffs and automatic GitHub publication.

### TODAY

Input target:

```text
2026-10-01
```

Materialized file:

```text
news/2026-10-01-18-44-43.txt
```

Automatic publication commit:

```text
1995950140874250ee4745efadf877d12f398000
Add AI news digest for 2026-10-01 via Drive bridge
```

### YESTERDAY recovery

Input target:

```text
2026-09-30
```

Materialized file:

```text
news/2026-09-30-18-54-17.txt
```

Automatic publication commit:

```text
67de680071c8ad41c6d7a123c7d4b1ac77abaf64
Add AI news digest for 2026-09-30 via Drive bridge
```

Both paths completed through the Drive bridge rather than direct ChatGPT→GitHub writes.

## Architectural invariants

Keep these rules true when evolving this system:

1. **Research may be probabilistic; publication authority is deterministic.**
2. **ChatGPT never writes canonical `news/` files directly.**
3. **A successful Sheet handoff is not equivalent to a successful GitHub publication.**
4. **The bridge does not lower the digest validator's standards.**
5. **One target date has at most one canonical daily digest publication path.**
6. **Every handoff ends in `processed/` or `failed/`, never silent limbo.**
7. **Recovery is bounded to TODAY + YESTERDAY unless an operator explicitly chooses a backfill.**
8. **GitHub Actions never uses an LLM to decide whether the digest may be committed.**
