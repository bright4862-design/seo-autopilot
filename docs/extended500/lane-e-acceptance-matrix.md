# Extended 500 — independent release-gate evidence matrix

Date: 2026-10-29. Scope: private source candidate on draft PR #377,
`002b84c9b6eaef78babec6081df150f31a000b11`; parallel isolated PRs
#388 (payment), #389 (atomic seed), #390 (collector). Review must refresh
live branch heads and use full CI checks before any integration.

This is **NOT** an approval to merge, deploy, sell, switch prices or claim a
customer 500-page job is possible. Standard 150 production incident #378
remains separate and unresolved unless proven otherwise.

| Phase | Source evidence | Status | Acceptance still required |
| --- | --- | --- | --- |
| USD $49 offer staged | New Stripe product `prod_VWxozdmSEe3iqm`, price `price_1UVtse4DcTLS57kiivKSCXKC`, inactive; PR #388 disabled checkout and webhook | IMPLEMENTED candidate | Test-mode Stripe payment-to-grant + webhook/replay/refunds; new price must remain inactive |
| ISSUED | `issueExtended500AdmissionV1`, `extended500EntitlementIssuer.js`, 120-s HMAC proofs | TESTED synthetic | Authenticated Base44 issuer + private signing keys + fresh Stripe-backed Access from trusted webhook |
| SEEDED | `extended500ScanRunDraft.js`; PR #389 isolated `scanrun_seed.py` | IMPLEMENTED candidate | Real Base44 create semantics and cross-instance Firestore CAS; unknown create outcome cannot duplicate |
| RESERVED | `extended500-admission/core.py` + mock Firestore adapter | TESTED synthetic | Real Firestore contention, exact seed receipt proof and isolated owner slot |
| DISPATCH_UNKNOWN -> ENQUEUED | `extended500-admission/service.py` deterministic Cloud Tasks route | TESTED synthetic | Dedicated queue provision, OIDC IAM, real unknown outcomes and quarantine checks |
| PICKUP_AUTHORIZED | `extended500_job_admission.py` preflight only | BLOCKED | Dedicated worker pickup route, fresh paid grant/slot/revocation read, deployed OIDC checks; issue #383 |
| COLLECTED | PR #390 isolated child `scanner.run_scan`, synthetic 510 -> 500 | TESTED synthetic | Live controlled performance/load/security/robot/resume, peak memory and worker time |
| REVIEWED | Existing unreviewed handoff is explicitly **not reviewed** | BLOCKED | Independent reviewed authority signer with proof of actual reviewed pages, findings and source release; issue #385 |
| TERMINAL | No Extended500 service-role terminal proof issuer | BLOCKED | Exact frozen attempt, signed reviewed persistence, terminal signed proof and no false complete |
| RELEASED | `core.decide_release` synthetic | TESTED synthetic | Real terminal CAS and late queued task/replay handling, owner slot recovery |
| CUSTOMER_REOPENED | No Extended500 signed FixList reader/deployed Base44 package | BLOCKED | Authenticated customer persisted FixList reload/history without 150 fallback |
| RELEASE CUTOVER | $49 Product swap issue #387; Standard150 checkout live | HOLD | Full-stage canary and explicit owner GO, cohesive source SHA/marker/price/webhook, auditable rollback |

## Independent negative test scope

`tests/frontend/extended500IsolationGate.test.mjs` is a **non-release
regression** ensuring that:

1. The public checkout/webhook still grant only Standard150.
2. Base44 ScanRun schema can represent 500 *without changing the Standard150
   default, admin-only writes or public 150 worker route*.
3. Wrong/unpaid/foreign/duplicate Access cannot authorize a private 500 draft.
4. Localhost, foreign owner and scoped URL cannot generate a queued draft.
5. Coordinator/issuer remain disabled without **explicit separate flags**.
6. The 500 unreviewed handoff cannot become customer authority by renaming its
   status; the Standard150 authority writer has no 500 handoff path.

Existing Python tests cover 12-way simulated owner-slot contention, replay
tombstones, and signed handoff acceptance. These are **not** a proof of actual
Firestore consistency, Cloud Tasks delivery, Base44 route deployment, or
Stripe webhook reliability.

## Stop-the-line defects / unresolved contracts

- **Schema alone does not authorize a job.** PR #389 seeder adapter must be
  integrated with Base44 and verified on a real staging project. A read-then-
  create race or a lost create acknowledgement is not a harmless retry.
- **Grant expiry/revocation.** 120-second signed issuer proofs may expire before
  a Cloud Task executes; pickup must fresh-read current owned Access and slot
  and reject revoked/superseded claims.
- **Mixed Standard150 + Extended500 Access rows.** Existing Standard150
  `findOwnedAccess` does not isolate different product plans; tests must cover
  coexistence before a commercial cutover.
- **Webhooks.** Standard150 webhook currently fails plan-mismatched events;
  event routing for separate 500 webhook must be verified without indefinite
  retries or unintended access grants. PR #388 local tests are not Stripe
  sandbox evidence. Need verified paid `checkout.session.completed` and
  `checkout.session.async_payment_succeeded`; async failure and refunds.
- **Future paid timestamp**: Access is trusted only because it is service-role
  data; a timestamp and checkout ID in Access are not themselves proof of
  Stripe settlement. Server-side webhook event verification is required.
- **Reviewer authority missing.** Cryptographically signing 500 raw pages
  does NOT demonstrate a complete review, valid repair priorities or verified
  fixes. No unreviewed raw handoff can authorize payment satisfaction.
- **Production incident #378**: Never lower the release fingerprint gate just
  to get a private 500 scan through. Standard150 runtime/prod alignment
  remains a separate gate.
- **Real HTTP/robots/429/performance unavailable** from synthetic fixtures:
  live gated staging tests must measure timeout, concurrency, memory and
  no cross-origin leaks.

## Integrator order

Review #389 and #388 (do not merge blindly) -> finish #383 pickup ->
test #390 private collector -> implement #385 review/persistence -> validate
cross-runtime proof -> separate authenticated result reader/reopen ->
sandbox Stripe end-to-end -> controlled owner canary -> explicit GO decision.

Maintain a single serialized integrator for any changes to
`extended500-admission/service.py`, `scanner-api/app/main.py`,
`base44/entities/`, shared release manifests, and public Standard150
checkout/webhook. Never merge this QA lane into `main` without the
integrator and full CI.
