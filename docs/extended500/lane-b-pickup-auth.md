# Extended 500 lane B — worker pickup authorization handoff

**Status: IMPLEMENTED, locally TESTED, NOT integrated, NOT deployed.** Issue #383; base is draft PR #377 (`002b84c9b6eaef78babec6081df150f31a000b11`). Changes are isolated to this lane's new files.

## What is implemented

- `scanner-api/app/extended500_pickup_authorization.py`: pure read-only authorization with an injectable `PickupReader` interface; no Cloud Tasks route, network access, database writes, scanner invocation or Standard 150 imports. Defaults `feature_enabled=False`, `verified_private_invoker=False`.
- Reads fresh server-owned `ScanRun`, `BusinessProject`, all owner's `Access` rows, isolated coordinator owner slot, immutable request receipt, and optional existing pickup claim. Missing/error/ambiguous records fail closed.
- Exact identity, attempt, canonical public-root target, immutable robots policy, paid `extended500_lifetime` Stripe provenance, app ID, signed grant integrity, coordinator fingerprint/receipt ID/task name, and state checks.
- Expired **120-second issuance grant is not considered a durable entitlement**: its HMAC identity may be used for queued work only when fresh paid Access, project, ScanRun and reservation still match. Grant issue age is capped at seven days (operator review needed).
- A valid read returns `ready_for_atomic_claim=True` but **`execution_allowed=False` in every case**. No crawl is permitted by this module. A separate atomic pickup-claim CAS transaction and fresh authority fencing must be implemented before execution.
- `scanner-api/tests/test_extended500_pickup_authorization.py`: 102 offline test cases covering revoked/pending/manual/owner-test/foreign/duplicate Access, stale slots, released receipts, replayed claim, superseded attempt, forged grant, changed project/target, task-body paid flag, missing reads, expired grant, duplicate task and service failure.

## Executed tests

From an isolated local copy of the new files plus the repository's existing `scanner-api/app/authority_seal.py` source:

```bash
cd scanner-api
python -m pytest -q tests/test_extended500_pickup_authorization.py
# 102 passed in 0.44s
python -m py_compile app/extended500_pickup_authorization.py
# success
```

These are **offline local tests**, not proof of actual Firestore, Cloud Run IAM or Base44 service-role behavior. The full repository suite was not available in the local runtime; GitHub PR CI must provide broader verification.

## Integrator-only work — do NOT enable this code as a working worker

1. Build private `/scan-job-extended500` route with Cloud Run IAM verified at deployment; validate invoker identity and queue provenance independently. The boolean argument alone is not an authentication mechanism.
2. Implement concrete fresh, service-authenticated Base44/Firestore `PickupReader` adapters. Fetch all owner Extended 500 Access records, including revoked and duplicates; do not use customer claims or cached access. Verify that `ScanRun` and `BusinessProject` reads are genuinely server-owned.
3. Implement a **transactional create-only pickup claim** in a distinct `extended500_pickup_claims/{receipt_id}` collection. The positive read-only verdict MUST NOT start work; two concurrent deliveries can both pass the reads. Transaction must fence attempt, owner slot, receipt and claim atomically, then ensure the claimed worker owns execution. No auto-expiry/reclaim of ambiguous in-flight jobs without a verified terminal state.
4. Resolve cross-system freshness: Base44 Access and ScanRun cannot be read atomically with Firestore owner slot. Design a revocation/fencing barrier and revalidation at claim/launch. A local fake is not a cross-service consistency guarantee.
5. Pin distinct signing root, dedicated queue path and trusted task-name source. Test actual JS issuer HMAC/Python parity in staging; verify exact deployed source SHA, IAM, OIDC audience and private queue.
6. Review the seven-day maximum task age against Cloud Tasks retry retention, operator recovery and customer SLA.
7. Dedicated bounded 500-page collector, signed reviewed persistence, source fingerprints and rollback remain required. Preserve Standard 150 untouched.

**Rollback:** delete the three lane-owned new files. No existing source imports them.

**No production changes:** no merge to `main`, deployment, Base44 publish, Cloud Tasks dispatch, Stripe mutations, customer scan or Standard 150 change.
