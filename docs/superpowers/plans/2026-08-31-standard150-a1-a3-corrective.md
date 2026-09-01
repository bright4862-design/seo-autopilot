# Standard 150 A1–A3 Corrective Implementation Plan

> **For Codex:** Execute this plan in the isolated `codex/standard150-a1-a3-corrective` worktree. Use strict TDD for every behavior change. Stop before merge or deployment.

**Goal:** Make Standard 150 classification resistant to translated-route vote inflation, make durable canonical FixItem grouping match the customer read model on production-shaped data, and render/export the persisted child evidence from that single canonical action model.

**Architecture:** The Python review layer will derive a locale-normalized, order-preserving structural path set while leaving raw text scoring untouched. The durable repair contract will group on any valid non-empty scanner-owned `repair_fingerprint`; `repair_identity_stable` remains unchanged and continues to gate cross-scan fixed-state verification only. The frontend card model remains the single customer action adapter, with both FixList rendering and PDF export consuming its canonical actions and evidence groups.

**Tech Stack:** Python 3.12/FastAPI scanner, pytest, React 18, Base44 SDK-backed functions, Node test runner, jsPDF, Vite.

---

## Task 1: Record the Current Boundary and Baseline

**Files:**
- No source changes

1. Confirm the isolated branch starts at exact `origin/main` and the legacy checkout remains untouched.
2. Record current PR boundaries: #215 diagnostic-only and green; #216 focused-scan implementation separate and red; #217 focused-scan design-only and green.
3. Confirm Base44 owner auth and remote function inventory read-only.
4. Confirm staged worker `00058-r82` is Ready, exact-main, concurrency 1, timeout 480, and 0% traffic.
5. Run focused classifier, repair-contract, grouping, evidence, and URL tests and record the baseline totals.

## Task 2: A1 — Locale-Normalized Structural Route Voting

**Files:**
- Modify: `scanner-api/app/review.py`
- Add: `scanner-api/tests/test_classifier_locale_normalized_routes.py`
- Modify only if supported by executable fixtures: `scanner-api/tests/test_finance_sub_playbooks.py`

1. Add a failing regression proving twelve locale variants of one article count as one structural article route.
2. Add a control proving twelve genuinely different articles still count as twelve.
3. Add route-shaped regressions tied only to available 35-site evidence for Musement, Tiqets, Pennylane, IKEA, Wise, N26, and Alan; preserve Wecandoo, Funbooker, Qonto, Spendesk, Pretto, Smartbox, Airbnb, PayFit, and wine-retail controls.
4. Run the new test file and record the expected RED failure.
5. Reuse `market_scope.strip_market_locale_prefix` to build an order-preserving deduplicated structural path list.
6. Use normalized structural paths only for route/pattern vote counts and structural diagnostics. Do not change raw title/H1/meta/keyword text scoring.
7. If executable evidence supports a B2B finance/accounting/spend-management playbook, add the narrowest playbook and keep Qonto/Spendesk/PayFit controls green. Otherwise record the gap without guessing.
8. Bump the classifier component marker, but do not freeze/regenerate the release fingerprint yet.
9. Run the new tests, all classifier tests, then the full scanner-api suite.

## Task 3: A2 — Production-Shaped Durable Fingerprint Grouping

**Files:**
- Modify: `scanner-api/app/repair_contract_v2.py`
- Modify: `scanner-api/tests/test_repair_contract_v2.py`
- Modify if needed for end-to-end persistence proof: `tests/frontend/persistedRepairGrouping.test.mjs`

1. Replace the stability-injected unit fixture with a production-shaped pair that has the same non-empty `repair_fingerprint` but no `repair_surface` and no `repair_identity_stable: true`.
2. Assert RED: the two rows persist separately before the fix.
3. Change persistence grouping identity to accept the same valid non-empty fingerprint the customer card model accepts.
4. Keep missing/empty fingerprints row-distinct.
5. Preserve URL union/dedup, child evidence groups, strictest action priority/severity/owner/effort, and the existing verification stability fields.
6. Add an explicit test that provisional grouping does not enable broader cross-scan `verified_fixed` behavior.
7. Bump `REPAIR_PERSISTENCE_GROUPING_VERSION`, without freezing the release fingerprint yet.
8. Run repair-contract, repair-identity, persistence, authority, and customer projection tests.

## Task 4: A3 — Render Evidence Groups and Share Canonical Export Model

**Files:**
- Modify: `src/lib/repairCardModel.js`
- Modify: `src/pages/FixList.jsx`
- Modify: `src/lib/exportScanReport.js`
- Add: `tests/frontend/customerEvidenceGroups.test.mjs`
- Add: `tests/frontend/canonicalExportParity.test.mjs`
- Modify as needed: `tests/frontend/persistedRepairGrouping.test.mjs`
- Modify: `data/cross-runtime-release-components.json`

1. Add failing model/render regressions for: exact child-group count, family, representative page, supported locale, single-child behavior, and no duplicate top-level action.
2. Add a failing export parity regression proving same-fingerprint raw rows produce one FixList repair and one export repair.
3. Expose a bounded customer evidence-group presentation from the existing canonical card model.
4. Render the persisted groups inside the canonical card's existing expandable evidence section, with a header count equal to rendered groups and a real link for each representative page.
5. Pass the scanned site origin through the canonical card list so relative evidence URLs resolve safely.
6. Make PDF export build its repair list through `buildRepairCards`, use the canonical repair count, and show the same group evidence without independently regrouping.
7. Keep dev recommendations as non-repair supplementary content only when no canonical repairs exist, avoiding hidden count inflation.
8. Bump the canonical cross-runtime repair presentation marker.
9. Run the new frontend tests, card/projection/export/evidence tests, then the full frontend suite.

## Task 5: Atomic Release Identity and Full Verification

**Files:**
- Generated by canonical scripts: `data/beta-crawler-revision.json`, `src/lib/generatedReleaseContract.js`, and Base44 generated release contracts/entry fingerprints
- Any canonical release documentation required by the freeze script

1. Inspect the complete diff for scope drift and accidental focused-scan, release-lane, admission, fallback, cap, Premium, or Grok changes.
2. Run the canonical beta revision freeze/generation workflow; never hand-edit generated fingerprints.
3. Run generated contract checks.
4. Run `npm run lint`, `npm run typecheck`, the complete frontend test suite, and production frontend build.
5. Run root scanner tests, complete scanner-api tests, and the frozen-revision drift check.
6. Build the production scanner image.
7. Re-run focused A1/A2/A3 before/after reproductions and capture exact totals.
8. Inspect the final diff and worktree status.

## Task 6: Draft PR Only

**Files:**
- No additional product behavior

1. Commit the green candidate on `codex/standard150-a1-a3-corrective`.
2. Push the branch and open a draft PR targeting `main`.
3. Do not merge, publish Base44, deploy Cloud Run, promote worker traffic, or run production scans.
4. Report branch, exact SHA, fingerprint, files, tests, before/after reproductions, FixList/export parity, CI totals, remaining blueprint gaps, merge order relative to #215, and staged-worker rebuild implications.
