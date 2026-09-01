# P1-B1 Focused Path Scans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add safe, explicit same-origin folder scans as separate Standard 150 ScanRuns without weakening admission, ownership, robots, SSRF, authority, or the 150-page cap.

**Architecture:** Extend the existing durable Standard 150 request identity with a normalized path scope, validate parent/scope ownership in startStandardScanJob, persist lineage on ScanRun, and expose a bounded customer CTA derived only from trustworthy sampling-v2 folder evidence. The Python scanner's existing path_prefix / same-origin boundary remains the crawl enforcement layer.

**Tech Stack:** React/Vite, Base44 Deno functions and entities, Node contract tests, Python scanner/pytest.

**Spec:** docs/superpowers/specs/2026-08-31-p1b1-focused-path-scans-design.md

## Global Constraints

- P1-B1 is same-origin path-prefix scanning only; subdomains are excluded.
- Standard 150 remains exactly 150 pages maximum.
- Respect robots.txt exactly as today.
- Preserve all SSRF/public-host checks.
- Preserve Python scanner/review authority and fail-closed persistence.
- Do not restore Deno fallback.
- Every focused scan gets a distinct ScanRun/FixList/authority decision.
- No focused scan starts without explicit user confirmation.
- Do not deploy or merge this branch into the current 7a95768cc8ee2076 release candidate.

---

### Task 1: Canonical focused-scope identity

**Files:**
- Create: src/lib/focusedScanScope.js
- Modify: src/lib/scanRunIdentity.js
- Test: tests/frontend/focusedScanIdentity.test.mjs
- Test: tests/frontend/scanRunIdentity.test.mjs

**Interfaces:**
- normalizeFocusedPathPrefix(value): string
- buildFocusedScopeIdentity({ scopeType, requestedPathPrefix }): object
- buildScanRequestIdentity accepts scopeType and requestedPathPrefix.

- [ ] **Step 1: Write the failing tests.** Prove full-site and /fr/ fingerprints differ; /fr/ and /en/ differ; duplicate /fr/ requests share the same scope identity; /fr, //fr// normalize to /fr/; URL-shaped prefixes, dot segments, backslashes, encoded separators and control characters are rejected.
- [ ] **Step 2: Verify RED.** Run: node --test tests/frontend/focusedScanIdentity.test.mjs tests/frontend/scanRunIdentity.test.mjs. Expected: failure because focused-scope helpers do not exist.
- [ ] **Step 3: Implement minimal pure scope helper and identity extension.** Keep full-site request fingerprints byte-for-byte backward compatible; append |scope:path_prefix:/fr/ only for focused scans.
- [ ] **Step 4: Verify GREEN** with the same test command.
- [ ] **Step 5: Commit** with message: feat(scan): add focused path request identity.

### Task 2: Server admission fingerprint and fail-closed scope validation

**Files:**
- Modify: base44/functions/startStandardScanJob/entry.ts
- Create only if needed: base44/functions/startStandardScanJob/focusedScope.ts
- Test: tests/frontend/serverOwnedScanAdmission.test.mjs
- Test: tests/frontend/scanAdmissionContract.test.mjs
- Test: tests/frontend/durableScanJobDispatch.test.mjs

**Interfaces:**
- Consumes scope_type, requested_origin, requested_path_prefix, parent_scan_id, discovered_from, user_confirmed.
- Produces scope-aware admission fingerprint and validated worker path_prefix.

- [ ] **Step 1: Add failing server-admission tests.** Assert full site vs /fr/ claim distinct fingerprints; /fr/ vs /en/ distinct; duplicate /fr/ replay; confirmation required; malformed/root/cross-origin scope rejected; missing/unowned/wrong-project parent fails before ScanRun creation; worker gets path_prefix=/fr/.
- [ ] **Step 2: Verify RED** with the three focused Node suites.
- [ ] **Step 3: Implement minimal server validator.** Normalize scope before claim; explicitly owner-check the parent through service role; require same project and origin; require terminal trustworthy parent; derive admission fingerprint from website plus scope; ensure any claimed admission is released if a later scope check fails.
- [ ] **Step 4: Verify GREEN.**
- [ ] **Step 5: Commit** with message: feat(scan): validate focused path admission.

### Task 3: Persist child-scan lineage safely

**Files:**
- Modify: base44/entities/ScanRun.jsonc
- Modify: base44/functions/startStandardScanJob/entry.ts
- Modify: src/lib/scanRuns.js
- Test: tests/frontend/scanRunPersistence.test.mjs
- Test: tests/frontend/recentScanLineageWiring.test.mjs

**Schema fields:** parent_scan_id, scope_type, requested_origin, requested_path_prefix, discovered_from, user_confirmed. Existing path_prefix remains the effective worker boundary.

- [ ] **Step 1: Write failing persistence tests** for all lineage fields and path_prefix; assert normal full-site rows do not fabricate focused metadata.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Add schema fields and creation/recovery parity.** A request key cannot be rebound to a different parent or scope; historical rows without scope stay readable.
- [ ] **Step 4: Verify GREEN.**
- [ ] **Step 5: Commit** with message: feat(scan): persist focused scan lineage.

### Task 4: Project lineage through customer result and history

**Files:**
- Modify: base44/functions/getCustomerScanResult/projection.js
- Modify: src/lib/scanRuns.js
- Test: tests/frontend/customerScanHistoryBoundary.test.mjs
- Test: tests/frontend/accountWideScanHistory.test.mjs
- Test: tests/frontend/customerResultBoundary.test.mjs

- [ ] **Step 1: Write failing projection tests.** Exact read and history must expose parent_scan_id, scope_type and requested_path_prefix for a child, while request/admission fingerprints remain absent.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Extend only the safe lineage projection and frontend mapping.**
- [ ] **Step 4: Verify GREEN.**
- [ ] **Step 5: Commit** with message: feat(history): expose focused scan lineage.

### Task 5: Derive trustworthy same-origin folder suggestions

**Files:**
- Create: src/lib/focusedScanSuggestions.js
- Modify samplingDisclosure.js only if a stable accessor is needed.
- Test: tests/frontend/focusedScanSuggestions.test.mjs

**Interface:** focusedPathScopes(record, { limit = 6 } = {}) returns bounded objects with path_prefix, label, discovered, sampled, reason and discovered_from.

- [ ] **Step 1: Write failing suggestion tests** using production-shaped sampling-v2 markets_discovered / markets_sampled evidence. Literal /fr/ and /en/ keys may become suggestions; human-readable country labels without a literal safe path must not. Reject root, URL-shaped, malformed and duplicate prefixes; cap at six.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement the pure helper.** Never infer from country names, domains, canonical URLs or arbitrary page samples.
- [ ] **Step 4: Verify GREEN.**
- [ ] **Step 5: Commit** with message: feat(scan): derive focused folder suggestions.

### Task 6: Explicit customer confirmation and scoped submission UI

**Files:**
- Modify: src/pages/FixList.jsx
- Modify: src/lib/scanRuns.js
- Modify ScanWebsiteForm.jsx only if sharing its durable submit seam is safer than a small library helper.
- Create: tests/frontend/focusedScanUx.test.mjs
- Test: tests/frontend/newScanPageUx.test.mjs

- [ ] **Step 1: Write failing UX tests.** Show Site sections discovered; show /fr/ coverage; first CTA click does not invoke scan; confirmation copy states separate Standard 150 scan; confirm sends exact parent/scope payload with user_confirmed=true; success navigates to exact server scan_id; failure leaves parent FixList intact.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement the compact panel and confirmation** below sampling disclosure, preserving the current visual hierarchy.
- [ ] **Step 4: Verify GREEN.**
- [ ] **Step 5: Commit** with message: feat(ui): add confirmed focused folder scan.

### Task 7: History labeling and reload behavior

**Files:**
- Modify the recent-scan presentation used by src/pages/FixList.jsx.
- Test: tests/frontend/scanHistoryPresentation.test.mjs
- Test: tests/frontend/scanHistoryLineageBadge.test.mjs
- Test: tests/frontend/standard150ScanRecovery.test.mjs

- [ ] **Step 1: Write failing tests** proving child history label is host · /fr/, click opens the exact child id, and refresh cannot substitute parent/full-site result.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement presentation using persisted lineage only.**
- [ ] **Step 4: Verify GREEN.**
- [ ] **Step 5: Commit** with message: feat(history): label focused folder scans.

### Task 8: Python scope regression and release-contract bump

**Files:**
- Add focused tests under scanner-api/tests/.
- Modify: data/cross-runtime-release-components.json
- Regenerate release-contract carriers through scripts/generate_release_contracts.mjs.
- Update beta revision through the repository's canonical freeze/generator process.
- Test: tests/frontend/releaseContractCanonical.test.mjs

- [ ] **Step 1: Add Python scope tests** proving explicit /fr/ excludes /en/, keeps same-origin /fr/ URLs, uses origin robots, and stays within 150.
- [ ] **Step 2: Run those tests.** If scanner behavior already passes, treat it as characterization and do not change Python production code unnecessarily.
- [ ] **Step 3: Add component marker focused_path_scan_scope_v1_same_origin_confirmed and regenerate all release identities atomically.**
- [ ] **Step 4: Run generator --check and releaseContractCanonical test.**
- [ ] **Step 5: Commit** with message: chore(release): version focused path scans.

### Task 9: Full verification and PR readiness

- [ ] **Step 1: Frontend gates:** npm run lint; npm run typecheck; npm run test:frontend; npm run build.
- [ ] **Step 2: Scanner gates:** pytest tests/; then cd scanner-api && pytest tests/ && python scripts/freeze_beta_revision.py --check.
- [ ] **Step 3: Build production scanner image:** docker build --tag fixlist-scanner:p1b1-ci .
- [ ] **Step 4: Diff review:** no robots override, SSRF relaxation, page-cap change, Deno fallback, entitlement weakening, authority weakening or subdomain trust.
- [ ] **Step 5: Keep the PR draft.** Do not merge/deploy until the current Standard 150 release is accepted and this feature receives independent review.