# FixList paid-beta handoff — 2026-08-14

> **Superseded for continuation:** use
> `docs/FINAL-PASSOVER-2026-08-14.md`. This longer report predates the
> in-progress server-owned ScanRun admission migration and its 342/342 test
> statement is no longer current.

## Executive verdict

**Current verdict: NO-GO for public payments.**

The Standard 150 scanner itself is credible and its crawl/discovery/review logic
has deliberately not been changed. A substantial customer-release hardening
wave is implemented **locally and uncommitted**, with **342/342 frontend tests
passing**. The remaining blockers are the server ownership of `ScanRun`, proven
atomic scan/checkout admission, a 25-seat purchase pause/cap, public
legal/support/deletion surfaces, production monitoring, and a fresh deployed
acceptance run plus the 20-site matrix.

Target posture remains a **capped 25-customer paid beta by Friday 2026-08-21**.
If any P0 below remains open, publish a waitlist and keep payments/scans
invite-only. Do not claim beta GO from local tests.

## Repository and release state

- Repository: `/Users/elizabethnguyenson/Documents/GitHub/seo-autopilot`
- Branch: `beta`
- Pre-change local HEAD: `5c53aaf484626f594a9babc0a109c6e2d69a182c`
- Current changes: 42 modified/untracked paths at handoff freeze;
  **not committed or pushed**
- No Base44 deploy, entity push, Cloud Run deploy, traffic change, queue change,
  signing-key change, payment test, or fresh customer scan was performed in this
  hardening wave.
- Scope: Standard 150 only. Grok and Premium 5,000 remain disabled.
- Strategic roadmap: `docs/beta-customer-release-roadmap.md`. Where its progress
  statements differ, this handoff is the newer source of truth.

## Status at a glance

| Release area | State | Passover meaning |
|---|---|---|
| Standard 150 crawl/review | Production evidence exists; logic frozen | Do not redesign it or loosen authority eligibility |
| Sealed duplicate suppression | Implemented and locally verified | Not deployed; repeat Ike only after the complete candidate is live |
| Paid result projection | Implemented locally for FixList/FixItem | Incomplete until ScanRun itself is server-owned |
| Customer recovery errors/history | Implemented and locally verified | Browser and deployed E2E remain pending |
| Checkout retry/webhook ordering | Hardened locally | Concurrent first checkout remains unsafe |
| 25-seat cap and purchase pause | Not implemented | Public first-come payments remain blocked |
| Public policies/support/deletion | Blocked on founder facts | Do not invent legal identity, email, or refund terms |
| Release package/provenance checks | Implemented locally | Must be exercised against a fresh deployed Base44 pull |
| Monitoring and final acceptance | Not complete | No beta GO until deployed paid acceptance and matrix |

Last recorded production worker state, which must be re-verified before any
release action:

- Service revision: `fixlist-standard150-worker-00009-2pz`
- Claimed source: `d2ed725c57f15628d80f494387b0777dd38cc7bb`
- Image digest: `sha256:a2d6c1f31b500895e1a19a910b662ba23420136d06cf30dddb1b064a5c26f2cd`
- Cloud Build: `71838abf-87ba-4846-8379-44ab4d81b9a2`
- Timeout/concurrency: `480s` / `1`
- Authority fingerprint: `5caec7fdcabceee7`

## Production evidence already available

- Norris Wines produced a fresh authoritative saved result.
- The first matrix produced 10 authoritative outcomes from 11 sites; Malt was a
  correct release-gate rejection rather than an infrastructure failure.
- Ike's Sandwiches completed authoritatively:
  - ScanRun `6a7f5577bd5a5dade6a1089b`
  - FixList `6a7f55c895ba0ad5d40998d3`
  - 163 URLs found, 150 crawled, score 56, Python scanner/review, no fallback.
- The Ike result exposed a real persisted duplicate defect: 36 rows represented
  four distinct actions. That defect is fixed locally before proof creation.

This evidence supports continuing toward a capped beta. It is not post-fix
production acceptance.

## Decisive live Base44 boundary evidence

A read-only inspection of the connected production Base44 app confirmed that
the hardened entity rules are **not deployed**:

- live `ScanRun` still permits owner create/read/update/delete and contains
  score, evidence, authority, and release fields;
- live `FixList` and `FixItem` still permit owner create/read/update/delete;
- live `Access` still uses `pending`/`active`/`revoked`, with admin writes and
  owner reads.

Therefore production still has a direct entity confidentiality/tamper/availability
boundary risk even though local contract tests pass. No live entity, function,
traffic, queue, payment, key, or scan was mutated during that inspection.

## Implemented locally

### 1. Sealed duplicate suppression

Files:

- `base44/functions/persistDurableScanAuthority/authoritySnapshot.js`
- `tests/frontend/authoritySnapshotDedup.test.mjs`

The durable authority snapshot now suppresses a page-level action only when a
same-rule family action explicitly covers that page. Deduplication happens
before counts, top-action IDs, HMAC creation, and persistence. The Ike fixture
contracts from 36 rows to four, keeps uncovered outliers, and reconstructs the
same valid proof. Scanner crawling, scoring, classification, and eligibility
were not changed.

### 2. Paid-result server boundary

Files:

- `base44/functions/getCustomerScanResult/function.jsonc`
- `base44/functions/getCustomerScanResult/index.ts`
- `base44/functions/getCustomerScanResult/projection.js`
- `base44/entities/FixList.jsonc`
- `base44/entities/FixItem.jsonc`
- `src/lib/scanRuns.js`
- `src/pages/FixList.jsx`
- `tests/frontend/customerResultBoundary.test.mjs`
- `tests/frontend/customerScanHistoryBoundary.test.mjs`

`FixList` and `FixItem` are now admin/service-role only. Customer content crosses
one owner- and entitlement-aware server projection. Full content is returned
only for an exact complete, non-provisional, release-eligible snapshot whose
relationships, counts, fingerprint, and HMAC all verify. Locked customers get
progress metadata and zero FixItems. Proofs and owner IDs are not projected.

The subsequent read-boundary slice is also complete locally:

- exact-result reads now service-read `ScanRun` and explicitly verify owner,
  owned project, and project/domain identity;
- legacy rows may use `created_by_id` only when `owner_user_id` is blank, and
  legacy ownership can expose progress only, never sealed paid content;
- saved history now crosses the same function as a strict progress-only
  projection capped at 20 rows;
- the browser history wrapper no longer directly reads `ScanRun`.

This closes the customer result/history read seam. It does **not** close the
remaining browser create/update/delete and terminal-state lifecycle seam.

Customer raw debug JSON, internal IDs, “Clear scans,” and browser recovery on a
result-page view were removed.

### 3. Checkout and webhook hardening

Files:

- `base44/functions/createAccessCheckout/entry.ts`
- `base44/functions/createAccessCheckout/function.jsonc`
- `base44/functions/stripeWebhook/entry.ts`
- `base44/functions/stripeWebhook/function.jsonc`
- `src/lib/checkout.js`
- `src/components/billing/UnlockAccessButton.jsx`
- `tests/frontend/checkoutExactOnce.test.mjs`

Implemented exact return-origin matching, pending Stripe-session reuse,
user-stable Stripe idempotency, historical paid-session activation,
replay-safe webhooks, revoked-access protection, and customer-safe failure
copy. The built-in production origin is:

`https://rich-rank-pilot-flow.base44.app`

Preview checkout additionally requires:

`CHECKOUT_RETURN_ORIGINS=https://preview--rich-rank-pilot-flow.base44.app`

`CHECKOUT_ALLOW_LOCALHOST` must remain false in production.

The local paid-beta fallback is now fail-closed and invite-only:

- `BETA_CHECKOUT_ENABLED` defaults off;
- `BETA_CHECKOUT_GENERATION` is mandatory when enabled;
- `BETA_COHORT_ALLOWED_USER_IDS` must contain 1–25 unique exact Base44 user IDs;
- checkout never creates Access rows; each invited ID must have exactly one
  pre-provisioned, owner-and-email-bound pending Access row;
- concurrent first checkout calls use the same user/generation/session-derived
  Stripe key and converge on one session.

This closes the uncontrolled first-Access creation race for the invite-only
posture. It does not implement public first-come seat allocation. The switch,
cohort, pre-provisioned rows, test-mode payment journey, and deployed webhook
must still be verified before payments are enabled.

### 4. Post-payment activation UI

Files:

- `src/pages/Billing.jsx`
- `tests/frontend/billingActivation.test.mjs`

`?paid=1` immediately enters “Activating access,” suppresses every repeat
purchase CTA, polls `loadAccess` for at most 15 attempts/30 seconds with
per-read bounds and cleanup, then shows success or a polling-only retry state.
It never directs the customer into a second checkout while activation is
pending.

### 5. Saved-result rediscovery

Files:

- `src/pages/FixList.jsx`
- `tests/frontend/savedResultRecovery.test.mjs`

`/dashboard` without `scan_id` shows up to eight recent owner-scoped scans for
the active project. Each row retains only customer-safe summary fields and
reopens the exact encoded `scan_id`. Active, complete, failed, limited, and
cancelled states have distinct copy. Result content still uses the verified
server projection.

### 6. Honest beta customer surface

Files:

- `src/pages/Landing.jsx`
- `src/App.jsx`
- `src/components/layout/DashboardLayout.jsx`
- `tests/frontend/publicBetaSurface.test.mjs`

The landing offer now says one-time USD 50 Standard 150 beta access, up to 150
pages, usually 2–4 minutes. False free/no-card claims are gone. Grok navigation
is removed and `/assistant` redirects to `/dashboard`. Premium remains
unavailable.

### 7. Worker provenance and Base44 release manifest

Files:

- `cloudbuild.durable-worker.yaml`
- `scripts/base44_release_manifest.mjs`
- `docs/standard150-deployment-contract.md`
- `tests/frontend/durableReleaseIntegrity.test.mjs`

Cloud Build no longer trusts a 40-hex label alone. It fetches the claimed SHA
from the canonical GitHub repository, compares the uploaded build policy,
Dockerfile, requirements, and complete `scanner-api/app` directory, prints the
verified `main.py` SHA-256, and builds only from a fresh archive of that commit.
Therefore the current dirty tree cannot be deployed under a claimed SHA; it
must first be reviewed, committed, and pushed.

The deterministic release manifest now covers all six customer-critical Base44
functions:

1. `startStandardScanJob`
2. `durableScanWorkerControl`
3. `persistDurableScanAuthority`
4. `getCustomerScanResult`
5. `createAccessCheckout`
6. `stripeWebhook`

The post-deploy verifier no longer contains a manual inventory skip. It now
requires `BASE44_PULLED_FUNCTIONS_DIR` to point to a fresh authenticated Base44
CLI pull and compares all six deployed package digests and the combined release
digest byte-for-byte. Missing or drifted functions fail promotion. This has
passed with synthetic exact, missing, and drifted inventories locally; it has
not yet been run against the deployed production inventory.

Known evidence gap: the manifest proves the six function packages but does not
hash `base44/entities/ScanRun.jsonc`, `FixList.jsonc`, or `FixItem.jsonc`.
Before locking entity RLS, extend the release evidence to compare the pulled
entity schemas (at minimum `ScanRun`) and retain live negative CRUD tests.

### 8. Discriminated customer recovery states

Files:

- `src/lib/scanRuns.js`
- `src/pages/FixList.jsx`
- `tests/frontend/customerRecoveryErrors.test.mjs`

History and exact-result reads now return stable `{ ok, kind, ... }` contracts
instead of turning every failure into `[]` or `null`. The customer can now see
safe states for unauthorized, not found, access conflict, unavailable,
authority invalid, non-authoritative, and generic load failure. Only transient
failures offer retry. A background transient failure keeps the last
proof-verified result; integrity, access, authentication, and not-found failures
clear it. Opaque deterministic `FL-...` support references do not include owner,
request, proof, or raw backend payload data.

### 9. Paid-beta funnel instrumentation

Files:

- `src/lib/analytics.js`
- `src/lib/AuthContext.jsx`
- `src/components/billing/UnlockAccessButton.jsx`
- `src/pages/Billing.jsx`
- `src/components/scan/ScanWebsiteForm.jsx`
- `tests/frontend/releaseFunnel.test.mjs`

Checkout start, payment return, access activation/delay, and accepted scan are
deduplicated at their customer seams. Pre-auth queued events flush only after a
successful authenticated session and failed event writes remain queued. The
event catalog also declares `result_viewed` and `fix_opened`, but those two
emissions are **not wired yet**. No production analytics journey or dashboard
has been demonstrated.

## Fresh local verification

Run with the bundled Node executable because the shell does not expose a normal
Node/npm toolchain:

```bash
NODE=/Users/elizabethnguyenson/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node
$NODE --test tests/frontend/*.test.mjs
$NODE node_modules/typescript/bin/tsc -p ./jsconfig.json --noEmit
$NODE node_modules/eslint/bin/eslint.js . --quiet
$NODE scripts/base44_release_manifest.mjs verify
git diff --check
```

Results on 2026-08-14:

- Frontend contracts: **342/342 passed**
- TypeScript no-emit: **passed**
- Full ESLint (`--quiet`): **passed**
- Six Base44 release packages: **portable, closed, pinned — passed**
- YAML parse for `cloudbuild.durable-worker.yaml`: **passed**
- `git diff --check`: **passed**
- Scoped ESLint for each changed implementation slice: **passed**

The local Vite/Rollup production build remains environment-blocked by the
macOS native Rollup module Team-ID signature error before compilation. Do not
“fix” this by destructive dependency reinstall during the handoff; use the
remote build or a clean trusted toolchain.

## Open P0 blockers

### P0.1 — `ScanRun` is not a sealed server-owned boundary

`base44/entities/ScanRun.jsonc` still lets the owner read, update, and delete a
row that contains health score, customer summary, evidence, release markers,
and authority identity. The result/history function now service-reads and
projects safe fields, but entity RLS still lets a caller bypass that intended
read boundary. HMAC verification prevents forging a valid result, while direct
writes/deletes can still destroy availability.

Minimum safe direction:

- make `ScanRun` admin-only for all CRUD after compatible functions/frontend
  are deployed;
- reduce `src/lib/scanRuns.js` to function invocations and remove direct browser
  `ScanRun` create/update/delete/terminalization;
- preserve historical rows; only a strictly proven `created_by_id` legacy
  fallback may reveal progress, never paid sealed content. The read/history
  function already enforces this rule; keep it intact during lifecycle work.

Do not deploy the current FixList/FixItem RLS change as a standalone mutation.
It must be bundled with the compatible server projection and frontend.

### P0.2 — scan admission and terminal ownership remain browser-driven

`src/lib/scanRuns.js` still restarts/terminalizes stale rows while starting a
new scan and explicitly has no cross-browser/process exact-once guarantee. The
client active TTL is 10 minutes, the worker request deadline is 480 seconds, and
the server watchdog is delayed 900 seconds. Customer result views no longer
terminalize jobs, but a later browser submission can still race valid delayed
work.

Minimum:

- turn the existing `startStandardScanJob` into a single authenticated
  begin-and-dispatch call; the browser supplies request identity, target, and
  context but does not create or choose a `scan_id`;
- use the already-required single paid `Access` row as the owner lease, claim it
  with a conditional compare-and-set, bind the created `scan_id`, enqueue the
  deterministic drain before the scan task, and keep dispatcher writes guarded
  from terminal rows;
- same-request losers must reuse/wait for the winner; different requests while
  active get 429 plus `retry_after`; worker/watchdog remain terminal owners;
- test two-tab contention, lost responses, claim/create/enqueue partial failures,
  worker-before-dispatcher completion, cancel races, and cross-owner independence;
- get an explicit Base44 guarantee that conditional single-row `updateMany` is
  atomic, then prove it with a sandbox contention test. The documented SDK has
  no transaction, unique index, create-if-absent, or stated CAS guarantee. If
  that guarantee is unavailable, use an external transactional/SETNX
  coordinator. Do not claim exact-once from query-then-create or in-memory state.

### P0.3 — deploy and operate the safe checkout posture

The local candidate now avoids unique Access creation entirely: checkout is
default-off, accepts at most 25 exact invited user IDs, requires one
pre-provisioned Access row, and uses user-stable Stripe idempotency. This is a
safe invite-only allocator, not public first-come allocation. It remains
undeployed and unproven against Stripe test mode.

Minimum:

- review and configure the default-off switch, cohort generation, and at most
  25 exact IDs, including every existing active owner;
- pre-provision exactly one pending Access row per invited owner/email and prove
  that missing and duplicate rows fail before Stripe;
- run the complete concurrent same-owner, disabled/corrupt/26-ID, open/expired
  session, webhook replay, and activation journey against Stripe test mode;
- public first-come allocation requires a preseeded singleton release-control
  row with a proven atomic conditional counter/reservation, or an external
  transactional coordinator;
- one duplicate paid session must keep one entitlement, perform one idempotent
  Stripe refund, and create an operator incident; add the runbook;
- replace “unlimited” with founder-approved fair-use wording/enforcement;
- keep the purchase switch off until the deployment inventory, webhook, and
  one controlled paid activation are proven.

### P0.4 — public policies, support, and deletion requests

There are no public Terms, Privacy, Refund/Cancellation, Security/read-only
scanning, retention, support, or deletion routes. Billing still points deletion
requests to generic Base44 support.

The product owner must supply or approve, at minimum:

- legal/operator name and required address/country details;
- public support email or ticket destination;
- refund/cancellation rule;
- retention/deletion rule;
- USD/tax wording, beta-change wording, 25-seat cap, and fair-use limit.

Do not invent these values or publish a personal email without approval.

### P0.5 — monitoring and final acceptance

Recovery classification and automated six-package inventory comparison are now
implemented locally. They still need browser/deployed proof. Provisioned alerts,
complete funnel evidence, and final acceptance are not proven. The formal
release record remains `candidate`.

Minimum:

- make a fresh authenticated CLI pull and prove that the six deployed Base44
  packages match the reviewed candidate with the fail-closed verifier;
- add deterministic digest/compare evidence for the deployed `ScanRun`,
  `FixList`, and `FixItem` entity schemas, then run authenticated negative
  create/read/update/delete tests after the RLS lock;
- emit and verify the missing `result_viewed` and `fix_opened` events;
- verify gateway/worker contracts, queue age, stuck runs, retry exhaustion,
  authority rejection, payment activation, and 5xx alerts;
- verify a rollback target and purchase-pause control;
- deploy the exact candidate, complete one paid owner-bound acceptance,
  complete one controlled non-authoritative negative, then run the 20-site
  matrix;
- freeze commit, package hashes, Cloud Run revision/image digest, Base44
  inventory, scan IDs, and artifact digest only after those checks pass.

## Acceptance and 20-site matrix handoff

Do not start the matrix merely because local tests are green. First freeze and
deploy one reviewed candidate, prove its worker revision/image and all six
Base44 package digests, then complete one owner-bound paid journey. Only after
that first scan succeeds may the production matrix begin.

Required controls called out by the product owner are Norris Wines,
Center Street Lending, Meilleurtaux, Pretto, Funbooker, and a fresh Ike's
Sandwiches duplicate check. Before the run, freeze an exact 20-target subset
from the following supplied pool so failures are not cherry-picked away:

`funbooker.com`, `pretto.fr`, `papernest.com`, `selectra.info`, `malt.fr`,
`ornikar.com`, `legalstart.fr`, `captaincontrat.com`, `wecasa.fr`,
`jestocke.com`, `qonto.com`, `alan.com`, `yousign.com`, `spendesk.com`,
`matera.eu`, `centerstreetlending.com`, `kiavi.com`, `lima.one`,
`anchorloans.com`, `visiolending.com`, `groundfloor.us`, `easystreetcap.com`,
`newsilver.com`, `pilot.com`, `guideline.com`, `collective.com`,
`tablascreek.com`, `bedrockwineco.com`, `scribewinery.com`, and
`deathwishcoffee.com`.

Confirm the exact Norris Wines, Meilleurtaux, and Ike's URLs with the owner
before freezing the list. A correct evidence-limited/non-authoritative outcome
is valid when the gate explains it; an infrastructure failure, fallback,
cross-account substitution, page-cap breach, duplicate action set, or stuck
run is not. Record every ScanRun/FixList ID and release marker.

## Decisions/inputs the next owner must obtain

Engineering must not guess these:

1. Is Friday's payment posture **invite-only (recommended safe fallback)** or
   truly public first-come? Invite-only can use a strict allowlist of at most 25
   exact user IDs. Public first-come requires a proven atomic allocator.
2. Will Base44 explicitly guarantee atomic conditional mutation on one row, or
   should the owner authorize an external transactional/SETNX coordinator for
   scan and checkout admission?
3. What are the legal/operator name, country/address details, public support
   destination, refund/cancellation rule, retention/deletion rule, tax wording,
   beta-change wording, and enforceable fair-use limit?
4. Who is the named release operator and rollback/incident owner during the
   first 25-customer cohort?

## Required next execution order

1. **Review and preserve the current dirty worktree.** Do not overwrite or
   reset it. Obtain a second code/security review of the local diffs.
2. **Choose the truthful payment posture.** For Friday, the safe fallback is an
   invite-only allowlist of no more than 25 exact users behind a default-off
   kill switch. Public first-come checkout requires proven atomic allocation.
3. **Close `ScanRun` ownership and server admission** in a Base44 sandbox with
   negative/direct-entity, two-tab, and partial-failure tests. Do not change
   crawler logic. Do not deploy admin-only entity rules before compatible
   functions and frontend exist.
4. **Close checkout concurrency, seat cap, purchase pause, duplicate-payment
   refund handling, and fair use.**
5. **Get founder/legal decisions** and implement public policies, support, and
   acknowledged deletion requests.
6. **Finish result/fix funnel emissions, monitoring/alerts, browser recovery
   E2E, and the fresh deployed-package comparison.**
7. **Run the complete local gate** and produce a reviewed commit. Push the
   commit before using the new Cloud Build provenance step.
8. **Deploy as one compatible release unit.** In particular, never publish
   admin-only FixList/FixItem rules without `getCustomerScanResult` and the new
   frontend that consumes it.
9. **Run one controlled paid production journey**: registration → payment →
   one entitlement → Standard 150 → exact saved result → refresh/relogin.
10. If that passes, run a fresh Ike duplicate check, a large-site control such
   as Funbooker/Ornikar, a controlled evidence-limited negative, then the full
   20-site matrix.
11. Only after every P0 is green, make the formal capped-beta go/no-go decision.

## Hard constraints for the next agent

- Do not redesign the scanner or change discovery, crawl cap, scoring,
  classification, review thresholds, or `isAuthorityEligible`.
- Do not enable Grok or Premium 5,000.
- Do not loosen the authority gate to make a scan pass.
- Do not rotate/sync signing keys unless a separately reviewed release step
  explicitly requires it.
- Do not change traffic, queue state, or run customer scans before the release
  candidate is deployed and verified.
- Do not claim beta GO without a successful fresh production acceptance.

## Copy/paste continuation prompt

> Continue the FixList capped paid-beta hardening from
> `docs/beta-release-handoff-2026-08-14.md`. Preserve the dirty worktree and
> first verify its 342/342 green baseline. Do not change scanner crawl,
> discovery, scoring, review, or authority eligibility logic. Work only on the
> remaining P0s in order: (1) server-owned ScanRun read/write/delete boundary
> and cross-tab admission with a proven atomic owner lease, (2) concurrent
> first-checkout protection plus a default-off purchase switch and strict
> 25-seat cap, (3) founder-approved public legal/support/deletion surfaces, and
> (4) deploy/monitoring/browser evidence. Base44's documented SDK does not prove
> CAS/transaction/uniqueness; keep payments invite-only behind an allowlist of
> at most 25 exact users unless atomic allocation is explicitly guaranteed and
> contention-tested. Start read-only, name the exact false boundary or race
> before editing, add executable negative tests, and do not deploy, push, change
> traffic/queue/secrets, or run a customer scan without explicit approval. The
> release remains NO-GO until one fresh paid production acceptance and the
> 20-site matrix pass on the exact deployed candidate.
