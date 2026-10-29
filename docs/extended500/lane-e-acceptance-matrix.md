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

---

# Lane E executable evidence ledger (agent session, appended)

The owner-authored matrix above is kept verbatim. The ledger below maps each stage and gate to the
executable tests in `scanner-api/tests/test_extended500_release_negative_matrix.py` and
`tests/frontend/extended500IsolationGate.test.mjs`. Where the two disagree on status, the stricter
status applies.

**Verdict: NOT release-ready.** This is a candidate-blind QA ledger, not a release approval.
Every PASS below is an offline, mocked source-decision proof. None of it proves Firestore
serializability, Cloud Run IAM, Cloud Tasks delivery, Stripe behaviour, deployed bytes,
real-site performance or customer correctness.

- Candidate tested: draft PR #377 head `002b84c9b6eaef78babec6081df150f31a000b11`
  (`agent/extended500-collector-proof-20261026`). PR #377 CI at that head: both jobs green.
- Lane E files: `scanner-api/tests/test_extended500_release_negative_matrix.py`,
  `tests/frontend/extended500IsolationGate.test.mjs`, this document. No implementation,
  workflow, schema, Standard 150, payment or deployment file was changed.
- Other lanes (ScanRun seed, pickup authorization, private collector, reviewed authority) were
  **not** tested; their code is not on this head. Several REDs below are written so that they
  start passing (and, in pytest, fail strictly as XPASS) when those lanes land.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| IMPLEMENTED | Code exists on the candidate; no Lane E test beyond existing suites. |
| TESTED | Code exists AND a Lane E (or existing) offline test exercises the actual source. Mocked; not staging proof. |
| RED | Requirement is not met by the candidate. An executable test asserts the requirement and currently fails (pytest `xfail(strict=True, raises=AssertionError)`, node `todo`). |
| BLOCKED | Requirement cannot be met or proven until another listed item exists (no code, or needs infra). |
| UNVERIFIED | Needs staging/live proof that no offline test can give. |

No row is VERIFIED or DEPLOYED. The "Staging proof" column is empty for every row: **no staging
evidence exists for any Extended 500 behaviour.**

## Lifecycle matrix

| Stage | What must hold | Code path (candidate) | Lane E / existing test | CI | Staging proof | Status |
| --- | --- | --- | --- | --- | --- | --- |
| ISSUED | Only authenticated owner, owned queued `extended_500` ScanRun, matching project/domain, exactly one active Stripe-paid `extended500_lifetime` Access; issuer off unless exact `true`; no proofs/keys returned | `base44/functions/issueExtended500AdmissionV1/{handler,issuer}.js`, `src/lib/extended500EntitlementIssuer.js` | node `iss:*`, `own:*`, `iso: product entitlement matrix`, policy byte-parity; existing `extended500Base44Issuer`/`EntitlementIssuer` | frontend job | none | TESTED |
| ISSUED (precondition) | A real `extended_500` ScanRun can be created atomically (owner+request -> one scan id) | `src/lib/extended500ScanRunDraft.js` is pure prep only; no writer | existing `extended500ScanRunDraft` | frontend job | none | BLOCKED (no CAS seed service) |
| ISSUED (timeout) | Coordinator call is time-bounded so outcome-unknown is prompt | `handler.js` `fetchImpl(...)` has no signal/timeout | node RED-JS-6 | — | none | RED |
| RESERVED | HMAC-authenticated service call; both proofs verified with distinct roots; owner slot + immutable receipt in ONE transaction; exactly one winner per owner | `extended500-admission/service.py` `authenticate/verify_assertions/reserve`, `core.py` | py `iso_08`, `iso_09`, `own_01..03`, `chain_01`, `c_01..03`, `d_01`, `p_03` | scanner job | none | TESTED (offline OCC fake) |
| RESERVED (live atomicity) | Single winner under real Firestore contention | Firestore transaction semantics | py `c_04` (shows single-winner depends entirely on serializability), py RED `c_05` | — | none | RED / UNVERIFIED |
| DISPATCH_UNKNOWN | Network error/5xx/429/409 keep slot, never claim admission, retry uses the same task name; re-minted evidence replays same receipt; late failure never downgrades `enqueued`; post-enqueue write failure never reports success | `service.enqueue`, `update_dispatch_state`, `core.decide_dispatch_state` | py `q_01..q_05` | scanner job | none | TESTED |
| ENQUEUED | Dedicated `extended500-*` queue, own worker URL/OIDC, deterministic name; Standard 150 gateway refuses 500 tasks; queue provisioning dry-run by default, created PAUSED, never resumed | `service.enqueue`, `provision-queue.sh`, `dispatch-gateway/main.py validate_dispatch` | py `iso_07`, `q_06`, `q_07`, `chain_01` | scanner job | none | TESTED; real Cloud Tasks 409/dedup semantics UNVERIFIED |
| PICKUP_AUTHORIZED | Dedicated worker re-reads ScanRun + paid Access at pickup (grant may have expired while queued; queue retries up to 3600s) | only read-only `/scan-job-extended500-preflight` (returns `admitted:false`); `/scan-job-extended500` does not exist | py `g_01` (expired grant always refused; owner stays wedged), py RED `g_02` | scanner job | none | RED |
| COLLECTED | Real bounded 500 collector with measured runtime/RSS | synthetic `run_scan` 500 fixture only | existing `test_extended500_collector_proof.py` | scanner job | none | BLOCKED (no worker; no benchmark) |
| COLLECTED (handoff) | Unreviewed signed handoff: frozen identity, exact counts, allowlisted pages, never `complete` | `scanner-api/app/extended500_evidence_handoff.py`, `src/lib/extended500EvidenceHandoff.js` | py `f_01`, `iso_05`, `p_01`; node `f: the 500 verifier only ever stages...`; existing handoff suites | both jobs | none | TESTED |
| REVIEWED | New reviewed signed 500 authority + Base44 validator, sampling denominators | none | py RED `f_03` | — | none | RED |
| TERMINAL | Verified terminal-release issuer signs `extended500_verified_terminal_release_v1` | none (coordinator only verifies) | py RED `t_04` | — | none | RED |
| RELEASED | Release only with exact terminal proof from the terminal root; receipt is a permanent tombstone; late/duplicate release cannot touch a newer slot | `service.release_route`, `core.decide_release` | py `t_01..t_03` | scanner job | none | TESTED (no issuer exists, see TERMINAL) |
| CUSTOMER_REOPENED | Customer reader shows a reviewed 500 result, labelled, owner-scoped | none (`getCustomerScanResult*` are Standard 150) | node RED-JS-7 | — | none | RED |

## Cross-cutting gates

| Area | Requirement | Code path | Test | Status |
| --- | --- | --- | --- | --- |
| Isolation | Standard 150 `/scan-job` refuses non-`standard_150` task mode before any read | `main.py scan_job` | py `iso_01` | TESTED |
| Isolation | Standard 150 `/scan-job` refuses a **frozen** `extended_500` ScanRun (schema now admits it) | `scan_job.identity_matches` ignores `scan_mode` | py RED `iso_02` | **RED** |
| Isolation | Every Standard 150 signer refuses results declaring `extended_500` (even 3 pages) | `require_standard150_authority_capacity` | py `iso_03` (16 cases) | TESTED |
| Isolation | Standard 150 completion/limited signers refuse a frozen `extended_500` ScanRun when the result omits mode keys | `build_completion_envelope/limited` check only result modes | py RED `iso_04` | **RED** |
| Isolation | Standard 150 persistence refuses a completion for a frozen `extended_500` ScanRun | `persistDurableScanAuthorityV8 validateCurrentIdentity` | node RED-JS-4 (executes extracted function) | **RED** |
| Isolation | 500 handoff cannot be relabelled as a 150 completion (version gate + HMAC) | V8 `COMPLETION_VERSION` gate | py `iso_05`, node `f:*` | TESTED |
| Isolation | Public scanner budget/response never widen to 500 for `extended_500` | `resolve_scan_budget`, `enforce_scan_response_page_budget` | py `iso_06` | TESTED |
| Isolation | Coordinator refuses Standard 150 queues/targets and shared/short/missing roots | `service.py` import-time guards | py `iso_08` | TESTED |
| Isolation | 500 coordinator and 150 gateway HMAC domains never cross-verify (even with a shared root) | `service.authenticate`, gateway `_expected_signature` | py `iso_09` | TESTED |
| Isolation | 500 grant key cannot equal Standard 150 `SCAN_EVIDENCE_SIGNING_KEY` at runtime | preflight only checks length | py RED `iso_10` | **RED** |
| Isolation | Worker preflight refuses grants signed by any other root and 150 envelopes | `evaluate_extended500_preflight` | py `iso_11` | TESTED |
| Defaults | Coordinator, preflight, issuer all OFF by default; no Firestore write before both readiness gates | `service.py`, `main.py`, `handler.js` | py `w_01`, `w_02`, `f_02`; node `iss:*` | TESTED |
| Defaults | Standard 150 build/deploy configs never supply Extended 500 switches | `cloudbuild*.yaml`, workflows, Dockerfiles | py `w_03` | TESTED |
| Defaults | Switches enable only on exact `true` (README); Python uses `.lower()`/`.strip().lower()` | `service.py`, `main.py` | py RED `w_04` (3 cases); JS issuer is exact (node `iss:*`) | **RED** (low severity) |
| Privacy | 500 pages carry no raw HTML/main text/link cache/unknown fields; input not mutated | `project_pages_for_external_boundary` (top level) | py `p_01` | TESTED |
| Privacy | Nested content inside allowlisted fields (`geo_evidence`, `redirect_fetch_evidence`, `url_verification`) is not projected | same (non-recursive) | py RED `p_02` | **RED** |
| Privacy | Receiving JS verifier refuses signed pages carrying `main_text`/`html`/`raw_html`/`_reachability_links` | `verifyExtended500EvidenceHandoff` checks only url | node RED-JS-5 | **RED** |
| Privacy | Queue body/Firestore docs carry no access id, entitlement proof, keys or target URL | `enqueue`, `core.decide_reservation` | py `p_03` | TESTED |
| Results | Distinct 500 result storage/history/export, mode-aware acceptance gates (`acceptance-gates.mjs` fails > 150) | none | — | BLOCKED |
| Security | Cloud Run IAM private, OIDC audience verified by platform, Base44 route mounting, secret scoping | infra | — | UNVERIFIED |

## Payments

| Requirement | Code path | Test | Status |
| --- | --- | --- | --- |
| Correct $49 price (Standard 150): UI label, price id, webhook 4900 USD | `src/lib/access.js`, `createAccessCheckout`, `stripeWebhook` | node `pay: $49 ...`; existing `checkoutExactOnce` | TESTED (Standard 150 only) |
| Extended 500 price / SKU / checkout / verified paid webhook | none on candidate 002b84c (owner doc above: inactive $49 price staged in PR #388, not on this head) | node RED-JS-3 | **RED / BLOCKED** on this head |
| Verified paid checkout grants exactly once; replay and duplicate payment never re-grant; wrong amount/currency/unpaid refused | `stripeWebhook classifyPaidDelivery/assertPaidSession` | node `pay: webhook grants exactly once...` | TESTED |
| No unauthorized 500 grants: a paid session claiming `extended500_lifetime` is refused before any read/write; a Standard 150 grant never satisfies the 500 policy | `stripeWebhook`, `evaluateExtended500PaidAccess` | node `pay: a paid session claiming...`, `iso: product entitlement matrix` | TESTED |
| Grant duplication: two 500 Access rows (owner or email) fail closed; second access id cannot mint a second reservation | `evaluateExtended500PaidAccess`, `core.fingerprint` | node `own:*`, py `d_01`, `t_03` | TESTED |
| **Coexistence:** Standard 150 customer who also holds a 500 row keeps Standard 150 access | `startStandardScanJobV8/entitlement.js evaluatePaidAccess` (any 2nd Access row => `paid_access_conflict`) | node RED-JS-1 | **RED — release blocker** |
| **Coexistence:** paid Standard 150 webhook still grants when a 500 row exists | `stripeWebhook findOwnedAccess` (`rows.length !== 1` => 400 after payment); `createAccessCheckout` => 409 `duplicate_access` | node RED-JS-2 | **RED — release blocker** |

## Status counts (rows in the three tables above)

| Status | Count |
| --- | --- |
| TESTED | 21 (6 lifecycle, 11 cross-cutting, 4 payments) |
| RED | 16 rows (covering the 16 RED items below) |
| BLOCKED | 3 (CAS ScanRun seed, real collector/benchmark, results/acceptance gates) |
| UNVERIFIED | 1 dedicated row (infra security) plus every TESTED row for staging/live behaviour |
| IMPLEMENTED-only | 0 |
| VERIFIED / DEPLOYED | 0 |

(RED rows overlapping BLOCKED/UNVERIFIED — `c_05`, the 500 SKU — are counted once, as RED.)

## RED ledger (16 items)

Python (`scanner-api/tests/test_extended500_release_negative_matrix.py`, strict xfail, 12 test cases):

1. `iso_02` Standard 150 `/scan-job` starts/crawls a frozen `extended_500` ScanRun (`identity_matches` ignores `scan_mode`).
2. `iso_04` (2 cases) Standard 150 completion and limited signers sign for a frozen `extended_500` ScanRun when the result omits mode keys.
3. `iso_10` No runtime separation between `EXTENDED500_ADMISSION_SIGNING_KEY` and `SCAN_EVIDENCE_SIGNING_KEY`.
4. `c_05` No CI job runs the reservation contention test against the Firestore emulator.
5. `t_04` No verified terminal-release issuer; reserved slots can never be released in practice.
6. `g_02` No `/scan-job-extended500` worker with pickup-time durable re-authorization.
7. `f_03` No reviewed signed 500 authority protocol (Python builder + Base44/JS validator).
8. `w_04` (3 cases) Feature switches accept case-folded/space-padded `true` contrary to the README "exact true" contract.
9. `p_02` Nested private content inside allowlisted page fields crosses the signed handoff.

Node (`tests/frontend/extended500IsolationGate.test.mjs`, `todo`, real assertions executed, 7 tests):

10. RED-JS-1 Standard 150 entitlement locks out a paid 150 customer who also holds a 500 Access row.
11. RED-JS-2 Standard 150 webhook returns 400 `checkout_access_conflict` after a real payment when a 500 row coexists.
12. RED-JS-3 No Extended 500 SKU/checkout/paid webhook.
13. RED-JS-4 `persistDurableScanAuthorityV8 validateCurrentIdentity` accepts a frozen `extended_500` ScanRun.
14. RED-JS-5 `verifyExtended500EvidenceHandoff` accepts signed pages containing raw HTML/main text.
15. RED-JS-6 Issuer's coordinator fetch has no timeout/abort signal.
16. RED-JS-7 No customer reader for a reviewed `extended_500` result (CUSTOMER_REOPENED).

node `todo` is non-strict (an unexpected pass is not a CI failure); remove the `todo` option when an item lands.

## Proposed bounded patches for the serialized integrator (not applied)

- `scanner-api/app/scan_job.py`: in `identity_matches` and `require_standard150_authority_capacity`'s callers
  (`build_completion_envelope`, `build_limited_envelope`, `build_scan_attestation`), refuse when
  `scan.get("scan_mode")` is set and not in `("standard_150", "advanced")`. Fixes RED 1–2.
- `base44/functions/persistDurableScanAuthorityV8/entry.ts` `validateCurrentIdentity`: reject
  `scan.scan_mode` other than empty/`standard_150`/legacy. Fixes RED 13. **Standard 150 release + build-id regeneration required.**
- `scanner-api/app/main.py` preflight: 503 when the admission key equals `SCAN_EVIDENCE_SIGNING_KEY`. Fixes RED 3.
- Access coexistence (RED 10–11): either scope Standard 150 `evaluatePaidAccess`/`findOwnedAccess` to
  `plan_id === "standard150_lifetime"`, or (preferred, zero Standard 150 change) store 500 grants in a
  separate entity. Decide **before** any 500 Access row is ever written in production.

## Recommended minimal integration order

1. Cross-mode fences on Standard 150 (RED 1, 2, 13) and the Access-coexistence decision (RED 10, 11) — before the
   `extended_500` ScanRun enum or any 500 Access row reaches production.
2. Key separation + exact-true switches (RED 3, 8); issuer fetch timeout (RED 15).
3. CAS ScanRun seed service (BLOCKED) and Firestore-emulator contention CI (RED 4).
4. Terminal-release issuer (RED 5), then dedicated worker with pickup re-authorization (RED 6) — both together,
   otherwise paid owners are wedged in non-expiring slots (py `g_01`).
5. Real bounded collector + benchmarks; recursive privacy projection and receiving-side page checks (RED 9, 14).
6. Reviewed authority protocol + Base44 validator (RED 7), mode-aware acceptance gates and result storage.
7. 500 SKU/checkout/webhook (RED 12) and customer reader (RED 16) last; then private staging canaries.

## Safe rollback checklist

- [ ] `EXTENDED500_ISSUER_ENABLED` unset in Base44 (issuer returns 503 before any entity read).
- [ ] `EXTENDED500_ATOMIC_ADMISSION_ENABLED`, `EXTENDED500_QUEUE_DISPATCH_ENABLED`, `EXTENDED500_WORKER_READY` unset (not `TRUE`/`True`: those currently enable, RED 8).
- [ ] `FIXLIST_EXTENDED500_PREFLIGHT_ENABLED` and `EXTENDED500_ADMISSION_SIGNING_KEY` absent from the Standard 150 worker (py `w_03`).
- [ ] `extended500-*` Cloud Tasks queue paused (`gcloud tasks queues describe ... state: PAUSED`); never purge tasks of a reserved owner without a terminal record.
- [ ] Coordinator Cloud Run service scaled to zero / ingress internal; no public invoker.
- [ ] Firestore `extended500_owner_slots` / `extended500_request_receipts` exported before any manual repair; receipts are tombstones — never delete to "free" an owner.
- [ ] No `extended500_lifetime` Access rows exist (they break Standard 150 entitlement for that customer, RED 10–11).
- [ ] Standard 150 release manifest and generated build ids unchanged (`issueExtended500AdmissionV1` not listed).
- [ ] Revert to the previous ScanRun schema only if no `extended_500` row was ever created.

## Commands and results (local, offline, 2026-10-29)

| Command | Result |
| --- | --- |
| `cd scanner-api && python3 -m pytest -q -rxX tests/test_extended500_release_negative_matrix.py` | 91 passed, 12 xfailed |
| `cd scanner-api && python3 -m pytest -q tests/test_extended500_*.py` | 172 passed, 12 xfailed |
| `cd scanner-api && python3 -m pytest -q tests/` | 2646 passed, 18 skipped, 12 xfailed |
| `node --test tests/frontend/extended500IsolationGate.test.mjs tests/frontend/extended500*.test.mjs` | 42 tests: 35 pass, 0 fail, 7 todo (incl. 6 owner-authored gates) |
| `npm run test:frontend` | 2021 tests: 2014 pass, 0 fail, 7 todo |
| repo root `python3 -m pytest -q tests/` | 420 passed |

Local runtime was Python 3.11 / Node 22; CI uses Python 3.12 / Node 20.
