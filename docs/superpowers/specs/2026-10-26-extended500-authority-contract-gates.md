# Extended 500 authority and product-contract gates — source audit

Status: **private R2 proof only; no end-to-end 500 product or deployment.**
Baseline: `main` `cd9d4ff562d6aad3cc7ecce059fa12f8d4098db2`, inspected 2026-10-26.
Working branch: `agent/extended500-collector-proof-20261026`, draft PR #377.
Paired Standard 150 backfill: PR #376; independent implementation and rollout.

## Verified in GitHub CI

- Synthetic private `scanner.run_scan` with test-only 500 budget retained exactly 500 distinct HTML page objects from 510 discovered fixture URLs.
- Live published `advanced` cap remains 150; `extended_500` is not an admitted public or worker mode.
- B11 reachability has explicit 500-page scope only under `max_assessed_pages=500` and default 150 rejects 151. B10/B11 helper evidence accepts 500 only when caller opts in; fails at 501, rejects mixed-mode provenance. No helper asserts sitewide orphaning from observed sample links.
- The 150-page review/HMAC builders now explicitly refuse an oversized result or reported count before signing; a forged 150 count cannot conceal a 500-object page array. 500-page private page projection uses the positive external allowlist and strips internal main-text, raw links and unknown future fields.
- The above are fixture assertions and repository CI. They do not measure live site speed, Cloud Run peak RSS, result storage sizing, review wall time or actual customer correctness.

## R3 development slice: signed, unreviewed evidence handoff (2026-10-26)

The branch adds `scanner-api/app/extended500_evidence_handoff.py` and the
pure `src/lib/extended500EvidenceHandoff.js` validator. This is **not** wired
into a customer API or any of the release-sensitive Base44 function packages.

- Frozen ScanRun must explicitly name `extended_500` with owner, project,
  scan, request, idempotency and attempt identifiers. The result must carry
  matching `scan_mode` and `canonical_mode`.
- Review status is always `not_reviewed`, `pages_reviewed=0`, and
  `release_gate_eligible=false`. A signed collection is not a published fix list.
- 1–500 retained page objects, exact mirrored page arrays, unique retained
  destination identity, truthful `pages_crawled`, `pages_found` and typed
  `scan_coverage` counts. No implied guarantee that 500 pages are available.
- Project pages through the existing positive external allowlist; raw main text,
  raw link cache and arbitrary new producer fields are not signed.
- The evidence envelope uses a distinct `extended500_evidence_handoff_v1_unreviewed`
  version and the existing canonical HMAC-SHA256 implementation. Python-generated
  full 500-page data is verified with JavaScript in a cross-runtime integration test.
- Source SHA (40 hex) and beta fingerprint (16 hex) are signed, but their actual
  match against the deployed worker requires separate operator/runtime verification.
- An explicit 8 MiB signing budget is a **development safety bound**, not a
  benchmarked production payload limit. Exceeding it fails rather than truncating.
- The older Standard 150 signing path also now rejects `extended_500` mode
  even when a legitimate short 500-tier crawl retains fewer than 150 pages.
- An initial attempt placed the verifier inside
  `base44/functions/persistDurableScanAuthority`, which triggered the generated
  package-build-ID gate. It was moved to `src/lib` so the production Standard 150
  Base44 package and its generated build ID remain unchanged.

**Next stage, still unimplemented:** explicit authenticated Extended 500 durable
admission/dispatch and a new *reviewed* authority persistence protocol. This
must read the fresh server-owned ScanRun, verify entitlement and source identity,
preserve CAS/attempt fencing, and bind evidence count vs review coverage before
allowing any completion or customer billing. Do not reuse the unreviewed handoff
as a `complete` envelope.

## R3 continuation: isolated 500 job preflight (2026-10-26)

The worker branch adds `scanner-api/app/extended500_job_admission.py`
and a **default-disabled, read-only**
`POST /scan-job-extended500-preflight` route. It is **not**
`/scan-job`, does not accept `standard_150`, and contains no
`run_scan`, `mark_scan_started`, queue, customer write, entitlement
charge or completion call. Even a fully verified request returns
`admitted: false, execution_enabled: false`.

- The route first uses `require_cloud_tasks_oidc()`, whose trust model
  relies on private Cloud Run IAM doing actual signature/audience checks.
  Deployment of this endpoint to a public Cloud Run service is prohibited:
  the application-level JWT check alone is forgeable.
- A separate `FIXLIST_EXTENDED500_PREFLIGHT_ENABLED=true` is required to
  read the persisted ScanRun at all. The Standard 150 deployment contract
  documents that this flag and the separate
  `EXTENDED500_ADMISSION_SIGNING_KEY` are **not supplied** to production.
- Policy compares the fresh stored `ScanRun` to every required task claim:
  explicit `extended_500` mode, queued state, owner, project, scan,
  request and idempotency IDs, exact 1-based integer attempt, website and
  path scope, and immutable robots policy. It never uses the legacy
  Standard-150 helper's compatibility behavior where some blank
  identities may match.
- Separately signed HMAC grant with exact `extended500_preflight_grant_v1`
  version, audience `fixlist_extended500_worker`, same task identity,
  and a maximum 300-second validity interval. Signature is checked with
  `hmac.compare_digest`; the grant key is distinct from the Standard
  150 evidence signing key.
- No grant issuer exists in production. A browser-supplied grant is not
  trusted without independently verified signing and the fresh ScanRun
  match. A valid grant plus read-only preflight is NOT an atomic claim and
  cannot prevent duplicate worker execution.
- The existing route authentication inventory and deployment variable
  registry explicitly cover the new route and both feature-off variables.
  Synthetic adversarial tests exercise expired, future, mismatched, forged,
  replayed, wrong-mode and malformed grants; both disabled and enabled
  preflight paths are tested with mocked durable reads, asserting **no
  crawl or persistence call**.

Remaining prerequisites for **actual** execution, in required order:
(1) independent server-side Extended 500 entitlement issuer with grants
bound to the owner and plan; (2) atomic CAS claim/queue isolation plus
idempotency and attempt fencing; (3) resource-bounded real 500 collector
adapter with measured runtime; (4) new reviewed signed persisted-authority
protocol with Base44 validator and release fingerprints; (5) measured staging
canaries, operator rollback and explicit customer authorization.

## 2026-10-27 Base44 server-authenticated issuance and CAS isolation slice

Implemented in **draft branch PR #377, not published or deployed**:

- Standalone Base44 package
  `base44/functions/issueExtended500AdmissionV1/{entry.ts,handler.js,issuer.js,authoritySeal.js}`.
  It is **not** part of the Standard 150 release manifest. Uses the signed-in
  `base44.auth.me()` identity and service-role reads of `ScanRun`,
  `BusinessProject` and `Access`. The only browser input is exact
  `scan_id`; rejects browser-supplied owner, plan, grant, mode, URL or attempt.
  Owner/project/host/frozen mode/attempt must match before considering access.
- Paid-only Extended 500 entitlement policy: exactly one own, active,
  Stripe-checkout `extended500_lifetime` Access record. Existing Standard 150
  paid Access rows may coexist but cannot authorize the 500 path; pending,
  manual, owner_test and conflicting records are rejected.
- Base44 issues two independent signed assertions with a 120-second bounded
  lifetime, then directly HMAC-signs the complete reservation request
  using the **distinct** `fixlist-extended500-atomic-admission-v1` domain
  and calls the private Cloud Run coordinator. No grant or signing root is
  returned to the caller. HTTP timeout is explicitly `outcome_unknown`.
- `tests/frontend/extended500Base44Issuer.test.mjs` mocks Base44 and validates
  owner/project/entitlement rejection paths, disallows client assertions,
  checks signatures against an independent Node HMAC implementation and
  checks refusal when the coordinator falsely claims execution is active.
  Existing Python-to-JavaScript proof verification remains covered.
- The isolated coordinator now **refuses a new Firestore owner-slot reserve**
  unless BOTH `EXTENDED500_QUEUE_DISPATCH_ENABLED` and
  `EXTENDED500_WORKER_READY` are exactly true, in addition to the
  independent atomic-admission gate. Both default OFF. The queue is not
  provisioned and the worker target is not yet implemented. Tests assert
  blocked dispatch cannot create a durable owner slot.
- **Schema blocker verified from source**:
  `base44/entities/ScanRun.jsonc` `scan_mode` enum does **not** include
  `extended_500`. Therefore none of this authorizes creating an actual
  Extended 500 ScanRun today. A separately reviewed schema migration and
  a service-owned job creation path are prerequisites. No change to the live
  Standard 150 schema has been made.
- `base44/entities/Access.jsonc` RLS restricts create/update/delete to
  administrators; customer reads are owner-scoped. This does not establish
  an Extended 500 Stripe SKU or paid webhook, which still needs separate
  design and verification.

**Not yet proven:** deployed Base44 package identity, private service IAM,
Firestore cross-instance serializability under contention, Cloud Tasks
delivery/replay during unknown outcomes, dedicated worker pickup-time recheck,
reviewed 500 result storage, release gates or real-site performance. A green
mocked CI suite only verifies the exercised source paths.

## Known remaining hard contract blockers

| Surface | Observed source behavior | Required change before enabling 500 |
| --- | --- | --- |
| Scanner public mode | `scanner.py` `advanced` = 150, unknown mode also resolves to advanced | Explicit internal `extended_500` budget with server-owned admission and no customer override |
| Durable worker | `main.py` `/scan-job` accepts only `standard_150`; dispatch-gateway also rejects nonstandard | New authenticated task mode, identity, replay fences, quota/entitlement and queue isolation |
| Worker timeout | `scanner.py` job crawl capped at 120s, outer wall at 135s | Benchmark and redesign/batch if 500 does not fit; do not simply increase timeouts |
| Response | `main.py` `enforce_scan_response_page_budget` clips advanced to 150 | Separate verified 500 response/summary projection preserving exact counts |
| Stage 2 | B10/B11 pure helper limit now opt-in 500; other producers/orchestrators remain audited only for 150 | Track all producers and aggregated evidence, validate CPU/memory and scope |
| Review | `review.py` site fingerprint uses `pages[:220]` in several paths | Define 500 sample policy and whether 220-page fingerprint suffices, with honest `sampled` counters |
| Review envelope | `scan_job.py` Standard 150 envelope declares `standard_150`, sends at most 60 pages and 100 findings | Version a distinct 500 authority review contract that differentiates all crawled from sampled/reviewed, never reuse Standard 150 signed completion |
| Signed storage | `scan_job.py` completion and limited contracts use Standard 150 versions; Base44 persistence/JS authority validates them | New signed mode/version, canonical serialization parity, source SHA, CAS, idempotence, compensation and replay tests |
| Frontend | `src/lib/scanRunModel.js`, `src/lib/scanStorageRecovery.js`, ScanWebsiteForm, billing still Standard 150 | Explicit feature-gated 500 plan, correctly labeled result/history/progress/export and entitlements |
| Customer release | `scripts/acceptance-gates.mjs` fails if `pages_crawled > 150` | Mode-discriminated acceptance gates retaining all existing Standard 150 fixtures |

## Formal invariants for R3/R4

1. A Standard 150 signed payload cannot contain or claim over 150 assessed pages regardless of frontend aliases or forged count.
2. A 500 signed payload, when introduced, must carry a new authenticated canonical mode distinct from Standard 150; same scan identity/mode invariant across signed task, scanner, reviewer and storage.
3. `pages_found` is a discovered inventory, `urls_attempted` is attempted fetches, `pages_crawled` is distinct retained destinations, `usable_html_pages` is accepted HTML, `sampled_pages_sent_to_review` is a bounded sample. Never substitute one for another.
4. A 500 page assessment or a 60-page review sample is *not* 500 reviewed pages by implication. Authoritative findings require observed evidence and a clear sampling denominator.
5. Distinct HTTP final destination identity and robots/scope/SSRF/rate limiting remain unchanged. 429 is never bypassed by increasing retry or concurrency.
6. Standard 150 replay and existing signed snapshots remain compatible byte-for-byte; new mode cannot consume a Standard 150 entitlement.
7. Real-site staging must measure completion, processing time, peak RAM, response and stored payload bytes, 429 behavior, error fractions and rollback. No invented throughput or `p95` threshold.

## Rollout decision

PR #377 remains a **draft test/proof branch**. Even with green CI, it is insufficient to merge/deploy as a public 500 feature. The next coherent engineering slice is an authenticated Extended 500 durable ingress **paired with** a new end-to-end signed review/persistence contract, or else a separate fixture-only design without bypassing any existing 150-page guards. No production activation absent operator approval and canary evidence.
