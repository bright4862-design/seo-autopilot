# Published Evidence Identity Implementation Plan

> Release sequencing update (2026-09-19): the user explicitly authorized “once stage one is ready deploy and publish.” Complete and review all stage-one behavior before merging and publishing exact source. Earlier references to waiting for the entire blueprint are superseded for this first release. B06–B24 and the genuine 30-site full-blueprint gate remain open; synthetic stage-one acceptance does not complete them. No further general implementation or deployment approval is required.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve distinct observed URLs through repair counting, authority and customer output without changing historical verification.

**Architecture:** Add opt-in versioned identity primitives alongside frozen legacy helpers. Thread trusted scan-origin context through current producers and validators, then enable the new semantics only for a new internal authority seal. Keep public V6 routes and the existing request/security budgets.

**Tech Stack:** Python 3.12, JavaScript ES modules, pytest, Node 20 built-in test runner, existing Base44 package-local modules.

**Spec:** `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`, B01/B02/B21/B27 and Evidence and revision boundary. This plan is the first evidence-correctness subproject; B03–B28 work not covered here remains required by the full blueprint and is not declared complete.

## Global Constraints

- Standard 150 retains its 150 assessed-page limit. Other scan modes retain their existing assessed-page limits.
- Old signed reports are verified with their original reconstruction rules. Do not rewrite stored reports or calculate new scores while reading old reports.
- Every new assessment field affecting displayed evidence, counts, priority or scores is authenticated. Free preview cannot expose hidden findings through new fields or exports.
- No broad entity push, signing-key rotation, repository disconnection, forced reconciliation, pricing change or unrelated UI redesign.
- New identity: `evidence_url_identity_v2_published_route`; coverage: `repair_coverage_v5_published_route_identity`; invariants: `repair_invariant_v2_published_route_identity`; seal: `standard_review_snapshot_hmac_identity_v1`.
- Preserve legacy URL helpers and fixtures. Unknown identity/seal versions fail closed; a row-supplied marker cannot select historical reconstruction semantics.
- Work on `codex/full-blueprint-20260919` in the dedicated clone. Local verification has no network/service side effects; no deployment before complete blueprint acceptance.

## Review Focus

- Relative repair URLs mixed with absolute page evidence: resolve against trusted scan origin, not a representative URL or global variable. Cover in Tasks 1–2.
- Encoded delimiters, duplicate query keys and query ordering: do not merge requests merely by decoding or sorting. Cover in Tasks 1–2.
- Missing/malicious version markers on historical rows: old signed bytes stay unchanged and new envelopes reject tampering. Cover in Task 3.
- Origin, default port, Unicode and IPv6 differences between Python and JavaScript parsers: literal shared fixtures must identify any runtime disagreement. Cover in Task 1.
- Two independent 200 routes versus a verified redirect alias: retain distinct observations but reuse final content only when redirect evidence proves it. Cover in Tasks 2–4.

## Execution and verification environment

Use the prepared `.venv/bin/python` for Python and sibling `../node-v20.19.5-darwin-arm64/bin/node` for focused Node tests. Full frontend verification uses the recorded Node 20 Bookworm environment with Bash 5 and real Git history; do not use macOS Bash 3.2 for Bash-4 test fixtures. Local commits are checkpoints, not approval to push, merge or deploy.

The user explicitly instructed implementation to start after approving the written design. Continue locally without another general approval cycle. Root owns the coupled changes; independent agents may inspect and review read-only.

### Task 1: Add versioned identity primitives and shared literal fixtures

**Files:**
- Modify: `scanner-api/app/repair_coverage.py` (add new helpers without changing legacy functions).
- Modify: `base44/functions/persistDurableScanAuthorityV6/evidenceUrlIdentity.js` (add exports alongside legacy exports).
- Create: `tests/fixtures/published-evidence-url-identity.json`.
- Create: `scanner-api/tests/test_published_evidence_identity.py`.
- Create: `tests/frontend/publishedEvidenceIdentity.test.mjs`.

**Interfaces:**
- Consumes observed absolute HTTP(S) URL strings or root-relative strings plus a trusted origin.
- Produces `published_evidence_url_key(value, *, scan_origin="") -> str` and `publishedEvidenceUrlKey(value, {scanOrigin=""}={}) -> string`; invalid/unresolvable inputs return `""`.
- Preserve the request path and query exactly, strip fragments, lowercase scheme/host, remove only an explicit default port, preserve non-default ports. Resolve root-relative URLs against the origin component of the trusted scan origin. Do not treat an absolute foreign origin as the scan origin. Reject credentials, controls, backslashes, non-HTTP schemes and unresolved relative evidence.
- Unicode hostnames use the same UTS-46/IDNA normalization in both implementations; paths are never passed through a whole-URL serializer. IPv6 is validated and represented consistently.

- [ ] **Step 1: Write literal cross-runtime regression fixtures and tests.**

```python
def test_separate_routes_keep_separate_evidence_keys():
    keys = [published_evidence_url_key(url, scan_origin="https://example.com")
            for url in ["/x", "/x/", "/X", "/a%2Fb", "/a/b"]]
    assert keys == ["https://example.com/x", "https://example.com/x/",
                    "https://example.com/X", "https://example.com/a%2Fb",
                    "https://example.com/a/b"]
```

Include literal expected keys for meaningful query order/duplicates, percent escapes, host/scheme case/default ports, foreign origin, root-relative input, fragments, IDN and IPv6; invalid input expects an empty key. Assert the existing legacy helper still returns `/x` for all three case/slash variants.

- [ ] **Step 2: Run new tests before implementation.**

Run: `.venv/bin/python -m pytest scanner-api/tests/test_published_evidence_identity.py -q` and `node --test tests/frontend/publishedEvidenceIdentity.test.mjs`.
Expected: fail because the new exported function is absent, confirmed by an assertion rather than a syntax/environment failure.

- [ ] **Step 3: Add the new pure helpers.**

```python
# Contract outline: origin normalization and observed route text are separate.
def published_evidence_url_key(value, *, scan_origin=""):
    parts = _published_evidence_parts(value, scan_origin=scan_origin)
    if parts is None:
        return ""
    origin, path_and_query = parts
    return origin + path_and_query
```

`_published_evidence_parts` owns validation, origin parsing and exact path/query retention. Implement the same boundary independently in JS; neither runtime computes fixture expectations. Retain all old exports and old fixture semantics.

- [ ] **Step 4: Verify new and old identity tests.**

Run: `.venv/bin/python -m pytest scanner-api/tests/test_published_evidence_identity.py scanner-api/tests/test_evidence_url_identity.py scanner-api/tests/test_evidence_identity_properties.py -q` and `node --test tests/frontend/publishedEvidenceIdentity.test.mjs tests/frontend/evidenceUrlIdentityParity.test.mjs`.
Expected: all pass. Also run the full relevant project suites before calling this task complete; record failures by name.

- [ ] **Step 5: Inspect the diff and checkpoint only this task's files.**

```bash
git diff --check
git add scanner-api/app/repair_coverage.py base44/functions/persistDurableScanAuthorityV6/evidenceUrlIdentity.js tests/fixtures/published-evidence-url-identity.json scanner-api/tests/test_published_evidence_identity.py tests/frontend/publishedEvidenceIdentity.test.mjs
git commit -m "feat: add versioned published evidence URL identity"
```

### Task 2: Preserve observed identity through Python repair production

**Files:**
- Modify: `scanner-api/app/review_primitives.py`, `review.py`, `repair_coverage.py`, `repair_dedup.py`, `repair_contract_v2.py`, `repair_priority.py`, `repair_priority_calibration.py`, `repair_shadow_calibration.py`, `repair_architecture_priority.py`, `repair_identity.py`.
- Tests: `test_grouped_metadata_evidence.py`, `test_repair_denominator_invariants.py`, `test_group_dedup.py`, `test_repair_contract_v2.py`, `test_repair_identity.py`, `test_published_request_urls.py` under `scanner-api/tests/`.

**Interfaces:**
- Consumes Task 1 identity helper.
- Pass keyword-only `scan_origin` through evidence operations; derive once from scan-owned `crawl_scope.requested_origin`, otherwise `website_url`/`normalized_url`, never from `normalized_domain`.
- New repairs carry the new identity marker. Keep `clean_path` and `template_family_key` for classification only; evidence URLs retain original absolute/root-relative text.
- New-version `normalize_repair_scope` and invariant checks use observed identity for affected membership and exact stamped-page joins. Preserve legacy callers until Task 3 completes the atomic activation.

- [ ] **Step 1: Extend the real extraction/review regression.**

```python
def test_three_200_routes_remain_three_affected_pages():
    pages = [page("https://example.com" + path, "")
             for path in ["/x", "/x/", "/X"]]
    [fix] = metadata_fixes(pages)
    assert fix["page_count"] == 3
    assert len(fix["affected_pages"]) == 3
    assert fix["metadata_state_counts"]["missing"] == 3
```

Use the existing `page`/`metadata_fixes` helpers in `test_grouped_metadata_evidence.py`. Add separate cases for relative/absolute equivalence under trusted origin, origin distinction, aggregate `/x` not covering singleton `/x/`, and independent indexability/business-role joins. Cross-version comparisons cannot yield `verified_fixed` from ambiguous old identities.

- [ ] **Step 2: Run the focused tests and verify the undercount failure.**

Run: `.venv/bin/python -m pytest scanner-api/tests/test_grouped_metadata_evidence.py scanner-api/tests/test_repair_denominator_invariants.py scanner-api/tests/test_group_dedup.py scanner-api/tests/test_repair_identity.py -q`.
Expected: new case/slash and version-compatibility assertions fail before code changes; old assertions remain attributable.

- [ ] **Step 3: Thread the context and replace only evidence joins.**

```python
# At the orchestrator, scan_origin is derived from the trusted scan result.
scope_evidence = normalize_repair_scope(
    fix, pages, family_resolver=family_resolver, scan_origin=scan_origin,
)
# At joins/deduplication, both sides use the same observed identity.
key = published_evidence_url_key(raw_url, scan_origin=scan_origin)
```

Add `scan_origin` to called signatures before passing it. Preserve classifier normalization. Apply the same identity to canonical merge, representatives, priority denominators and verification comparability; do not merely adjust `page_count` after a lossy merge.

- [ ] **Step 4: Run affected tests and complete scanner suite.**

Run: `.venv/bin/python -m pytest scanner-api/tests -q`.
Expected: all pass, including verified redirect coalescing and the three-200-route regression. Legacy fixture expectations are retained where explicitly versioned, not rewritten wholesale.

- [ ] **Step 5: Inspect and checkpoint the Python migration.**

```bash
git diff --check
git add scanner-api/app scanner-api/tests
git commit -m "fix: preserve observed route identity through repair production"
```

### Task 3: Version authority invariants, suppression and historical reconstruction

**Files:**
- Modify package-local `evidenceUrlIdentity.js`, `repairInvariants.js`, `repairEvidence.js`, `authoritySnapshot.js`, `customerPreviewSeal.js`, `geoReadiness.js`, active V6 writer/reader `entry.ts` and `projection.js` as required.
- Update canonical/packaged counterparts only through reviewed parity requirements; preserve all historical reconstruction branches.
- Modify: `scanner-api/app/beta_revision.py`, `data/cross-runtime-release-components.json`; regenerate release artifacts through existing scripts.
- Tests: `publishedEvidenceIdentity.test.mjs`, `repairCoverageInvariants.test.mjs`, `authoritySnapshotDedup.test.mjs`, `geoAuthority.test.mjs`, `historicalAuthoritySealCompat.test.mjs`, `customerPreviewSeal.test.mjs`, `reportEvidenceRoundTripBlocker.test.mjs`.

**Interfaces:**
- `firstFailedRepairInvariant(repair, {scanOrigin="", identityVersion=""}={})` and its callers select identity only from validated producer/seal context.
- The authority predicate gets trusted origin from `scan.requested_origin`/`scan.website_url`; persisted reconstruction gets it from stored `run`.
- New signed repair evidence requires the identity marker. New internal seal includes GEO/report capabilities; existing old seals ignore injected new fields and preserve their bytes.

- [ ] **Step 1: Add real writer/invariant/HMAC regressions using existing signed fixtures.**

```javascript
const repair = {page_count: 3, affected_pages: ["/x", "/x/", "/X"],
  family_breakdown: {activity_detail: 3}, page_scope: "family"};
assert.equal(firstFailedRepairInvariant(repair, {
  scanOrigin: "https://example.com",
  identityVersion: "evidence_url_identity_v2_published_route",
}), "");
```

Add independent old-seal and new-seal persistence/readback checks. Mutating the new route, reserved escape or identity marker must invalidate new HMACs. Injecting a marker into an old row must not change reconstructed legacy bytes. A new preview retains GEO summary and exact published example URL without hidden evidence.

- [ ] **Step 2: Run these tests before implementing and confirm the intended failures.**

Run: `node --test tests/frontend/repairCoverageInvariants.test.mjs tests/frontend/authoritySnapshotDedup.test.mjs tests/frontend/geoAuthority.test.mjs tests/frontend/historicalAuthoritySealCompat.test.mjs tests/frontend/customerPreviewSeal.test.mjs tests/frontend/reportEvidenceRoundTripBlocker.test.mjs`.
Expected: new count/suppression/seal assertions fail; baseline historical assertions remain valid.

- [ ] **Step 3: Implement explicit version dispatch and sealed projection.**

```javascript
const key = identityVersion === PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
  ? (url) => publishedEvidenceUrlKey(url, {scanOrigin})
  : evidenceUrlKey;
```

Unknown versions reject before this dispatch. Require the new marker for new signed repairs; use the envelope's seal version for readers, not raw row input. Thread the same key into writer aggregate suppression. Preserve historical serializer branches; add new capabilities without changing V6 public route names.

- [ ] **Step 4: Verify authority suites, package integrity and generated contracts.**

Run focused tests above, then full frontend suite in the documented Linux environment, `node scripts/base44_release_manifest.mjs verify`, and `node scripts/generate_release_contracts.mjs --check`.
Expected: all pass, no orphan/cross-package imports, no historical signature drift.

- [ ] **Step 5: Inspect and checkpoint only reviewed migration/generated files.**

```bash
git diff --check
git add base44/functions scanner-api/app/beta_revision.py data/beta-crawler-revision.json data/cross-runtime-release-components.json src/lib/generatedReleaseContract.js tests/frontend
git commit -m "feat: seal published-route evidence with historical compatibility"
```

### Task 4: Prove the integrated user-visible path and independently review

**Files:**
- Tests: `tests/frontend/canonicalExportParity.test.mjs`, `canonicalRepairRow.test.mjs`, `evidenceUrlContract.test.mjs`; add the needed synthetic fixture in `tests/fixtures/`.
- Update: `docs/full-blueprint-progress.md` with requirement-specific results, not a full-blueprint completion claim.

**Interfaces:**
- Consumes real Python-produced new-version repair data, writer seal/persistence/readback, verified customer projection and existing card/export modules.
- Produces evidence that the original three-200-route case displays and exports three unique affected pages and cannot lose reserved escapes or origin distinctions.

- [ ] **Step 1: Add the end-to-end persisted-fixture assertions before fixing any remaining consumer seam.**

```javascript
assert.equal(customerRepair.page_count, 3);
assert.deepEqual(customerRepair.affected_pages, ["/x", "/x/", "/X"]);
assert.equal(exportedRepair.page_count, customerRepair.page_count);
assert.deepEqual(exportedRepair.affected_pages, customerRepair.affected_pages);
```

Use actual existing writer/reader/card/export fixture setup; do not mock the normalized result. Test authorized full access, preview no-leak, historical records and a real observed-redirect control separately.

- [ ] **Step 2: Run focused UI/export tests; fix only a demonstrated identity loss.**

Run: `node --test tests/frontend/canonicalExportParity.test.mjs tests/frontend/canonicalRepairRow.test.mjs tests/frontend/evidenceUrlContract.test.mjs`.
Expected: all direct evidence assertions pass; any newly exposed failure gets its own RED→GREEN fix.

- [ ] **Step 3: Run full source verification and an independent whole-diff review.**

Run full Python/scanner/frontend suites, lint, typecheck, build, release-contract and package checks. Give a fresh reviewer the actual diff, approved spec, this plan and Review Focus. Resolve important findings with reproducing tests before claiming this identity subproject complete.
Expected: direct B01/B02/B21 identity evidence confirmed; historical/privacy/security regressions pass. Full blueprint remains open for all other requirements and deployment.

- [ ] **Step 4: Record results and checkpoint test/documentation changes.**

```bash
git diff --check
git add tests/frontend tests/fixtures docs/full-blueprint-progress.md
git commit -m "test: prove published route identity through customer exports"
```
