# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest code/test checkpoint before this handoff refresh: `c858aac5022929939e992f8cbc2183e613a3dd86`

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
- `nextgen_psi_field_dimension_v1`, deriving PSI CrUX field device context only from retained
  raw field-metric `formFactor` metadata and never from Lighthouse lab strategy;
- **`nextgen_field_metric_distribution_v1` + integrity**, normalizing direct-CrUX histograms
  and PSI CrUX distributions into one field-only `{min,max,proportion}` shape only after the
  corresponding bound source contract succeeds; raw source identity/coverage, p75, units,
  ordering and distribution mass are rechecked and PSI Lighthouse values are never accepted;
- strict direct-Lighthouse requested/final identity, runtime-error and failed-audit provenance;
- lab-only Lighthouse metric-unit and opportunity normalization/integrity;
- deterministic representative template/high-value sampling, final-URL deduplication and a
  hard 12-candidate ceiling plus deterministic population binding;
- **`nextgen_performance_sample_origin_binding_v1` + integrity**, proving selected final page
  identities remain on one caller-supplied authoritative HTTP(S) origin before later
  browser/provider work may trust the sample; foreign origins, scheme/port changes,
  credential-bearing identities and malformed rows fail closed;
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
   deterministic selection is trusted.
3. Bind that already-validated sample to the integrator's authoritative site identity with
   `bind_representative_sample_to_site_origin(sample, site_url=authoritative_site_url)`, then
   require `validate_representative_sample_origin_contract(...)`. A valid origin binding proves
   identity only; it is **not** an execution entitlement.
4. Feed only an integrator-budget-approved subset into the existing safe browser/render path,
   preserving existing DNS/SSRF/redirect/body/deadline/cancellation controls.
5. For parity evidence, use `compare_critical_content_parity_resolved(...)`, validate it,
   assess sufficiency, validate sufficiency, and aggregate completed/failed/unassessed coverage
   separately.
6. For direct CrUX, use `normalize_crux_query_record_evidence_bound(...)` then
   `validate_bound_crux_contract(...)`; optional device context comes only after that via
   `normalize_crux_field_dimension_context(...)` + its integrity validator. Optional field
   histograms may then be derived with
   `normalize_crux_field_distribution_evidence(raw_crux_payload, bound_crux)` and must pass
   `validate_field_distribution_contract(...)` before trust.
7. For PSI, use `normalize_pagespeed_insights_evidence_bound(...)` then
   `validate_bound_pagespeed_contract(...)`.
8. After a bound PSI contract succeeds, optional PSI **field** device context comes from
   `normalize_psi_field_dimension_context(raw_psi_payload, bound_psi)` plus
   `validate_psi_field_dimension_contract(...)`. Optional PSI CrUX distributions may be derived
   with `normalize_psi_field_distribution_evidence(raw_psi_payload, bound_psi)` plus
   `validate_field_distribution_contract(...)`. Neither path may use Lighthouse lab strategy or
   measurements to fill field evidence.
9. For direct Lighthouse, use `normalize_lighthouse_evidence_bound(...)` plus its integrity
   validator; metric-unit and opportunity artifacts remain lab-only.
10. Bind sampled observation sources before trusting aggregate performance coverage.
11. Keep field and lab envelopes, distributions and device contexts separate through any future
    persistence/authority/customer logic. Repair priority/customer scoring remain integrator-owned.

A 500/1,000-page adaptive crawl must never imply 500/1,000 browser or Lighthouse executions.

## Verification evidence

Prior Lane-C checkpoints recorded **221 focused tests across 19 test files**.

The new field-distribution slice adds **18 deterministic regressions** covering direct-CrUX and
PSI distribution normalization, PSI CLS scaling, explicit field/lab separation, invalid bound
source contracts, rate-limited behavior, raw/trusted percentile disagreement, malformed bin
geometry/mass, all-unavailable distributions, PSI origin fallback, raw/source identity mismatch,
integrity tampering, credential-bearing identities, cross-provider contract laundering and input
immutability.

Focused hermetic contract-boundary result: **18/18 passed**. The new implementation and
repository-shaped test file also passed `py_compile`. Lane C therefore records **239 focused
tests across 20 test files**.

**239/239 exact-repository execution is not claimed.** This environment did not materialize the
complete branch for a repository-shaped full-suite run, and this integration-target draft does
not receive the normal main-target PR CI workflow.

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
  tests/test_nextgen_browser_performance_field_distributions.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_sample_origin.py \
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
  app/nextgen_browser_performance_field_distributions.py \
  app/nextgen_browser_performance_coverage.py \
  app/nextgen_browser_performance_sample_binding.py \
  app/nextgen_browser_performance_sample_origin.py \
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
  tests/test_nextgen_browser_performance_field_distributions.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_sample_origin.py \
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

The main evidence risk remains treating unavailable, mismatched, partial, unit-ambiguous or
failed provider/render observations as measured defects. Field and lab evidence must remain
separate.

Derived field distributions add a second trust requirement beyond provider shape: the raw
histogram/distribution must still bind to the already-validated provider identity and trusted p75.
A distribution from a different URL/origin, collection period, or PSI request must fail closed
even if the numeric bins look plausible.

The representative sampler has two distinct trust gates now: deterministic population binding
and site-origin binding. Neither gate authorizes execution. Foreign final redirects must remain
foreign evidence and must not silently become representative target-site browser candidates.

PSI field device context and field distributions are connected only from retained CrUX field
material. Lighthouse lab strategy and measurements never fill those field contexts.

## Rollback

Because the lane remains unwired from shared orchestration, rollback is deletion of Lane-C
helper/test/docs/fixture files. No data migration, authority rewrite, customer projection
rewrite, historical reconstruction change, worker configuration change, or deployment action
is required.
