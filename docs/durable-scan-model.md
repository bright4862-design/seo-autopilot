# Durable scan data model

Phase 2 of the roadmap makes scans durable. Today a scan behaves like a
synchronous request and the result lives only in the browser's `localStorage`
(`seo_autopilot:last_scan`, `seo_autopilot:scan_history`, ...). This document
defines the persistent data models that replace that transient state.

The runtime wiring lives in `src/lib/scanRuns.js` (persistence, best-effort)
and `src/lib/scanRunModel.js` (pure record mapping, unit-tested). The scan flow
in `ScanWebsiteForm` records the lifecycle as it runs: `beginScanRun` on
submit, `markScanRunReviewing` before Python Review, `completeScanRun` (FixList
+ FixItems + lineage) on success, `failScanRun` on error. Durable writes are
fire-and-forget — a persistence failure logs a warning and never breaks the
customer's scan, and `localStorage` remains the UI's read path until the
redesign.

The models are additive Base44 entities. Legacy entities (`CrawlJob`,
`ScanDiagnostic`, `SeoIssue`, `Report`, `CrawledPage`) are left untouched so the
current UI keeps working during the transition.

## Entities

| Entity | Purpose | Cardinality |
| --- | --- | --- |
| `ScanRun` | One durable scan: its status lifecycle, coverage/evidence state, and result summary. | one per scan attempt |
| `FixList` | The saved list produced by a completed scan: scores, counts, authoritative provenance. | one per `ScanRun` that reaches `complete`/`limited` |
| `FixItem` | One durable finding, aligned to the review contract, with completion tracking and cross-scan lineage. | many per `FixList` |

Relationships:

```
BusinessProject 1───* ScanRun 1───1 FixList 1───* FixItem
                          │                          │
                          └── previous_scan_id ◄─────┘ first_seen_scan_run_id
```

- `ScanRun.project_id` → `BusinessProject` (scan history per website).
- `ScanRun.fix_list_id` → the `FixList` for that run (nullable until review completes).
- `FixList.scan_run_id` → its `ScanRun`.
- `FixItem.fix_list_id` / `scan_run_id` / `project_id` → parents (denormalized for query and RLS).

Every entity carries `owner_user_id` and reuses the existing per-row RLS policy
(owner, creator, or admin) so the durable records inherit the app's current
access model unchanged.

## Status lifecycle

`ScanRun.status` uses the roadmap lifecycle:

```
queued ──► crawling ──► reviewing ──► complete
   │           │            │            
   │           │            └────────► limited      (coverage/access limited; score provisional)
   │           │
   ├───────────┴────────────────────► failed        (unrecoverable error; error_code/message set)
   │
   └────────────────────────────────► cancelled      (user or system stopped it; cancelled_reason set)
```

- **queued** — accepted, not yet started. `queued_at` set.
- **crawling** — scanner is fetching pages. `started_at` set; `pages_crawled`/`pages_found`/`queued_remaining` update as it runs.
- **reviewing** — crawl done, Python Review is scoring. `reviewing_at` set.
- **complete** — full-confidence result. `completed_at`, `health_score`, `fix_list_id` set; `score_is_provisional` false.
- **limited** — completed but coverage or access was limited (maps to the review contract's `complete_with_access_limitations` / `incomplete_evidence` / provisional states). `score_is_provisional` true and `limitation` explains why. Still produces a `FixList`.
- **failed** — terminal error before a usable result. `error_code` + `error_message` set; `resumable` indicates whether a resume is possible.
- **cancelled** — terminal, stopped intentionally. `cancelled_reason` set.

Terminal states are `complete`, `limited`, `failed`, `cancelled`. A row never
leaves a terminal state; retry/resume/reopen create **new** `ScanRun` rows (see
below) rather than mutating history.

The distinction between `complete` and `limited` is authoritative from Python
Review, mirroring the review-presentation contract — the frontend must not
promote a `limited` run to `complete`.

## Retry, resume, reopen

These are modeled as new `ScanRun` rows linked to their ancestor, so history is
immutable and comparable:

- **Retry** — a fresh attempt after a `failed`/`cancelled` run. Create a new
  `ScanRun` with `rescan_of_scan_id` set to the failed run and
  `attempt_count = previous.attempt_count + 1`.
- **Resume** — continue a run that stored a `resume_token` (e.g. crawl budget
  exhausted mid-way). Create a new `ScanRun` seeded from `resume_token`; only
  runs with `resumable: true` expose a resume affordance.
- **Reopen** — viewing a previous scan needs no new row: load the `ScanRun` plus
  its `FixList` and `FixItem`s by id. "Reopen and rescan" is a normal rescan.

## Comparison against previous results

Each `ScanRun` records `previous_scan_id` (the prior completed run for the same
project). Improvement is derived without a separate diff entity:

- **Score delta** — `this.health_score - previous.health_score`.
- **Fix lineage** — when a scan's `FixList` is built, each `FixItem` is matched
  against the previous run's items by a stable key (`rule` + `page_scope` +
  `page_template_family` + representative URL). A match sets `carried_over: true`
  and preserves `first_seen_scan_run_id`; a new issue sets
  `carried_over: false` and `first_seen_scan_run_id = this scan`. Items present
  in the previous run but absent now are counted as **resolved**.
- `user_status` on `FixItem` (`open` / `in_progress` / `done` / `dismissed`)
  captures customer-driven completion independently of whether a later rescan
  still detects the issue.

## Mapping from the review contract

`ScanRun` and `FixList`/`FixItem` are the persistent home of the fields frozen
in `docs/review-presentation-contract.md`:

- Top-level "Identity and versions", "Coverage and evidence state", and
  "Customer summary" fields → `ScanRun` (+ authoritative flags on `FixList`).
- Per-finding "Identity", "Customer-facing copy", "Scope and classification",
  "URL evidence", "Confidence and verification", and "Workflow ownership" fields
  → `FixItem`. The full original finding is retained in `FixItem.raw_finding`
  so nothing authoritative is lost, honoring "Python decides the SEO truth."

`FixItem.page_scope` and `priority` enums are kept identical to the contract's
valid values so persistence cannot silently narrow them.

## Migration from localStorage

The current keys map onto the model as follows:

| localStorage key | Durable replacement |
| --- | --- |
| `seo_autopilot:active_scan_url` / `:active_scan_started_at` | the in-flight `ScanRun` (`status` in `queued`/`crawling`/`reviewing`) |
| `seo_autopilot:last_scan` | the most recent terminal `ScanRun` + its `FixList`/`FixItem`s |
| `seo_autopilot:scan_history` | `ScanRun` rows for the project, newest first |

The frontend continues to read `localStorage` as a cache; the durable records
become the source of truth once the scan pipeline writes them.
