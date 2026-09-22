# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest code/test checkpoint before this handoff refresh: `a8c270511b3863633c5c50be726c49ee162c7ff8`

## Ownership boundary

Lane C is limited to pure provider/browser evidence helpers, representative-page selection,
integrity/binding helpers, deterministic tests, fixtures and documentation. It does **not**
modify `scanner.py` / `run_scan`, global scan budgets, worker deployment configuration,
repair priority/customer scoring, authority/persistence/projection, admission,
release/deployment, schema/IAM/credentials, provider accounts, or production.

No helper in this lane performs a live CrUX/PSI/Lighthouse/browser call or creates
credentials. New behavior is unwired and shadow/off until the serialized integrator adopts it.

## Implemented contracts

Lane C currently provides:

- provider-neutral field-performance evidence with explicit connected/disconnected/
  unavailable/rate-limited/provider-error states;
- direct CrUX and PSI normalization with field CrUX and lab Lighthouse evidence separate;
- strict direct-CrUX URL/origin source identity, collection-period provenance and
  `nextgen_crux_field_dimension_v1` device context;
- source-bound PSI requested/final/component provenance plus bound integrity;
- **`nextgen_psi_field_dimension_v1`**, which derives PSI CrUX field device context only from
  the retained raw field metrics' own `formFactor` metadata and never from Lighthouse lab
  strategy; missing, partial, mixed or unknown field dimensions remain unavailable;
- strict direct-Lighthouse requested/final identity, runtime-error and failed-audit provenance;
- lab-only Lighthouse metric-unit and opportunity normalization/integrity;
- deterministic representative template/high-value sampling, final-URL deduplication and a
  hard 12-candidate ceiling plus sample binding;
- field/lab performance observation coverage and source binding;
- raw-vs-rendered critical-content parity for title/H1/canonical/indexability/main content,
  important links, structured data and product/entity facts;
- resolved-canonical parity, contract-bound parity coverage and critical-parity sufficiency;
- field-only Core Web Vitals assessment requiring trusted LCP/INP/CLS field evidence.

## Serialized integration hook

The serialized integrator, not this lane, owns execution and shared orchestration.

1. After accepted retained-page/template evidence exists, call
   `select_representative_performance_pages(...)` only to produce bounded candidates.
2. Require `validate_representative_sample_binding(authoritative_pages, sample)` before the
   sample is trusted. A valid sample is not an execution entitlement.
3. Feed only an integrator-budget-approved subset into the existing safe browser/render path.
4. For parity evidence, use `compare_critical_content_parity_resolved(...)`, validate it,
   assess sufficiency, validate sufficiency, and aggregate coverage separately.
5. For direct CrUX, use `normalize_crux_query_record_evidence_bound(...)` then
   `validate_bound_crux_contract(...)`; optional device context comes only after that via
   `normalize_crux_field_dimension_context(...)` + its integrity validator.
6. For PSI, use `normalize_pagespeed_insights_evidence_bound(...)` then
   `validate_bound_pagespeed_contract(...)`.
7. After a bound PSI contract succeeds, optional PSI **field** device context comes from
   `normalize_psi_field_dimension_context(raw_psi_payload, bound_psi)` plus
   `validate_psi_field_dimension_contract(...)`. Do not use Lighthouse strategy to populate it.
8. For direct Lighthouse, use `normalize_lighthouse_evidence_bound(...)` plus its integrity
   validator; metric-unit and opportunity artifacts remain lab-only.
9. Bind sampled observation sources before trusting aggregate performance coverage.
10. Keep field and lab envelopes and device contexts separate through any future
    persistence/authority/customer logic. Repair priority/customer scoring remain integrator-owned.

A 500/1,000-page adaptive crawl must never imply 500/1,000 browser or Lighthouse executions.

## Verification evidence

Recorded focused checkpoints include the prior **193 focused tests across 17 test files** plus
this PSI field-dimension slice: **13/13 passed in a hermetic lane harness** and source/test
`py_compile` passed. Lane C therefore contains **206 focused tests across 18 test files**.

**206/206 exact-repository execution is not claimed.** The available execution container
cannot resolve GitHub to materialize the complete branch, and this integration-target draft
does not receive the normal main-target PR CI workflow.

Required exact-head gate:

```bash
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_psi_integrity.py \
  tests/test_nextgen_browser_performance_psi_dimensions.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance_source_binding.py \
  tests/test_nextgen_browser_performance_parity_hardening.py \
  tests/test_nextgen_browser_performance_lighthouse_provenance.py \
  tests/test_nextgen_browser_performance_crux_provenance.py \
  tests/test_nextgen_browser_performance_crux_dimensions.py \
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
  app/nextgen_browser_performance_psi_dimensions.py \
  app/nextgen_browser_performance_coverage.py \
  app/nextgen_browser_performance_sample_binding.py \
  app/nextgen_browser_performance_evidence_coverage.py \
  app/nextgen_browser_performance_source_binding.py \
  app/nextgen_browser_performance_parity_hardening.py \
  app/nextgen_browser_performance_lighthouse_provenance.py \
  app/nextgen_browser_performance_crux_provenance.py \
  app/nextgen_browser_performance_crux_dimensions.py \
  app/nextgen_browser_performance_cwv.py \
  app/nextgen_browser_performance_lighthouse_units.py \
  app/nextgen_browser_performance_parity_sufficiency.py \
  app/nextgen_browser_performance_lighthouse_opportunities.py \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_psi_integrity.py \
  tests/test_nextgen_browser_performance_psi_dimensions.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance_source_binding.py \
  tests/test_nextgen_browser_performance_parity_hardening.py \
  tests/test_nextgen_browser_performance_lighthouse_provenance.py \
  tests/test_nextgen_browser_performance_crux_provenance.py \
  tests/test_nextgen_browser_performance_crux_dimensions.py \
  tests/test_nextgen_browser_performance_cwv.py \
  tests/test_nextgen_browser_performance_lighthouse_units.py \
  tests/test_nextgen_browser_performance_parity_sufficiency.py \
  tests/test_nextgen_browser_performance_lighthouse_opportunities.py
```

## Current risks

The main evidence risk is still treating unavailable, mismatched, partial, unit-ambiguous or
failed provider/render observations as measured defects. Field and lab evidence must remain
separate.

PSI now has an explicit additional guard: Lighthouse `mobile`/`desktop` strategy cannot fill a
missing CrUX field form factor. PSI field device context is connected only when the retained
field metric objects themselves provide one consistent supported form factor.

The representative sample ceiling remains a candidate bound, not an execution entitlement.

## Rollback

Because the lane remains unwired from shared orchestration, rollback is deletion of Lane-C
helper/test/docs/fixture files. No data migration, authority rewrite, customer projection
rewrite, or historical reconstruction change is required.
