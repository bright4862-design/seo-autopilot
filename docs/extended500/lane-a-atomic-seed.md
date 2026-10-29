# Extended 500 Lane A: atomic initial ScanRun seed (issue #382)

Status: **IMPLEMENTED + TESTED (offline only). Off by default and not wired into any route.**
Base: draft PR #377 head `002b84c9b6eaef78babec6081df150f31a000b11`.

## Files (lane-owned only)

- `extended500-admission/scanrun_seed.py`: pure decisions, plus the `Extended500ScanRunSeeder`
  adapter boundary and an UNVERIFIED `FirestoreSeedStore` mapping.
- `scanner-api/tests/test_extended500_scanrun_seed.py`: self-contained offline tests.
- `docs/extended500/lane-a-atomic-seed.md`: this handoff.

## The gap this closes, and where it shows in the code

- README "Still blocked": *"a future server-side creation flow must atomically bind
  owner+request to exactly one generated scan ID, not merely query then create."*
- `classifyExtended500DraftReplay()` (`src/lib/extended500ScanRunDraft.js`) returns
  `requires_atomic_create`, and its comment says that this result does **not** permit
  `ScanRun.create()`.
- `issueExtended500Admission()` (`base44/functions/issueExtended500AdmissionV1/handler.js`)
  needs an existing `queued` `extended_500` ScanRun with owner, project, request,
  idempotency and attempt. Nothing creates that row safely today.

## Design

Firestore and Base44 **do not share a transaction**. This design never claims they do.
Instead, the Base44 create call is **single-claim**, guarded by a Firestore-style receipt:

```
RESERVED --CAS claim (one committed winner)--> CREATE_PENDING --create 200 + exact proof--> SEEDED
                                                 |  \--definite rejection (port-classified)--> FAILED (terminal)
                       lost response / timeout / 5xx / crash / proof mismatch
                                                 v
                                          CREATE_UNCERTAIN --exact server-owned proof--> SEEDED
SEEDED --verified terminal ScanRun--> RELEASED (terminal)
```

Each decision below is grounded in existing code:

| Decision | Grounding |
| --- | --- |
| Seed receipt `sha256(domain, owner, request_id)`, immutable tombstone | `core.receipt_id()` / README "receipt is never deleted/reused". A separate domain prefix and separate collections (`extended500_seed_*`). The constructor refuses the admission collections `extended500_owner_slots` and `extended500_request_receipts`. |
| One active seed per owner (`extended500_seed_owner_slots/{owner}`), with no lease expiry | `core.decide_reservation` `owner_slot_busy`, and README "No automatic lease expiry". |
| Owner-scoped idempotency index doc binding key to exactly one receipt/request/attempt fingerprint | Issue #382 requirement. It is owner-scoped so that another tenant cannot block a key (DoS). It does **not** require `idempotency_key == request_id`, even though the draft sets them equal, so this boundary still holds if the key ever diverges. |
| Fingerprint = `core.fingerprint()` over owner, project, request, idempotency digest, attempt, access id, root site, normalized domain, draft `request_fingerprint`, mode, source | Reuses core's canonical JSON SHA-256. |
| Seed input = exact `buildExtended500QueuedScanDraft()` record (exact 21-key set) + server-read Access row | The draft test asserts these keys exist in `ScanRun.jsonc`. Create receives exactly that record, and a cross-runtime test feeds real JS output into Python. |
| Initial seed is attempt 1 only, type-strict | The draft sets `attempt_count: 1`. The classifier rejects `!== 1`. `core.safe_attempt` rejects `True`. |
| Access re-check (owner, id, `extended500_lifetime`, app id, active, full, `stripe_checkout`, session id, `paid_at`) | Mirrors `paidAccessRecord()` in `extended500EntitlementIssuer.js`. The e-mail is not re-checked or stored, because the JS builder already bound it. |
| Mode checked first: `standard_150`/legacy -> `invalid_scan_mode` | `core.canonical_request` code. Standard 150 remains the schema default. |
| Proof = exact row match: id, owner, project, `extended_500`, request, idempotency (by digest), attempt (int 1), `admission_access_id`, website/domain/fingerprint, no `path_prefix`, source, robots, `scan_id in (None, "", id)`, `status == "queued"` | Union of the `classifyExtended500DraftReplay` checks, the issuer handler checks and `ScanRun.scan_id` ("set to this entity record's server-generated id"). |
| Unknown network/commit outcome means never infer success | Same rule as `service.enqueue()`: "Never assume network timeout = absent", where a 409 is not proof. |
| Release only with `verified_terminal is True` and a `core.TERMINALS` status, and an old receipt cannot touch a newer slot | Mirrors `core.decide_release` and its "late" no-op test. |

Failure semantics:

- The **only** call site of `create_scanrun` runs after *this caller's* RESERVED -> CREATE_PENDING
  transaction has committed. If the claim's commit acknowledgement is lost, the caller does **not**
  create. A retry then sees CREATE_PENDING and only looks up.
- Retries, restarts and concurrent submissions that observe CREATE_PENDING or CREATE_UNCERTAIN perform only a
  read-only `find_scanruns(owner, request_id)`. Zero rows leaves the receipt pending. A
  CREATE_PENDING older than `pending_stale_seconds` (default 600, an UNVERIFIED choice) is relabelled
  CREATE_UNCERTAIN, and that relabelling never creates. More than one row, a non-list result or any field mismatch
  is refused with a stable code and **no write**.
- Only `ScanRunCreateRejected` (the port asserts that Base44 definitely wrote nothing) moves to FAILED
  and frees the slot. Every other exception counts as an unknown outcome.
- A create response that is not our exact row is stored as CREATE_UNCERTAIN (`created_row_proof_mismatch`).
- Receipts, slots and idempotency docs are written through a field allowlist. They contain no Access row,
  Stripe session, e-mail, signing key, proof, token or raw idempotency key; the key is stored as a SHA-256 digest.

## Commands and results (this branch, offline)

| Command | Result |
| --- | --- |
| `cd scanner-api && python3 -m pytest -q tests/test_extended500_scanrun_seed.py` | 70 passed |
| `cd scanner-api && python3 -m pytest -q tests/test_extended500_*.py` | 151 passed |
| `cd scanner-api && python3 -m pytest -q tests/` | 2625 passed, 18 skipped |
| `python3 -m pytest -q tests/` (repo root) | 420 passed |
| `node --test tests/frontend/extended500*.test.mjs` | 20 pass, 0 fail |
| `node --test tests/frontend/*.test.mjs` | 1999 pass, 0 fail |

What the focused tests cover:

- 12 threads racing on the same request: exactly one create.
- 12 distinct requests from one owner: one create, 11 `owner_slot_busy`. The fake store records
  aborts and retries, which shows that the threads really interleaved.
- 12 requests sharing one idempotency key: one bind.
- A lost response, a timeout, then retries and a new-process restart: no second create, and the receipt stays
  pending until an exact proof reconciles it.
- A crash after the Base44 commit, a crash before the create was sent, a crash after reserve but before claim, and a lost claim ack.
- 18 mismatched-proof cases, including owner, project, `standard_150`/`advanced` mode, request, attempt `2`/`True`/`1.0`,
  idempotency, foreign Access, target, scope, source, robots, scan_id, status and id.
- Duplicate or malformed lookup rows.
- A different request reusing an idempotency key, both while active and after release. The same key used by another owner stays independent.
- `standard_150` and other modes.
- Foreign or unpaid Access, and tampered drafts.
- Terminal replay after FAILED and after RELEASED.
- Field allowlists and no credentials in stored docs.
- Off-by-default with zero calls.
- A shape check of the Firestore adapter.
- No live imports, and nothing wired into `service.py` or the Dockerfile.

## UNVERIFIED

- Real Firestore serializability and contention across Cloud Run instances. The tests use a synthetic
  optimistic-concurrency fake with retry. `FirestoreSeedStore` has been exercised only against a lock-serialized fake
  of `google.cloud.firestore`.
- Real Base44 `ScanRun.create` and `ScanRun.filter` behaviour. Still unverified: whether a timeout can still commit,
  read-after-write visibility for `filter`, whether `attempt_count` (schema `number`) returns as int `1` and
  not `1.0` (the proof is strict and would refuse it, so the receipt would stay pending), and which
  responses are definitely non-committing (`ScanRunCreateRejected`).
- Whether the 600 s pending-stale threshold suits the real Base44 request timeout.

## Remaining blockers

1. **No port implementations or route.** Where the orchestration runs is still open:
   - (a) Base44 drives the flow. A private Base44 function calls coordinator endpoints that wrap
     `decide_*` for each transition, and performs the service-role create/filter itself.
   - (b) A Python composition calls a private, HMAC-authenticated Base44 create/filter bridge.
   Both options need review of auth, IAM and secrets, and neither exists.
2. **Operator resolution of a permanently uncertain receipt.** One case is a crash before send with zero rows.
   Today such a receipt holds the owner slot forever, by design, because no automatic lease expiry exists. Resolving
   it requires an audited, operator-attested abandon or compensation step. That step is not built.
3. **Proof exactness is limited to schema fields.** A row with identical fields written by another
   admin/service path would be indistinguishable. The proposed patch C below adds a receipt binding field.
4. The admission coordinator does not yet require a SEEDED seed receipt (proposed patch A).
5. All the prerequisites in the README and the spec still apply: no paid SKU or webhook, no worker,
   no pickup-time re-authorization, and no reviewed persistence.

## Proposed shared-file patches (NOT applied; for the serialized integrator)

**A. `extended500-admission/service.py`: the reservation requires an exact SEEDED seed receipt
in the same Firestore transaction** (bounded; it would also need a test in
`test_extended500_atomic_service_adapter.py`):

```diff
--- a/extended500-admission/service.py
+++ b/extended500-admission/service.py
@@
 import core
+import scanrun_seed
@@
 COLLECTION_RECEIPTS = os.getenv("EXTENDED500_RECEIPT_COLLECTION", "extended500_request_receipts")
+COLLECTION_SEED_RECEIPTS = os.getenv("EXTENDED500_SEED_RECEIPT_COLLECTION", "extended500_seed_receipts")
@@ def reserve(entitlement: dict, grant: dict) -> dict:
     receipt_ref = client.collection(COLLECTION_RECEIPTS).document(rid)
+    seed_ref = client.collection(COLLECTION_SEED_RECEIPTS).document(
+        scanrun_seed.seed_receipt_id(claim["owner_user_id"], claim["request_id"]))
@@
         slot_doc = slot_ref.get(transaction=transaction)
         receipt_doc = receipt_ref.get(transaction=transaction)
+        seed_doc = seed_ref.get(transaction=transaction)
+        seeded = seed_doc.to_dict() if seed_doc.exists else None
+        if (not seeded or seeded.get("state") != scanrun_seed.SEEDED
+                or seeded.get("scan_id") != claim["scan_id"]
+                or seeded.get("project_id") != claim["project_id"]
+                or seeded.get("access_id") != claim["access_id"]
+                or seeded.get("idempotency_ref") != scanrun_seed.idempotency_ref(
+                    claim["owner_user_id"], claim["idempotency_key"])
+                or seeded.get("attempt_count") != claim["attempt_count"]):
+            raise core.AdmissionRefused("scanrun_seed_not_bound")
         decision = core.decide_reservation(
```

**B. `extended500-admission/Dockerfile`**: only when patch A is accepted, change the copy line to
`COPY core.py scanrun_seed.py service.py ./`. Until then, the seed module is deliberately not copied into the image.

**C. `base44/entities/ScanRun.jsonc` (needs schema review; never synchronize it without approval)**: add an
admin-write-only `seed_receipt_id` string property. The seeder would then add it to the create record and
check it in `validate_scanrun_proof`, so that a row's origin is bound to exactly one receipt. The
`extended500ScanRunDraft` field-compatibility test would need the same addition.

**D. `extended500-admission/README.md`**: replace "no isolated CAS-safe ScanRun seed service" in
"Still blocked" with a pointer to this module. State that it is unwired, UNVERIFIED on Firestore and has no Base44 ports.

## Rollback

Revert the single lane commit. Alternatively, delete the three files: nothing imports them, the
Dockerfile does not copy them, and no route, flag, workflow or schema refers to them.

## Explicit non-changes

This lane made zero deploy, publish, Base44, GCP, Firestore, Cloud Tasks, Stripe, payment or SKU changes, ran no
customer scan, and made no change to Standard 150 code, schema/RLS, release manifests, fingerprints,
`main` or other lanes' files. Every test is offline, and the only subprocess is a local `node` call that evaluates the
repository's own draft builder.
