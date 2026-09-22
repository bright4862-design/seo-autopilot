# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest code/test checkpoint before this handoff refresh: `b73610ca88a22fb567a7beb07940ce00b1e4c96b`

## Ownership boundary

Lane C is limited to pure provider/browser evidence helpers, representative-page selection,
integrity/binding helpers, deterministic tests, fixtures and documentation. It does **not**
modify `scanner.py` / `run_scan`, global scan budgets, worker deployment configuration,
repair priority/customer scoring, authority/persistence/projection, admission,
release/deployment, schema/IAM/credentials, provider accounts, or production.

No helper in this lane performs a live CrUX/PSI/Lighthouse/browser call or creates
credentials. New behavior is unwired and shadow/off until the serialized integrator
explicitly adopts it.

## Implemented contracts

Lane C currently provides:

- provider-neutral field-performance evidence with explicit `connected`, `disconnected`,
  `unavailable`, `rate_limited`, and `provider_error` states;
- direct CrUX and PageSpeed Insights normalization with CrUX field evidence and Lighthouse
  lab evidence kept in separate envelopes;
- strict direct-CrUX URL/origin scope, source identity and collection-period provenance;
- source-bound PSI requested/final/component provenance and a fail-closed integrity layer;
- bounded Lighthouse metric/opportunity extraction with direct-Lighthouse requested/final
  identity, runtime-error and failed-audit provenance;
- lab-only Lighthouse metric-unit normalization so timing metrics are trusted only with an
  explicit timing unit and CLS only with an explicit score/unitless unit;
- lab-only `nextgen_lighthouse_opportunity_evidence_v1`, which rebuilds allowlisted
  Lighthouse opportunity evidence from the raw payload plus the source-bound Lighthouse
  envelope. Explicit `overallSavingsMs` / `overallSavingsBytes` fields remain typed;
  generic `numericValue` is used only when `numericUnit` explicitly says milliseconds or
  bytes; missing/unsupported units are never guessed; credential-bearing provider identities
  and raw/bound redirect mismatches fail closed;
- deterministic representative template/high-value sampling, final-URL deduplication and a
  hard 12-candidate ceiling;
- representative-sample binding that recomputes the sample from the authoritative candidate
  population before browser/provider work can trust it;
- performance evidence coverage that keeps field and lab attempted/connected/unassessed
  coverage separate;
- observation-source binding so connected field/lab evidence must belong to the sampled
  request, its origin, or an explicit provenance-backed redirect;
- raw-vs-rendered critical-content parity evidence for title/H1/canonical/indexability,
  main-content presence, important links, structured data and product/entity facts;
- resolved-canonical parity so relative and protocol-relative canonicals are compared against
  the actual document identity;
- contract-bound parity coverage that separates completed, failed/unverifiable and unassessed
  selected pages;
- `nextgen_critical_parity_sufficiency_v1`, which requires bilateral observation of title,
  H1, canonical, indexability, main-content presence and important links before a no-delta
  row becomes `verified_match`. A contract-valid changed field can still establish
  `verified_delta` while unrelated fields remain unassessed;
- field-only `nextgen_cwv_field_assessment_v1`, which requires trusted CrUX-style LCP/INP/CLS
  field evidence and never substitutes Lighthouse lab metrics.

## Serialized integration hook

The serialized integrator, not this lane, owns execution and shared orchestration.

1. After accepted retained-page/template evidence exists, call
   `select_representative_performance_pages(...)` only to produce bounded candidates.
2. Before trusting that sample, call
   `validate_representative_sample_binding(authoritative_pages, sample)`. A valid binding
   proves deterministic selection only; it is **not** permission to execute all candidates.
3. Feed only an integrator-budget-approved subset into the existing safe browser/render path,
   preserving current DNS/SSRF/redirect/body/deadline/cancellation controls.
4. For parity evidence, prefer `compare_critical_content_parity_resolved(...)`, validate with
   `validate_resolved_critical_parity_contract(...)`, then call
   `assess_critical_parity_sufficiency(...)` before interpreting a matched row as sufficiently
   observed. Bind that derived assessment with `validate_critical_parity_sufficiency(...)`.
5. Aggregate browser execution coverage separately with
   `summarize_resolved_critical_parity_coverage(...)`.
6. For direct CrUX `queryRecord` payloads, prefer
   `normalize_crux_query_record_evidence_bound(...)`, then require
   `validate_bound_crux_contract(...).valid` before trusting connected field evidence.
7. For PSI payloads, prefer `normalize_pagespeed_insights_evidence_bound(...)`, then require
   `validate_bound_pagespeed_contract(...).valid` before trusting either connected component.
8. For direct Lighthouse lab payloads, prefer `normalize_lighthouse_evidence_bound(...)`, then
   require `validate_bound_lighthouse_contract(...).valid`.
9. If canonical lab metric units are needed, call `normalize_lighthouse_metric_units(...)` and
   require `validate_lighthouse_metric_unit_contract(...).valid`.
10. If Lighthouse opportunity savings are needed, call
    `normalize_lighthouse_opportunity_evidence(raw_lighthouse_payload, bound_lab)` and require
    `validate_lighthouse_opportunity_contract(raw_lighthouse_payload, bound_lab, artifact).valid`.
    This derived artifact is lab-only and must not become field evidence.
11. Assemble already-observed provider results under sampled request identities, then require
    `validate_performance_observation_source_binding(sample, observations)` before aggregate
    coverage is trusted.
12. Only after source binding succeeds, call `summarize_performance_evidence_coverage(...)`.
13. For trusted direct-CrUX or PSI **field** evidence, the integrator may optionally call
    `assess_core_web_vitals_field_evidence(field)`. Do not substitute Lighthouse lab metrics.
14. Keep field and lab envelopes separate through any future persistence/authority/customer
    logic. Repair priority/customer scoring remain integrator-owned.

A 500/1,000-page adaptive crawl must never imply 500/1,000 browser or Lighthouse executions.

## Verification evidence

Recorded focused checkpoints include:

- original repository-shaped checkpoint: 17 tests passed;
- provider shape: 8/8;
- PSI provenance: 10/10;
- parity coverage: 9/9;
- representative-sample binding: 9/9;
- field/lab evidence coverage: 9/9;
- performance observation source binding: 10/10;
- resolved-canonical/contract-bound parity: 10/10;
- direct Lighthouse provenance/integrity: 10/10;
- direct CrUX provenance/integrity: 10/10;
- PSI bound integrity: 12/12;
- field-only CWV assessment: 10/10;
- Lighthouse lab metric-unit normalization/integrity: 12/12;
- critical parity sufficiency/integrity: 11/11;
- Lighthouse opportunity unit/provenance hardening: **13/13 in 0.06s**; source/test
  `py_compile` passed.

Lane C now contains **180 focused tests across sixteen test files**. **180/180 exact-repository
execution is not claimed.** The available execution container cannot resolve GitHub to
materialize the full branch, and this integration-target draft does not receive the normal
main-target PR CI workflow. Exact-head repository execution remains an integration-readiness
gate.

Required exact-head gate:

```bash
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_psi_integrity.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance_source_binding.py \
  tests/test_nextgen_browser_performance_parity_hardening.py \
  tests/test_nextgen_browser_performance_lighthouse_provenance.py \
  tests/test_nextgen_browser_performance_crux_provenance.py \
  tests/test_nextgen_browser_performance_cwv.py \
  tests/test_nextgen_browser_performance_lighthouse_units.py \
  tests/test_nextgen_browser_performance_parity_sufficiency.py \
  tests/test_nextgen_browser_performance_lighthouse_opportunities.py

python -m py_compile \
  app/nextgen_browser_performance.py \
  app/nextgen_browser_performance_contract.py \
  app/nextgen_browser_performance_provider.py \
  app/nextgen_browser_performance_psi_provenance.py \
  app/nextgen_browser_performance_psi_integrity.py \
  app/nextgen_browser_performance_coverage.py \
  app/nextgen_browser_performance_sample_binding.py \
  app/nextgen_browser_performance_evidence_coverage.py \
  app/nextgen_browser_performance_source_binding.py \
  app/nextgen_browser_performance_parity_hardening.py \
  app/nextgen_browser_performance_lighthouse_provenance.py \
  app/nextgen_browser_performance_crux_provenance.py \
  app/nextgen_browser_performance_cwv.py \
  app/nextgen_browser_performance_lighthouse_units.py \
  app/nextgen_browser_performance_parity_sufficiency.py \
  app/nextgen_browser_performance_lighthouse_opportunities.py \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_psi_integrity.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance_source_binding.py \
  tests/test_nextgen_browser_performance_parity_hardening.py \
  tests/test_nextgen_browser_performance_lighthouse_provenance.py \
  tests/test_nextgen_browser_performance_crux_provenance.py \
  tests/test_nextgen_browser_performance_cwv.py \
  tests/test_nextgen_browser_performance_lighthouse_units.py \
  tests/test_nextgen_browser_performance_parity_sufficiency.py \
  tests/test_nextgen_browser_performance_lighthouse_opportunities.py
```

## Current risks

The main evidence risk remains treating unavailable, mismatched, partial, unit-ambiguous or
failed provider/render observations as measured defects. Lane-C contracts therefore preserve
unknown/not-verified states and keep CrUX field evidence separate from Lighthouse lab evidence.

Lighthouse opportunities need special care because `numericValue` is audit-specific. The new
opportunity contract does not infer a savings unit: it accepts explicitly typed provider
savings fields, or an explicit millisecond/byte `numericUnit`, and otherwise excludes the
ambiguous numeric value. This derived evidence remains lab-only.

The representative sample ceiling is only a candidate bound, not an execution entitlement.

## Rollback

Because this lane remains unwired from shared orchestration, rollback is deletion of the
Lane-C helper/test/docs/fixture files. No data migration, authority rewrite, customer
projection rewrite, or historical reconstruction change is required.
