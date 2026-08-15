# FixList beta release — final engineering passover

**Prepared:** 2026-08-14  
**Target:** capped paid beta by Friday 2026-08-21  
**Current verdict:** **NO-GO for public payments or customer scans**

This report is the current source of truth. The longer
`docs/beta-release-handoff-2026-08-14.md` contains useful historical detail,
but its 342-test statement predates the unfinished server-owned ScanRun
migration described here.

## 1. Executive summary

The Standard 150 scanner has credible production evidence and its crawl,
discovery, scoring, review, and authority-eligibility logic was deliberately
left unchanged. The local candidate contains substantial customer-release
hardening: persisted duplicate suppression, sealed customer result projection,
invite-only checkout controls, payment activation recovery, safer UI copy,
release provenance checks, and the beginning of server-owned scan admission.

The repository is currently in the middle of the ScanRun ownership migration.
The new focused admission protocol passes its tests, but the complete frontend
gate is **344/351**, with seven older static contract tests still asserting the
browser-owned design. The admission path is default-off and must remain so
until Base44's conditional mutation is proven atomic and contention-tested.

Do not deploy this dirty tree as-is. Do not claim beta GO. The safe Friday
fallback is a manually invited cohort of at most 25 exact users, with checkout
and scan admission default-off until the complete release gate passes.

## 2. Repository state

- Repository: `/Users/elizabethnguyenson/Documents/GitHub/seo-autopilot`
- Branch: `beta`
- Pre-change HEAD: `5c53aaf484626f594a9babc0a109c6e2d69a182c`
- Dirty paths: **51** modified/untracked paths, including this final report
- Tracked diff: **30 files, 2,084 insertions, 517 deletions**
- State: local, uncommitted, unpushed, undeployed
- No traffic, queue, gateway, worker, key, Stripe, or production entity state
  was changed during this hardening wave.

Preserve the entire worktree. Do not reset, checkout over, or discard files.

## 3. Non-negotiable scope

- Standard 150 remains the only customer scanner.
- Preserve large-site discovery and the 150-page crawl behavior.
- Do not change crawler discovery, scoring, classification, review thresholds,
  or `isAuthorityEligible`.
- Do not enable Grok or Premium 5,000.
- Do not loosen an authority gate to make a test or scan pass.
- Do not rotate or synchronize signing keys without a separate reviewed need.
- Do not run a customer scan before the exact release candidate is deployed and
  verified.

## 4. What is implemented locally

### Persisted duplicate suppression

`persistDurableScanAuthority/authoritySnapshot.js` now suppresses a page-level
action only when a same-rule family action explicitly covers that page. The
deduplication runs before counts, top-action IDs, proof/HMAC generation, and
persistence. The captured Ike's Sandwiches fixture contracts from 36 duplicate
rows to four distinct actions while preserving uncovered outliers.

This changes saved-result normalization, not scanner crawl or scoring logic.

### Sealed paid-result boundary

- `FixList` and `FixItem` schemas are admin/service-role only locally.
- `getCustomerScanResult` performs owner, project, domain, entitlement,
  authority-marker, relationship, count, fingerprint, and HMAC checks.
- Locked users receive progress metadata and no paid FixItems.
- Browser history uses the same bounded server projection and no longer reads
  ScanRun directly for result/history display.
- Raw debug payloads, proof material, owner IDs, and internal result IDs are not
  projected to customers.

The boundary is incomplete until ScanRun creation/mutation is fully server
owned and compatible entity rules are deployed as one release unit.

### Safe invite-only checkout posture

- `BETA_CHECKOUT_ENABLED` defaults off.
- `BETA_CHECKOUT_GENERATION` is mandatory when enabled.
- `BETA_COHORT_ALLOWED_USER_IDS` must contain 1–25 unique exact user IDs.
- Checkout never creates Access rows.
- Every invited user must have exactly one pre-provisioned pending Access row
  bound to the exact owner ID and email.
- Concurrent first checkout retries converge on one user/generation/session
  Stripe idempotency key.
- Webhook processing is replay-safe and revoked access is protected.
- The UI suppresses repeat purchase calls while activation is pending.

This supports a controlled invite-only cohort. It is not a safe public
first-come 25-seat allocator.

### Customer UX and recovery

- Honest one-time USD 50 Standard 150 beta wording.
- No false free/no-card language.
- Grok navigation removed; Premium remains unavailable.
- Paid-return activation polling and safe retry state.
- Saved scan rediscovery with customer-safe failure classifications.
- Opaque support references that exclude owner/request/proof data.
- Funnel events for checkout, payment return, access activation/delay, and scan
  acceptance. `result_viewed` and `fix_opened` are declared but not wired.

### Release provenance

- Cloud Build now fetches the claimed Git SHA, compares the submitted scanner
  build inputs to that commit, prints the verified `main.py` hash, and builds
  from a fresh commit archive.
- The Base44 release manifest covers six critical function packages and three
  authority schemas: `ScanRun`, `FixList`, and `FixItem`.
- The post-deploy verifier requires function and entity directories from the
  same fresh authenticated Base44 pull.

These checks are implemented locally but have not been exercised against a
fresh deployed candidate.

## 5. ScanRun migration — exact current state

New files and principal changes:

- `base44/functions/startStandardScanJob/admission.js`
- `base44/functions/startStandardScanJob/entry.ts`
- `base44/entities/Access.jsonc`
- `base44/entities/ScanRun.jsonc`
- `src/components/scan/ScanWebsiteForm.jsx`
- `tests/frontend/scanAdmissionLease.test.mjs`
- `tests/frontend/serverOwnedScanAdmission.test.mjs`

Implemented protocol:

- `BETA_SCAN_ADMISSION_ENABLED` defaults off.
- `BASE44_ATOMIC_UPDATE_MANY_CONFIRMED` must be exactly `true` to enable it.
- An Access-row lease records claim token, request ID, fingerprint, canonical
  ScanRun ID, and expiry.
- Same-request contenders reuse/wait for one winner.
- A different request for an active owner receives a bounded busy response.
- A conflicting fingerprint cannot reuse a request ID.
- Only the winning token can bind the canonical server-created ScanRun.
- The browser's new path sends project/request/target context and receives the
  canonical ScanRun ID from `startStandardScanJob`.
- ScanRun RLS is changed locally to admin-only CRUD.

The handler temporarily accepts the legacy caller-supplied `scan_id` path for
deployment/cache compatibility. This dual mode is migration code, not the final
security boundary.

### Why it is not ready to enable

1. Base44 documents Mongo-style conditional `updateMany`, but the inspected
   documentation does not promise transaction/CAS/linearizable semantics. An
   environment variable named “confirmed” is only a fail-closed switch; it is
   not evidence.
2. A different request can remain busy for the full 20-minute lease after the
   previous ScanRun has already terminalized. Add a conditional terminal-row
   reclaim path.
3. If Base44 creates the ScanRun but the following update response is lost, the
   recovery path may find a queued row with blank `scan_id`. Normalize that row
   to its canonical entity ID before binding/enqueue and test the partial
   failure.
4. `ScanWebsiteForm.jsx` still contains an unreachable synchronous fallback
   block and imports browser terminal mutation helpers. Remove that dead block
   so the active browser boundary is unambiguous; do not alter scanner logic.
5. Legacy functions including `aiReviewScan`, `runAdvancedScan`,
   `runStandard150Scan`, `persistScanAuthority`, and `grokChat` still contain
   caller-context ScanRun reads. Determine whether each is dead/disabled or
   migrate it before claiming a repository-wide server-only boundary.
6. Admin-only ScanRun RLS and a cached old frontend are incompatible. Define and
   rehearse a compatible deployment sequence; never deploy the schema alone.

If Base44 will not explicitly guarantee atomic conditional single-row mutation,
use an authorized transactional/SETNX coordinator. Do not approximate exact
admission with query-then-create or process memory.

## 6. Fresh verification at passover

Run on 2026-08-14 with the bundled Codex Node runtime:

- Complete frontend contracts: **351 total, 344 passed, 7 failed**
- Focused admission contracts: **6/6 passed**
- TypeScript no-emit: **passed**
- Function-package portability/closure verification: **passed for all six**
- `git diff --check`: **passed**

The seven failures are migration assertions, not hidden scanner-output
failures. They must still be reviewed and updated to enforce the new contract:

1. `asyncStandardScanJob.test.mjs` — exact owner-bound identity end to end
2. `durableReleaseIntegrity.test.mjs` — deployment contract lists every new env
3. `durableScanModel.test.mjs` — new lease fields and admin-only ScanRun rules
4. `durableScanModel.test.mjs` — durable entity ownership model
5. `durableScanModel.test.mjs` — tenant input/server-only create expectations
6. `scanRunIdentity.test.mjs` — server, not browser, creates the ScanRun
7. `twoScannerProductContract.test.mjs` — remove old `beginScanRun` assertion

Do not simply delete assertions. Rewrite them to prove: no browser-supplied
scan ID, no browser ScanRun CRUD, server-created canonical identity, admin-only
ScanRun/FixList/FixItem, deterministic same-request replay, and fail-closed
admission configuration.

Full ESLint passed before the latest admission slice but was not rerun after
it. The Vite production build remains locally blocked before compilation by a
macOS native Rollup Team-ID signature issue; use the remote build or a clean
trusted toolchain rather than destructively reinstalling this worktree.

## 7. Production evidence and current live posture

Last recorded worker state, to be re-verified before release:

- Revision: `fixlist-standard150-worker-00009-2pz`
- Claimed SHA: `d2ed725c57f15628d80f494387b0777dd38cc7bb`
- Image digest:
  `sha256:a2d6c1f31b500895e1a19a910b662ba23420136d06cf30dddb1b064a5c26f2cd`
- Cloud Build: `71838abf-87ba-4846-8379-44ab4d81b9a2`
- Timeout/concurrency: `480s` / `1`
- Authority fingerprint: `5caec7fdcabceee7`

Useful historical evidence:

- Norris Wines produced an authoritative saved result.
- The earlier matrix produced 10 authoritative outcomes from 11 sites; Malt
  was a correct release-gate rejection rather than infrastructure failure.
- Ike's Sandwiches completed authoritatively with 163 URLs found and 150
  crawled, but its saved result exposed 36 duplicate rows representing four
  actions. The local authority-snapshot fix addresses this.

Live Base44 entity rules were previously inspected read-only and still allowed
owner CRUD on ScanRun/FixList/FixItem. Therefore the local sealed entity rules
are not deployed. Historical successful scans do not constitute acceptance of
the current local candidate.

## 8. Remaining release blockers

### P0 — Finish and prove server-owned ScanRun admission

Resolve the six issues in section 5, obtain the atomicity guarantee or choose
an external coordinator, add real concurrent sandbox tests, and restore the
complete local gate.

### P0 — Deploy and prove invite-only payments

Keep checkout off while configuring one generation, at most 25 exact user IDs,
and exactly one pending Access row per invited owner/email. Prove concurrent
checkout, webhook replay, activation, revoked access, duplicate paid-session
refund/incident handling, and the purchase-pause control in Stripe test mode.

### P0 — Legal, support, deletion, and fair-use facts

The owner must provide legal/operator identity, required address/country,
public support destination, refund/cancellation terms, retention/deletion
terms, tax wording, beta-change wording, and an enforceable fair-use limit.
Engineering must not invent them.

### P0 — Monitoring and deployed acceptance

Provision/verify alerts for gateway/worker errors, queue age, stuck jobs, retry
exhaustion, authority rejection, and payment activation. Prove rollback and the
purchase kill switch. Then complete one paid owner-bound production journey on
the exact reviewed candidate before any matrix run.

## 9. Required execution order

1. Preserve and review the dirty worktree.
2. Finish the server-owned ScanRun migration without touching scanner logic.
3. Obtain Base44 atomicity evidence plus a real two-client contention test, or
   obtain authorization for an external transactional coordinator.
4. Rewrite the seven stale contract tests and add partial-failure, terminal
   lease-reclaim, cross-owner, direct-entity-negative, and cached-client tests.
5. Run all 351+ frontend tests, TypeScript, full ESLint, manifest tests,
   `git diff --check`, and a trusted production build.
6. Obtain a second code/security review, then commit and push the reviewed
   candidate. The provenance build intentionally rejects an unpushed dirty
   filesystem masquerading as a Git SHA.
7. Deploy functions, frontend, and entity rules as a rehearsed compatible
   release unit. Keep checkout and admission switches off initially.
8. Pull the deployed Base44 functions and entities with authenticated CLI and
   compare all six function packages and three entity schemas byte-for-byte.
9. Run negative direct CRUD checks and verify the exact Cloud Run revision,
   image, SHA, config, IAM, queue, alerts, and rollback target.
10. Enable only the controlled invite cohort and run one complete paid journey:
    registration → checkout → one entitlement → Standard 150 → authoritative
    saved result → refresh/relogin.
11. If and only if that passes, run the frozen 20-site matrix.
12. Make the capped-beta go/no-go decision from the retained evidence bundle.

## 10. Proposed 20-site matrix

Freeze the exact URLs before starting. The owner explicitly requested
Funbooker, Norris Wines, Center Street Lending, Meilleurtaux, and Pretto. A
balanced 20-site set is:

1. `funbooker.com`
2. Norris Wines — **confirm exact URL**
3. `centerstreetlending.com`
4. Meilleurtaux — **confirm exact URL**
5. `pretto.fr`
6. `papernest.com`
7. `selectra.info`
8. `malt.fr`
9. `ornikar.com`
10. `legalstart.fr`
11. `captaincontrat.com`
12. `wecasa.fr`
13. `jestocke.com`
14. `qonto.com`
15. `alan.com`
16. `yousign.com`
17. `spendesk.com`
18. `kiavi.com`
19. `deathwishcoffee.com`
20. Ike's Sandwiches — **confirm exact URL**

Record every ScanRun/FixList ID, release marker, pages found/crawled, backend,
fallback flags, authority state, duplicate result, duration, and terminal
status. A correctly explained evidence-limited result such as Malt can be a
valid negative control. Infrastructure failure, fallback, cross-owner leakage,
page-cap breach, equivalent persisted duplicates, or a stuck run is a failure.

## 11. Beta GO criteria

All of the following must be true:

- complete local and remote gates green;
- deployed code/schema digests match the reviewed commit;
- no browser ScanRun CRUD and negative tenant-boundary tests pass;
- admission atomicity is documented and contention-tested;
- checkout/scan kill switches work and the cohort is capped at 25 exact users;
- one payment creates exactly one entitlement;
- one fresh production Standard 150 scan saves an authoritative result with
  Python scanner/review markers and no fallback;
- refresh/relogin recovers that exact owner-bound result;
- fresh Ike result has no equivalent persisted duplicates;
- monitoring and rollback are proven;
- legal/support/deletion/fair-use surfaces are approved and public;
- the frozen 20-site matrix completes against the exact release candidate.

Until then the truthful state is **candidate / invite-only / NO-GO for public
payments**, not beta GO.

## 12. Copy/paste continuation prompt

> Continue FixList beta hardening from
> `docs/FINAL-PASSOVER-2026-08-14.md` in
> `/Users/elizabethnguyenson/Documents/GitHub/seo-autopilot`. Preserve the 51
> dirty paths and start read-only. The local gate is 344/351; the six focused
> server-admission tests pass, but the migration is incomplete and default-off.
> Do not change Standard 150 discovery, crawl, scoring, review, page cap, or
> `isAuthorityEligible`; do not enable Grok/Premium; do not deploy, push, change
> traffic/queues/keys, enable payments, or run customer scans without explicit
> authorization. First remove the dead browser terminal fallback, close
> terminal lease reclaim and create/update partial-failure recovery, audit the
> remaining caller-context ScanRun functions, and rewrite the seven stale tests
> to enforce server-owned canonical ScanRun identity and admin-only CRUD. Do
> not enable scan admission merely because
> `BASE44_ATOMIC_UPDATE_MANY_CONFIRMED=true`; obtain a Base44 atomicity guarantee
> and real sandbox contention evidence, or request authorization for an
> external transactional/SETNX coordinator. Restore the full local gate, get a
> second review, then follow the compatible deploy, authenticated inventory
> comparison, one paid acceptance, Ike duplicate regression, and frozen
> 20-site matrix sequence. Do not claim beta GO before all P0 criteria pass.
