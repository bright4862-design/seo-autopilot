# Server-owned scan admission

Status: **implemented and tested locally, not deployed, not wired in.**
`BETA_SCAN_ADMISSION_ENABLED` is `false` and no existing code path calls the new
modules.

This document covers the admission coordinator only. The browser-path removal,
the watchdog process and the ScanRun RLS change are tracked at the end as
remaining work, because they land in files held open by concurrent work.

## The problem

Two failures were observed in production on 2026-08-14:

| Scan | Symptom |
| --- | --- |
| Funbooker `6a7f67bdee7f1e82ce6b418c` | Stayed `crawling` at 0/0 with no terminal update |
| Pretto `6a7f68d74633a26189302346` | Became `failed` / `orphaned_no_terminal_state` after eight minutes |

Both have the same root cause, visible at `499d6479`:

- `src/lib/scanRuns.js:150` `recoverOrphanedScanRuns()` selects stale active
  runs and calls `terminalizeStaleScanRuns()`, writing terminal state **from the
  browser**. Pretto was closed only because a customer tab happened to be open.
- Funbooker had no tab open, so nothing closed it at all.
- `beginPersistedScanRun()` creates the ScanRun through `base44.entities.ScanRun`
  on user credentials, resolving identity across two separate `filter()` reads.
  That read-then-write has no atomicity, so two tabs can both decide they are
  first.

Terminal state and admission are both owned by a process that may close at any
moment. Neither can be made correct there.

## Why Firestore, and why not Base44

Base44 documents `updateMany(query, data)` with matched/updated counts, but does
not document transactional, compare-and-set or linearizable semantics strong
enough to claim exactly-once cross-tab admission. Base44 entity ids are also
server-managed, so a caller cannot pre-allocate an id and use it as a uniqueness
key.

Cloud Firestore transactions are explicitly atomic with serializable isolation
under contention. The admission decision moves there.

Consequences, deliberately preserved:

- `BASE44_ATOMIC_UPDATE_MANY_CONFIRMED` is **not introduced**. Nothing in this
  design depends on Base44 update atomicity.
- The existing Access-row conditional update is **not** claimed to be
  exactly-once anywhere in this work.

## Why a separate Cloud Run service

Base44 functions have no Google ADC, and
`constraints/iam.disableServiceAccountKeyCreation` forbids minting a key to give
them any — the same constraint that put Cloud Tasks dispatch behind a Cloud Run
gateway. The coordinator reuses that shape, so it adds no new trust boundary:

```
browser ──▶ Base44 startStandardScanJob ──HMAC──▶ admission coordinator ──ADC──▶ Firestore
                      │                                    │
                      │ service role                       │ decides the winner
                      ▼                                    │
              Base44 ScanRun  ◀───────── canonical id ──────┘
```

## Admission transaction

`POST /claim`, applied inside one Firestore transaction. Rules, in order:

| Rule | Condition | Result |
| --- | --- | --- |
| **A** | No document, released, or lease expired | Mint `claim_token`, store request + fingerprint, `state=claimed`, `scan_id=""`, bounded expiry. Caller wins. |
| **B** | Same `request_id`, same fingerprint, lease active | Return the existing claim, including its token and any bound `scan_id`. Idempotent replay. |
| **C** | Same `request_id`, different fingerprint | Fail closed, `request_conflict`. |
| **D** | Different `request_id`, lease active | `admission_busy` with a retry hint. **Creates nothing.** |

The transaction is the only authority deciding the winner. Because the decision
function is pure, Firestore's contention retry is safe — it re-runs against the
re-read document.

Rule B returns the original token rather than the caller's own, so two tabs
submitting the same request drive one claim instead of racing two.

## Canonical ScanRun creation

Admission is won **before** anything is created. Only then:

1. Query Base44 with the service role for exact `owner_user_id` + `request_id`.
2. Resolve with `resolveCanonicalScanRun()`:

   | Rows | Action |
   | --- | --- |
   | 0 | Create exactly one ScanRun, server-side |
   | 1 | Adopt it |
   | >1 | Fail closed — `admission_scan_conflict` |

3. Normalize `scan_id = entity.id`. Base44 assigns entity ids server-side, so
   that is the only guaranteed-unique identity. Any `scan_id` already on the row
   is treated as advisory and overwritten — that field is what a browser used to
   be able to choose.
4. Bind the id into Firestore with a second transaction requiring the exact
   `request_id` **and** `claim_token`.

## Partial-create recovery

The ordering above exists for one specific failure: **Base44 commits the row and
the response is lost.**

Because admission was won first and the create is keyed on `request_id`, the
retry re-enters at rule B, receives the same claim token, re-queries, finds
exactly one row, and adopts it. It never creates a second row.

If the loss happens *after* the bind instead, the retry's bind lands on
`already_bound` and returns success. If a caller somehow tries to bind a
different id to a claim that already has one, that is `scan_identity_conflict`
and fails closed — two durable identities for one request is a state no
automatic repair can resolve safely, because either row may already carry sealed
authority.

## Terminal release path

`POST /release`, called by the durable worker or the server watchdog:

- Accepts only `complete`, `limited`, `failed`, `cancelled`.
- Releases **only** if the document's bound `scan_id` matches the terminal scan.
  A stale run cannot free admission that a newer scan now holds.
- Does **not** require the claim token. The releaser knows the canonical scan id
  but was never handed the token; matching the bound id is the authority check.
- Does **not** require a live lease — closing a run whose lease already lapsed is
  precisely the watchdog's job.
- Sets `lease_expires_at` to the release moment, so the next scan is admitted
  immediately rather than waiting out the original lease.
- Is idempotent: the worker and the watchdog may both report the same terminal
  state, and the first release remains the record.

No browser is involved at any point.

## Release scenario coverage

| # | Scenario | Status | Where |
| --- | --- | --- | --- |
| 1 | Browser starts scan and closes immediately | **Partial** | Coordinator side proven: a claim persists with no further caller, and release never requires a live lease. End-to-end needs the wiring phase. |
| 2 | Worker succeeds → terminal result persists | **Covered** | `test_admission.py::test_worker_success_releases`, `test_coordinator.py::test_claim_bind_release_round_trip` |
| 3 | Worker fails → terminal failure persists | **Covered** | `test_worker_failure_releases`, `test_every_terminal_status_releases` |
| 4 | Worker disappears → watchdog terminalizes | **Partial** | `test_watchdog_can_terminalize_a_vanished_worker` proves the coordinator accepts it. The watchdog process does not exist yet. |
| 5 | Two tabs, same request → one canonical ScanRun | **Covered** | `test_two_tabs_same_request_replay_one_claim`, `test_two_tabs_same_request_share_one_claim`, `scanAdmissionContract` reuse tests |
| 6 | Two tabs, different request → one winner + one busy | **Covered** | `test_two_tabs_different_request_one_winner_one_busy` (asserts nothing was written for the loser) |
| 7 | Response lost after ScanRun create → retry recovers same entity | **Covered** | `resolveCanonicalScanRun` one-row adoption + `test_lost_bind_response_replays_to_the_same_scan` |
| 8 | Same request, different fingerprint → conflict | **Covered** | `test_same_request_different_fingerprint_fails_closed` and its HTTP twin |
| 9 | Terminal scan allows immediate next admission | **Covered** | `test_released_document_admits_immediately` |
| 10 | Expired lease can be reclaimed | **Covered** | `test_expired_lease_can_be_reclaimed`, plus a boundary test one second before expiry |
| 11 | Stale browser cannot mutate ScanRun | **Not covered** | Requires removing browser ScanRun CRUD |
| 12 | Direct user ScanRun CRUD fails under admin-only RLS | **Not covered** | Requires the `ScanRun.jsonc` RLS change |

Eight covered, two partial, two not started. The two uncovered scenarios both
depend on files excluded from this change.

## Remaining work

1. **Deployment.** No deploy script exists and the coordinator is not in the
   Cloud Operator allowlist. Adding either touches `scripts/` and
   `.github/workflows/`, which are excluded here.
2. **Firestore provisioning.** The database, the `scan_admission` collection and
   `roles/datastore.user` for the coordinator runtime service account do not
   exist yet.
3. **Wiring into `startStandardScanJob`.** The client modules are written and
   tested but imported by nothing.
4. **Browser path removal.** `beginScanRun`, `cancelScanRun`, `failScanRun` and
   `recoverOrphanedScanRuns` are still live in `src/lib/scanRuns.js`,
   `src/components/scan/ScanWebsiteForm.jsx` and `src/pages/FixList.jsx`, along
   with the unreachable `SYNC_FALLBACK_ENABLED` branch.
5. **Watchdog.** Nothing yet scans for expired leases and terminalizes them.
6. **ScanRun RLS.** `ScanRun`, `FixList` and `FixItem` still permit owner-scoped
   writes; scenarios 11 and 12 need admin-only.
7. **Stale test rewrites.** The seven tests named in the passover still pin the
   browser-owned contract. They pass today because that contract is unchanged;
   they must be rewritten as part of the removal, not before it.

Until items 3 and 4 land together, `BETA_SCAN_ADMISSION_ENABLED` must stay
`false`. Enabling it earlier would create a second admission path alongside the
browser one, which is strictly worse than either alone.
