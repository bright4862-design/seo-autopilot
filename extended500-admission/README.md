# Extended 500 atomic admission — isolated candidate (not deployed)

**Status: implementation candidate, feature OFF.** No customer Extended 500
access, no paid 500 SKU in production, no working 500 review/persistence worker.
Do not merge/deploy/activate as a product without independent acceptance.

## Distinct trust boundaries

- **Entitlement issuer library**: `src/lib/extended500EntitlementIssuer.js` only,
  not a deployed Base44 endpoint. Future backend must authenticate the customer,
  server-read exactly one owner-matched `Access` record and frozen `ScanRun`,
  and sign only an active Stripe-paid `extended500_lifetime` entitlement.
  Standard150, preview, pending, owner test, manual grants, duplicate records
  are rejected. Grant root `EXTENDED500_ENTITLEMENT_SIGNING_KEY` differs from
  the worker preflight root `EXTENDED500_ADMISSION_SIGNING_KEY`.
- **Coordinator**: separate Flask Cloud Run service under `extended500-admission`,
  **not** `admission-coordinator` or `dispatch-gateway`.
  Authenticates Base44 request HMAC (derived label
  `fixlist-extended500-atomic-admission-v1`), verifies BOTH issuer-generated
  assertions, and compares exact owner/scan/project/request/attempt/mode.
  A valid signed claim is necessary; the caller must still be the authenticated
  Base44 service role, never a browser.
- **Atomic reservation**: Firestore transaction reads owner slot in
  `extended500_owner_slots/{owner_user_id}` and immutable request receipt in
  `extended500_request_receipts/{sha256(owner + newline + request_id)}`,
  creates receipt and sets slot in the **same transaction**.
  At most one active slot per owner; releasing cannot reopen a prior receipt.
  No automatic lease expiry of a slot which might have a live queued task.
- **Queue**: dedicated `extended500-*` Cloud Tasks queue, not Standard 150
  scan/drain queues; fully server-owned task URL, invoker service account,
  audience, and deterministic task name. The `provision-queue.sh` script only
  creates and PAUSES it with explicit operator confirmation.
  The target `/scan-job-extended500` **does not exist yet**. Never unpause
  or turn on dispatch before dedicated worker + resource and persistence
  gates. Cloud Tasks creation is NOT in the Firestore transaction; if outcome
  is unknown the owner slot stays reserved and the same named task is retried.
  409 by itself does NOT prove the previous task is identical; treated unknown.
- **Terminal**: only a distinct `EXTENDED500_TERMINAL_SIGNING_KEY` receipt
  issued by a verified service-role terminal-result reader may release an
  exact scan/attempt/owner. No such issuer exists yet. No customer input may
  supply `verified_terminal=true` directly.
- **Worker**: current `/scan-job-extended500-preflight` is read-only and
  returns `admitted:false`. It is not the target working scan route.
  A queued task's short-lived preflight grant can expire before delivery:
  implement a fresh server-side durable authorization read on pickup,
  rather than trying to treat 120s issuance as sufficient for long queues.

## Configuration (no defaults for private roots)

| Variable | Isolation |
| --- | --- |
| `EXTENDED500_COORDINATOR_SIGNING_KEY` | Service-role HMAC root, unique |
| `EXTENDED500_ENTITLEMENT_SIGNING_KEY` | Proof of separate 500 paid grant |
| `EXTENDED500_ADMISSION_SIGNING_KEY` | Worker preflight proof |
| `EXTENDED500_TERMINAL_SIGNING_KEY` | Signed terminal-release receipt |
| `EXTENDED500_TASKS_QUEUE_PATH` | Dedicated full queue path |
| `EXTENDED500_WORKER_ORIGIN` | Dedicated HTTPS URL ending `/scan-job-extended500` |
| `EXTENDED500_INVOKER_SERVICE_ACCOUNT` | Separate private worker invoker |
| `EXTENDED500_SLOT_COLLECTION` | default `extended500_owner_slots` |
| `EXTENDED500_RECEIPT_COLLECTION` | default `extended500_request_receipts` |
| `EXTENDED500_ATOMIC_ADMISSION_ENABLED` | **OFF unless exact `true`** |
| `EXTENDED500_QUEUE_DISPATCH_ENABLED` | **OFF unless exact `true`** |

These keys should not be set in Standard150's production worker/dispatcher.

## Replay/failure behavior

Reservation loss response after the Firestore commit → exact retry sees
receipt and owner slot, does not reserve again. Cloud Tasks create 200 →
mark `enqueued` in a new transaction. Unknown network/409/5xx →
keep `dispatch_unknown`; never release or create a different task name.
Terminal release requires exact signed terminal proof and atomically updates
slot+receipt. An old receipt remains `released` forever.

## Verification and rollout

`scanner-api/tests/test_extended500_atomic_reservation.py` tests pure
decisions; `tests/frontend/extended500EntitlementIssuer.test.mjs` tests
the paid-only policy and JS signatures. HTTP/Firestore adapter and Cloud Tasks
integration need additional contract and staging tests; passing mocked tests
**does not establish Firestore deployment or production exactly-once delivery**.

Gate: keep PR #377 draft. Before dispatch: deploy distinct service privately,
verify IAM, grant issuer and separate paid plan, test Firestore contention
with emulator/live controlled account, signed request integration, Cloud
Tasks deterministic retries/unknown outcomes, release CAS, queue paused
staging, new worker pickup-time durable authorization, audited review/persistence,
source SHA and rollback. No live changes from this PR.
