# Customer Result Truthfulness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FixList page counts, section guidance, grouped-card counts, labels, links, and score messaging accurate and understandable.

**Architecture:** Add a pure page-accounting helper between persisted ScanRun evidence and the FixList UI. Keep ranked focused-scan candidates separate from complete page arithmetic, and regenerate customer card wording only after grouping has produced final counts.

**Tech Stack:** React 18, JavaScript ES modules, Node test runner, Python/pytest scanner regressions.

**Spec:** `docs/superpowers/specs/2026-09-05-matrix-truthfulness-and-worker-reliability-design.md`

## Global Constraints

- Preserve Standard 150 and the hard `pages_crawled <= 150` limit.
- Preserve PR #252 URL safety, vocabulary, same-origin sitemap, and `health_score_v3_cosmetic_capped` behavior.
- Display `/` as `Homepage (/)`.
- Displayed page-accounting rows plus the remainder must equal `pages_found` exactly.
- Do not imply ranked follow-up sections are an exhaustive site inventory.
- Never merge repairs without the scanner’s persisted repair identity.

---

### Task 1: Exact Page Accounting Model

**Files:**
- Create: `src/lib/pageAccounting.js`
- Create: `tests/frontend/pageAccounting.test.mjs`

**Interfaces:**
- Consumes: `record.pages_found`, `record.sampling_evidence`, and ranked section objects from `focusedPathSections(record)`.
- Produces: `buildPageAccounting(record, sections): { total, namedTotal, remainder, rows, isPartial }`.

- [ ] **Step 1: Write failing Wecandoo and IKEA accounting tests**

```js
test("named sections plus other pages equal the authoritative total", () => {
  const result = buildPageAccounting(
    { pages_found: 5000 },
    [
      { requested_path_prefix: "/atelier", label: "Atelier section", discovered: 2947 },
      { requested_path_prefix: "/ateliers", label: "Ateliers section", discovered: 2051 },
    ],
  );
  assert.equal(result.namedTotal, 4998);
  assert.equal(result.remainder, 2);
  assert.equal(result.rows.reduce((sum, row) => sum + row.count, 0), 5000);
});

test("a partial focused inventory exposes its full unexplained remainder", () => {
  const result = buildPageAccounting(
    { pages_found: 1200 },
    [{ requested_path_prefix: "/fr", label: "FR folder", discovered: 417 }],
  );
  assert.equal(result.remainder, 783);
  assert.equal(result.isPartial, true);
});
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `node --test tests/frontend/pageAccounting.test.mjs`  
Expected: FAIL because `src/lib/pageAccounting.js` does not exist.

- [ ] **Step 3: Implement bounded, deduplicated accounting**

```js
const finiteCount = (value) => {
  const count = Number(value);
  return Number.isFinite(count) ? Math.max(0, Math.trunc(count)) : 0;
};

export function buildPageAccounting(record = {}, sections = []) {
  const total = finiteCount(record?.pages_found);
  const seen = new Set();
  let remaining = total;
  const namedRows = [];
  for (const section of Array.isArray(sections) ? sections : []) {
    const prefix = String(section?.requested_path_prefix || "").trim().toLowerCase();
    if (!prefix || seen.has(prefix) || remaining <= 0) continue;
    seen.add(prefix);
    const count = Math.min(finiteCount(section?.discovered), remaining);
    if (count <= 0) continue;
    namedRows.push({ key: prefix, label: section.label || prefix, path: section.requested_path_prefix, count });
    remaining -= count;
  }
  const remainder = remaining;
  const rows = remainder > 0
    ? [...namedRows, { key: "other", label: "Homepage and other pages", path: "", count: remainder }]
    : namedRows;
  return { total, namedTotal: total - remainder, remainder, rows, isPartial: remainder > 0 };
}
```

- [ ] **Step 4: Add overlap, duplicate, invalid-count, and over-total tests**

```js
test("duplicate and over-total rows never exceed pages_found", () => {
  const result = buildPageAccounting(
    { pages_found: 10 },
    [
      { requested_path_prefix: "/fr", discovered: 8 },
      { requested_path_prefix: "/FR", discovered: 8 },
      { requested_path_prefix: "/en", discovered: 20 },
    ],
  );
  assert.deepEqual(result.rows.map((row) => row.count), [8, 2]);
  assert.equal(result.rows.reduce((sum, row) => sum + row.count, 0), 10);
});
```

- [ ] **Step 5: Run tests and commit**

Run: `node --test tests/frontend/pageAccounting.test.mjs`  
Expected: PASS.

```bash
git add src/lib/pageAccounting.js tests/frontend/pageAccounting.test.mjs
git commit -m "fix(fixlist): reconcile discovered page accounting"
```

### Task 2: Honest Section UI and Homepage Links

**Files:**
- Modify: `src/lib/evidenceUrl.js`
- Modify: `src/pages/FixList.jsx`
- Modify: `tests/frontend/matrixRunFindings.test.mjs`
- Modify: `tests/frontend/resultsPresentationContract.test.mjs`

**Interfaces:**
- Consumes: `buildPageAccounting(record, focusedSections)` and existing `evidenceLink(page, websiteUrl)`.
- Produces: a “Pages found” accounting block and a separately named “Sections to scan next” action block.

- [ ] **Step 1: Add failing UI and homepage-label assertions**

```js
test("the root page has an explicit customer label", () => {
  assert.equal(evidenceDisplayLabel("/"), "Homepage (/)");
  assert.equal(evidenceLink("/", "https://example.com").href, "https://example.com/");
});

test("follow-up sections are not presented as a complete inventory", () => {
  assert.match(page, /Sections to scan next/);
  assert.doesNotMatch(page, />\s*Site sections discovered\s*</);
  assert.match(page, /Homepage and other pages/);
});
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `node --test tests/frontend/matrixRunFindings.test.mjs tests/frontend/resultsPresentationContract.test.mjs`  
Expected: FAIL on the old heading and `Homepage · /` label.

- [ ] **Step 3: Change the shared root label**

In `evidenceDisplayLabel(page)` return `Homepage (/)` when the normalized path is `/`. Do not change `resolveEvidenceUrl` or its protocol allowlist.

- [ ] **Step 4: Integrate page accounting in FixList**

```jsx
const pageAccounting = useMemo(
  () => buildPageAccounting(scanRecord, focusedSections),
  [scanRecord, focusedSections],
);
```

Render a “Pages found” block whose rows show `row.label` and `formatCount(row.count)`, followed by an explicit total. Rename the existing action heading to “Sections to scan next” and explain that the list is a ranked set of optional separate scans.

- [ ] **Step 5: Run focused tests and commit**

Run: `node --test tests/frontend/evidenceUrl.test.mjs tests/frontend/matrixRunFindings.test.mjs tests/frontend/resultsPresentationContract.test.mjs tests/frontend/focusedScanScope.test.mjs`  
Expected: PASS.

```bash
git add src/lib/evidenceUrl.js src/pages/FixList.jsx tests/frontend
git commit -m "fix(fixlist): explain pages found and follow-up sections"
```

### Task 3: Regenerate Grouped Counts After Merging

**Files:**
- Modify: `src/lib/repairCardModel.js`
- Modify: `src/components/scan/ScanWebsiteForm.jsx`
- Modify: `tests/frontend/repairPriorityPresentation.test.mjs`
- Modify: `tests/frontend/repairGroupSummary.test.mjs`

**Interfaces:**
- Consumes: final merged `affected_pages`, `page_count`, and `family_breakdown`.
- Produces: customer text whose numeric claims match final merged evidence.

- [ ] **Step 1: Add failing merged-count tests**

```js
test("merged customer actions derive the Where line from final evidence", () => {
  const cards = buildRepairCards([
    repair({ id: "a", repair_fingerprint: "same", affected_pages: ["/a"] }),
    repair({ id: "b", repair_fingerprint: "same", affected_pages: ["/b", "/c"] }),
  ]);
  assert.equal(cards.length, 1);
  assert.match(cards[0].where, /^3 pages/);
  assert.doesNotMatch(cards[0].where, /^1 page/);
});
```

Add a source-contract assertion that grouped legacy records initialize `current_value` from the final group rather than copying the first child’s count-bearing sentence.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `node --test tests/frontend/repairPriorityPresentation.test.mjs tests/frontend/repairGroupSummary.test.mjs`  
Expected: at least the legacy stale-count assertion fails.

- [ ] **Step 3: Generate legacy grouped current text after aggregation**

In `groupAndSortFixes`, do not inherit `current_value` when a group is created. After `page_count` is finalized, set an evidence-only value such as:

```js
existing.current_value = `${existing.page_count} affected ${existing.page_count === 1 ? "page" : "pages"} in this group.`;
```

Keep canonical `buildRepairCard` count and `whereLine` derivation unchanged except for any minimal correction proven by the new test.

- [ ] **Step 4: Run focused tests and commit**

Run: `node --test tests/frontend/repairPriorityPresentation.test.mjs tests/frontend/repairGroupSummary.test.mjs tests/frontend/ikeCustomerFixList.test.mjs`  
Expected: PASS.

```bash
git add src/lib/repairCardModel.js src/components/scan/ScanWebsiteForm.jsx tests/frontend
git commit -m "fix(fixlist): derive grouped copy from final page counts"
```

### Task 4: Preserve Score and Vocabulary Contracts

**Files:**
- Modify: `scanner-api/tests/test_matrix_run_findings.py`
- Modify: `tests/frontend/matrixRunFindings.test.mjs`

**Interfaces:**
- Consumes: `compute_health_score_breakdown` and `customerCopyForFix`.
- Produces: regression proof only; no new score version.

- [ ] **Step 1: Add regression assertions for the accepted contract**

```python
def test_score_contract_stays_on_cosmetic_capped_v3():
    result = compute_health_score_breakdown(COSMETIC_SITE, FINGERPRINT)
    assert result["version"] == "health_score_v3_cosmetic_capped"
    assert 55 <= result["score"] <= 75
```

Retain the existing headline jargon allowlist test and extend it only for customer-visible words observed in this matrix.

- [ ] **Step 2: Run score and vocabulary tests**

Run: `python -m pytest scanner-api/tests/test_matrix_run_findings.py -q && node --test tests/frontend/matrixRunFindings.test.mjs`  
Expected: PASS without changing production score constants.

- [ ] **Step 3: Commit regression coverage**

```bash
git add scanner-api/tests/test_matrix_run_findings.py tests/frontend/matrixRunFindings.test.mjs
git commit -m "test: freeze matrix score and vocabulary fixes"
```

### Task 5: Customer-Result Verification Gate

**Files:**
- Modify only if a test exposes a defect in files already listed above.

**Interfaces:**
- Consumes: all customer-result changes.
- Produces: a verified frontend/scanner patch ready for integration.

- [ ] **Step 1: Run frontend gates**

Run: `pnpm lint && pnpm typecheck && pnpm test:frontend && pnpm build`  
Expected: all commands exit 0.

- [ ] **Step 2: Run focused scanner gates**

Run: `python -m pytest scanner-api/tests/test_matrix_run_findings.py scanner-api/tests/test_review_calibration.py -q`  
Expected: PASS.

- [ ] **Step 3: Inspect scope and commit only necessary repairs**

Run: `git diff --check && git status --short && git diff --stat origin/main...HEAD`  
Expected: no unrelated Base44, reconciliation, classifier, or Premium changes.

