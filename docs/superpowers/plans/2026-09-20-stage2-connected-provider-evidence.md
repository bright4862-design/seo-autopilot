# Stage 2 connected-provider evidence checkpoint — 2026-09-20

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

Integration branch: `agent/full-blueprint-stage2-coverage-b06-20260919` / PR #303.

## Exact verified executable checkpoint

Code/test SHA: `d8eb5ab82cf9b824b57b06551ee338601dc557e5`

FixList CI: `35485946042` — **SUCCESS** on both jobs.

Fresh CI evidence on the exact code SHA:

- immutable checkout: passed;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,968 passed / 18 intentional skips**;
- focused connected-provider regressions: **7 passed** inside the scanner suite;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:7e7b06697fca5734b4775f5376d3f2ade6eafe93a56f676dc57113625c86b7c9`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow installed Node `20.20.2`. Do not describe this run as Node 20.19.5 runtime evidence.

## Slice implemented

New files:

- `scanner-api/app/stage2_connected_provider_evidence.py`
- `scanner-api/tests/test_stage2_connected_provider_evidence.py`

This slice hardens the optional connected-provider boundary needed by B17/B18. It does **not** create a provider connection, perform network I/O, or claim provider coverage.

### B17 optional CrUX boundary

`build_crux_scan_evidence` accepts only a versioned integration payload supplied by a future authenticated connector layer. It requires:

- explicit `connected` / `disconnected` / `unavailable` state;
- owner authorization before connected evidence can be admitted;
- an exact source `scan_id` matching the current scan;
- explicit observation date and scope;
- the existing bounded CrUX adapter, which retains only LCP, INP and CLS.

Stale evidence loses metrics. Cross-scan, unauthorized, malformed and disconnected evidence cannot silently become a current performance claim. `coverage_complete_claim` is always false.

This does **not** close B17: directly measured transfer bytes are still open, and the authenticated provider caller/result-authority wiring is still serialized integration work.

### B18 optional GSC boundary

`build_gsc_scan_evidence` requires the same owner-authorization and exact-scan identity gates, plus an exact whitelist of retained Standard-150 assessed URLs. It:

- refuses an assessed set above 150 instead of silently truncating it;
- retains metrics only for exact URLs present in the current retained scan set;
- does not case-fold, query-strip or otherwise normalize one published URL into another;
- drops arbitrary fields such as search-query text;
- retains only bounded clicks, impressions, position and explicit index state through the existing adapter;
- strips stale metrics;
- rejects cross-scan rows;
- fails a conflicting duplicate URL row closed instead of picking one value;
- never claims full provider/site coverage from the observed subset.

This does **not** close B18: no real GSC connection was fabricated, and authenticated connector/authority/customer integration remains open.

## Adversarial regression coverage

The seven focused tests prove:

1. disconnected CrUX and connected-but-unauthorized CrUX remain explicit unknown states;
2. cross-scan and stale CrUX payloads cannot expose metrics;
3. current authorized CrUX retains only the approved bounded metrics plus scope/time;
4. disconnected, unauthorized and cross-scan GSC payloads cannot expose page metrics;
5. GSC page metrics are limited to exact current assessed URLs, with same-looking non-assessed URLs rejected and unapproved fields dropped;
6. stale GSC metrics are removed and conflicting duplicate rows fail closed;
7. a provider assessed-URL set above Standard 150 raises rather than being silently truncated.

## Stage-2 requirement state after this slice

- B06–B12: materially integrated as recorded in the current progress/handoff ledger.
- B13/B14: page evidence and bounded cross-page aggregate exist, but the aggregate is still not attached to the shared top-level `run_scan`/authority result.
- B15: retained-page contextual freshness producer is integrated and green.
- B16: exact URL-variant evidence is integrated.
- B17: decoded/inline bytes plus the new fail-closed optional CrUX admission contract exist; **direct measured transfer bytes and shared provider/result wiring remain open**.
- B18: fail-closed optional GSC admission contract exists; **authenticated provider/result wiring remains open**.

No customer-visible finding, score adjustment, repair card, provider connection, schema change, request-budget expansion or production action was introduced by this slice.

## Review state

CodeRabbit commit status is green, but a status check is not substituted for the required fresh independent review of the complete Stage-2 shared source. Final Stage-2 completion still requires independent review with concrete findings closed by regressions and a final exact-head CI after the remaining shared wiring.

## Exact next action

Remain on Stage 2. Attach the existing B13/B14 bounded scan aggregate to the shared scanner/authority result without altering pages, scoring or request budgets. Implement direct B17 transfer-body measurement at the hardened fetch boundary and carry only actually measured bytes into page-weight evidence. Then connect B17/B18 optional-provider envelopes only through an authenticated exact-scan integration seam, add downstream authority/persistence/customer regressions for any evidence that becomes displayed, and run fresh final review + exact-head CI before beginning Stage 3 shared integration.

No merge, deployment, `main` change, worker/admission mutation, live scan, provider connection, schema/secret change or customer-data write is authorized or performed by this checkpoint.
