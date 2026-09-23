# Trustworthy rescan comparison and customer guidance checkpoint

Base: `ai-layer/integration-20260923` at `776e964b23b81a4759a590969ce981789a30d6d7`.
Production main was refreshed at `c1080d75f7d1aacd748e74009be7a6c15aa40a93`.
This is a reviewed integration candidate. No production route, shared V8 reader/writer, authority snapshot format, entity schema, `FixList.jsx`, release manifest, or deployment changed. The serialized AI Integrator remains the sole owner of those surfaces.

## What this checkpoint delivers

- Authenticated rescan adapter: verifies both existing result HMACs and a separate signed lineage artifact before calling the existing comparator. It never accepts client repair arrays, page evidence, comparison states, or authority receipts as proof.
- Actual Python completion → V8 writer → JSON persistence → V8 reader → Python comparison adapter → customer panel model acceptance.
- Disjoint comparison counts: verified returns are no longer counted again in the unmatched-current bucket. Contradictory totals fail closed.
- Customer guidance composition: meaningful role selection over reviewed copy, preserved scanner instructions, and a separate deterministic execution plan.
- Reuses selected code/tests from #350, #351, #353 and #354. It incorporates the reviewed v2 role wording. These are dependencies carried into one reviewable candidate, not new competing implementations. Other open documentation PRs remain separate.

## Why the extra comparison boundary is necessary

The V8 authority snapshot does not include `previous_scan_id`. A regression using actual writer/reader code proves that changing that persisted pointer leaves reconstructed bytes and their HMAC unchanged. A valid result proof therefore cannot authenticate a relationship between two scans.

`build_scan_comparison_lineage_v1` is an **internal producer**, not a customer operation. Its caller must load the pointer through the existing service-owned, owner/project-bound ScanRun path. It verifies both snapshots, requires the supplied pointer to match the previous snapshot, and signs an artifact in a separate integrity domain binding owner, project, origin/scope, both scan IDs and both exact result proofs.

`build_authenticated_scan_comparison_v1` verifies the result proofs and artifact again. It requires the expected current scan/owner/project, compatible origins and scope, chronological seals, authoritative terminal states, coherent counts and consistent technical identity. Matching fingerprints cannot bypass incompatible rule/profile/URL semantics. Unknown historical identity remains unverified. Mutable workflow status never establishes repair truth.

The artifact's signature attests the internal producer's relationship assertion. It cannot prove how the caller obtained the pointer. Do not expose artifact issuance to a browser or accept its inputs from customer JSON. This adapter also does not grant paid access or perform release compatibility checks; existing reader gates remain mandatory.

Durable snapshots do not contain the complete current-page evidence population. This adapter deliberately supplies `current_pages=[]`. Missing historical repairs remain `could_not_verify`, even when stable identity exists. Verified fixed results require the separate genuine recheck evidence path; never manufacture page observations from affected URL lists. Published URL identity is carried into the existing comparator, preserving query/trailing-slash distinctions.

The return object includes `customer_projection_authorized=false`. It is an internal candidate, not permission to deliver its contents. The customer may receive only the validated presentation after server access/identity/release gates; never expose snapshots, proofs or internal transport wholesale.

## Customer wording

The five panel labels are **Verified fixed**, **Still detected**, **Returned**, **Not matched**, and **Could not verify**.

“Not matched” describes current findings whose reference identity could not be matched to previous findings. It must not be called “newly observed” or “new problems”: a provisional identity can change even when rule and URL remain the same. Tests preserve this counterexample. Coverage and identity differences are explicitly explained.

Scores remain descriptive. Different sample sizes, or equal counts with different page populations, cannot establish that the website improved or regressed.

Role copy keeps the prior wording review: missing H1 does not imply a missing visible headline; potential orphans remain scoped to checked pages; repeated titles do not establish a shared template defect. No ranking, traffic or provider-outcome promise is added.

## Guidance integration contract

`CustomerRepairGuidance` composes the existing card renderer without joining raw rows to projected cards by index, title or rule. V8 authenticates the whole row population; per-row scan IDs may be absent. The component requires matching authenticated population IDs and rejects conflicting local source/card identities when present.

```jsx
<CustomerRepairGuidance
  sourceItems={authenticatedCanonicalRows}
  cards={customerRepairCards}
  trustedScanId={currentScanId}
  sourceScanId={authenticatedBundle.scan_id}
  cardsScanId={authenticatedBundle.scan_id}
  authorityVerified={hasAuthoritativeScan}
  renderCards={(cards, { explanationForCard }) => (
    <CustomerRepairList
      cards={cards}
      explanationForCard={explanationForCard}
      websiteUrl={scanRecord.website_url}
    />
  )}
/>
```

The integrator should pass `explanationForCard` through the existing list to each card and replace only its explanation heading/text. Keep `card.whatToChange`, evidence, priority and ordering intact. Do not pass projected cards into `repairSuggestion()`; they lack its original instruction fields. Unsupported rules keep their existing explanation. An entirely unmapped list has no ineffective selector. Selection is per-view, resets for a different scan, and makes no model call.

The separate implementation view consumes original authorized canonical rows. It uses `orderedRepairIds` for sequence and groups only for related-work context. It never flattens groups into a new order. Missing/duplicate IDs hide the plan. Instructions reuse `repairSuggestion(rawRow)` and its existing scanner precedence. Confirm the full entitled population before mounting this component; no preview expansion.

## Verification

- 123 focused frontend/role/plan/panel/transport tests passed, including real cross-language V8 persistence and four new authority adapter acceptance tests.
- 226 focused Python comparison, identity and targeted-verification tests passed, including 68 new authority adapter tests.
- Changed frontend ESLint, repository typecheck, production build and diff whitespace checks passed. Build retains existing stale Browserslist and large-chunk warnings.
- Independent review found and resolved stale projected-card identity handling and the overly strong “newly observed” label.
- JSX rendering and controlled selector changes were exercised. A live browser/mobile session, full repository suites, exact-head CI and production acceptance were not run for this checkpoint. Integration-target PRs do not trigger the repository workflow currently restricted to main.

## Next serialized integration actions

1. Ingest this candidate after review, reconciling overlap with #350/#351/#353/#354; do not stack duplicate alternative implementations.
2. In the existing authorized read path, load both exact scans and validate paid access, owner/project, readable release, terminal authority and server-owned lineage. Use a bounded internal transport to the Python adapter, never a customer-supplied snapshot or pointer. The serving route and its timeout/error behavior remain to be implemented by the integrator.
3. Issue/verify the detached lineage artifact on that trusted path. Return only validated comparison presentation. Comparison failure should show an unavailable comparison while leaving the separately verified current FixList readable.
4. Mount the comparison panel with the exact current scan ID and comparison-specific verified state; the current scan's authority flag alone cannot authenticate the comparison.
5. Mount the guidance composition above canonical full-access repairs using the contract above, preserving existing sections and evidence controls.
6. Exercise real rerun → display → reload/history, forged/mismatched pair rejection, changed-sample caution, role selection and mobile layout. Promote only from the exact integrated release after existing acceptance gates.

H1-1/H1-2/H1-3 are advanced by this checkpoint, not marked released. Grok/chat, runtime models, GEO scoring thresholds and the Standard 150 crawl budget remain outside this change.
