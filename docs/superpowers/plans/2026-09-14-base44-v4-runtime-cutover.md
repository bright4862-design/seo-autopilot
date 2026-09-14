# Base44 V4 Runtime Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore Standard 150 using fresh Base44 V4 route names while preserving all current customer and authority behavior.

**Architecture:** Clone the current active route packages into fresh V4 identities, route browser/worker traffic to V4, and update deterministic release tooling to verify V4 while retaining V3/V2 as historical aliases. No business/scanner logic changes.

**Tech Stack:** React/Vite, Node test runner, Deno Base44 functions, Python Standard 150 worker, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-14-base44-v4-runtime-cutover-design.md`

## Global Constraints

- LIVE admission remains closed throughout implementation and deployment.
- Preserve authority fail-closed behavior and `SCAN_EVIDENCE_SIGNING_KEY` semantics.
- Preserve Standard 150 limits, robots/SSRF protections, and historical result correctness.
- Preserve unpaid preview: maximum two verified preview fixes and `$49` unlock CTA.
- Do not upgrade Base44 CLI during this cutover.
- Do not promote any worker built from a SHA older than the merged V4 cutover SHA.

---

### Task 1: Pin V4 route and teaser contracts

**Files:**
- Create: `tests/frontend/base44V4Cutover.test.mjs`

**Interfaces:**
- Consumes: `data/base44-function-routes.json`, active Base44 packages, frontend/worker call sites.
- Produces: failing contract that requires V4 active routes, V3+V2 historical routes, package parity, and unpaid-preview invariants.

- [ ] Write the V4 contract test.
- [ ] Run it before implementation and confirm it fails because generation is still V3/V4 packages do not exist.
- [ ] Commit the failing test.

### Task 2: Create fresh V4 packages and deterministic route identity

**Files:**
- Create: six `base44/functions/*V4/` packages copied from current V3/canonical behavior.
- Modify: `data/base44-function-routes.json`
- Modify: `scripts/generate_release_contracts.mjs`

**Interfaces:**
- Consumes: canonical package identity and V3 package behavior.
- Produces: active V4 aliases with fresh activation IDs and canonical build IDs; V3/V2 historical aliases remain stamped.

- [ ] Copy package files without changing executable behavior.
- [ ] Change only V4 function names and activation IDs where route identity requires it.
- [ ] Change route registry generation to V4 and retain V3/V2 history.
- [ ] Generalize historical alias stamping across all historical generations.
- [ ] Regenerate release/build contracts and run V4 parity tests.

### Task 3: Route frontend, worker, deploy and verification tooling to V4

**Files:**
- Modify: `src/components/scan/ScanWebsiteForm.jsx`
- Modify: `src/lib/scanRuns.js`
- Modify: `src/lib/scanHistory.js`
- Modify: `scanner-api/app/scan_job.py`
- Modify: `scripts/base44_release_manifest.mjs`
- Modify: `scripts/deploy-base44-beta-functions.sh`
- Modify: `scripts/deploy-base44-beta-site.sh`
- Modify: `scripts/verify-base44-functions.sh`
- Modify: affected route-contract tests.

**Interfaces:**
- Consumes: V4 route registry/packages.
- Produces: customer and worker traffic uses only V4 active routes; release tooling verifies V4.

- [ ] Replace active V3 route calls with V4, leaving recovery/history tooling intact where V3 is intentionally historical.
- [ ] Update deploy/manifest/verification enumerations to V4.
- [ ] Update route-generation tests without changing scanner expectations.
- [ ] Run frontend and scanner focused suites.

### Task 4: Verify, merge and perform guarded production cutover

**Files:** no product behavior beyond Tasks 1-3.

**Interfaces:**
- Consumes: green V4 PR.
- Produces: exact-main V4 release staged and production-verified before admissions reopen.

- [ ] Run full CI and review the complete PR diff for unrelated changes.
- [ ] Merge only if green and capture new exact main SHA.
- [ ] Stage a new worker candidate at zero traffic from that exact SHA.
- [ ] Publish Base44 `site-and-functions` from exact SHA using the guarded owner workflow.
- [ ] Verify all six live V4 build IDs/activation IDs/source identity.
- [ ] Promote exact-SHA worker, resume queues while claims remain closed, and run one fresh unpaid canary.
- [ ] Verify scan completion, authority, 1-2 preview fixes, `$49` CTA, no full FixItem leakage, reload/history, and paid full-access sanity.
- [ ] Open claim barrier only after acceptance passes.
