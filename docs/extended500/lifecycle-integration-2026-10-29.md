# Extended 500 private lifecycle integration — 2026-10-29

**Development candidate, NOT deployed, NOT commercial-ready.** This branch
assembles all six separate PRs (#388–#393) on PR #377 source and adds a
serialized seed/admission/pickup integration. Public Standard 150, production
release fingerprint, Base44 deployment and Stripe live settings are untouched.

## Source work implemented in this checkpoint

| Transition | Source / proof | Verified limitation |
| --- | --- | --- |
| Paid Access -> draft | #388 disabled $49 checkout/webhook; `extended500ScanRunDraft.js` + strict paid issuer | New live price intentionally INACTIVE; no paid sandbox end-to-end |
| Draft -> ScanRun | #389 `Extended500ScanRunSeeder`: one Firestore claim then exact Base44 proof; lost-response tombstone | Real Base44 create/query and cross-instance Firestore tests missing |
| SEEDED -> RESERVED | **NEW** `seed_admission_bridge.py` + `service.reserve_seeded` | Requires reconciled receipt + active seed slot inside SAME Firestore transaction; actual seeder output tested through coordinator, including lost-create recovery and 12-way contention |
| RESERVED -> ENQUEUED | Coordinator deterministic task + immutable receipt | Dedicated queue, worker and IAM not activated; dispatch remains disabled |
| ENQUEUED -> PICKUP CLAIMED | #391 fresh paid access/tenant reads; **NEW** `extended500_pickup_claim.py` CAS for one immutable claim | CAS only accepts `enqueued` (not `dispatch_unknown`), 12 simultaneous tasks produce one claim; **execution_allowed=false** |
| Pickup -> 500 collected | #390 isolated spawned 500 crawler; actual scanner logic in mocked 510-URL sample | No authenticated worker route or real site/runtime benchmark |
| COLLECTED -> REVIEWED | #393 signed unreviewed handoff, separate reviewer HMAC and authority HMAC | Actual trusted review engine not connected; reviewed_but_unreleased only |
| REVIEWED -> SIGNED PERSISTENCE | No 500 Base44 terminal proof issuer/writer yet | BLOCKED: never reuse Standard 150 persistence or declare complete based on unreviewed evidence |
| PERSISTED -> CUSTOMER REOPEN | No tenant-scoped 500 customer result read/reload yet | BLOCKED: must prove actual durable FixList and read after reload |

## Safety invariants

- No customer-visible 500 scan, public billing or Cloud Run trigger in this
  integration. New $49 product/price remain inactive.
- All ScanRun writes must come from server-side authority. A read-then-create
  Base44 request is NOT atomic. An unknown create outcome blocks automatic
  recreation until exact trusted reconciliation.
- An issued proof, even with a valid signature, must not reserve a job unless
  a committed seed receipt is observed in the **same Firestore transaction**
  that creates the admission receipt.
- No unseeded reservation bypass is permitted: `service.reserve` delegates
  to `reserve_seeded`, and the /reserve route calls the seeded variant.
- Pickup makes an immutable single-use receipt in Firestore only after fresh
  paid/owner/project/scan reads and exact queue task-name verification;
  UNKNOWN CAS means NO execution, and revocation can still race across Base44
  and Firestore. A separate revocation barrier is a release prerequisite.
- Review signatures never imply customer authority. The signing roots for
  collection, reviewer and terminal authority must remain distinct.
- No customer result is complete until the exact signed review, terminal
  persistence, ownership and customer reopened read have been verified.

## Verification requirements

Run local affected suites:
`pytest scanner-api/tests/test_extended500_seed_admission_bridge.py`
and `pytest scanner-api/tests/test_extended500_pickup_claim.py`
(with scanner-api as working directory); full FixList CI must pass from the
**exact** integration source copy. Because `.github/workflows/ci.yml`
listens only for PRs targeting main, use a disposable separate validation
branch with an isolated push trigger; DO NOT change release workflow or main.

Acceptance still requires real authenticated Base44 service-role create,
Firestore emulator + multi-instance contention, Cloud Tasks OIDC, runtime
budget under 500-page workload, separately trusted reviewer, signed Base44
persistence/tenant proof, explicit customer reopening, Stripe test-mode paid
checkout, full source fingerprint release, and rollback dry run.

**Status: PARTIAL, fail-closed.** No production GO, no deploy, no sale.
