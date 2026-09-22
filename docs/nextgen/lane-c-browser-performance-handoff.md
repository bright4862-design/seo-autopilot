# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest code/test checkpoint before this handoff refresh: `d6ea7998f370a6f191bcb346472edda70e1abfad`

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
- strict direct-CrUX URL/origin source identity, collection-period provenance,
  field device context, and field metric distributions;
- source-bound PSI requested/final/component provenance plus bound integrity;
- PSI field device context and field distributions derived only from retained CrUX material,
  never from Lighthouse lab strategy or measurements;
- strict direct-Lighthouse requested/final identity, runtime-error and failed-audit provenance;
- lab-only Lighthouse metric-unit and opportunity normalization/integrity;
- `nextgen_lighthouse_lab_context_v1` + integrity for provider-neutral lab execution context;
- deterministic representative template/high-value sampling, final-URL deduplication,
  hard 12-candidate ceiling, deterministic population binding, authoritative-site-origin
  binding, and bound representativeness coverage;
- field/lab performance observation coverage and request/source binding;
- `nextgen_performance_observation_provider_binding_v1`, proving transported field/lab
  components came from already-valid bound CrUX/PSI/Lighthouse provider envelopes for the
  same sampled request before aggregate coverage may trust them;
- raw-vs-rendered critical-content parity for title/H1/canonical/indexability/main content,
  important links, structured data and product/entity facts;
- resolved-canonical parity, contract-bound parity coverage, critical-parity sufficiency,
  and source binding back to the exact retained raw/rendered observations/render outcome;
- field-only Core Web Vitals assessment requiring trusted LCP/INP/CLS field evidence.

## Serialized integration hook

The serialized integrator, not this lane, owns execution and shared orchestration.

1. After accepted retained-page/template evidence exists, call
   `select_representative_performance_pages(...)` only to produce bounded candidates.
2. Require `validate_representative_sample_binding(authoritative_pages, sample)` before the
   deterministic selection is trusted.
3. Derive `build_representative_sample_coverage(authoritative_pages, sample)` and require
   `validate_representative_sample_coverage_contract(...)` when downstream code needs to know
   how much template/positive sampler-weight population the bounded sample represents. This is
   descriptive evidence only; it is not customer scoring and grants no execution budget.
4. Bind the sample to the authoritative site identity with
   `bind_representative_sample_to_site_origin(...)`, then require
   `validate_representative_sample_origin_contract(...)`. This gate also proves identity only.
5. Feed only an integrator-budget-approved subset into the existing safe browser/render path,
   preserving existing DNS/SSRF/redirect/body/deadline/cancellation controls.
6. For parity evidence, build resolved parity with `compare_critical_content_parity_resolved(...)`,
   validate the resolved contract, require
   `validate_resolved_critical_parity_source_binding(...)` against the exact retained raw and
   rendered observations plus render outcome, then assess/validate sufficiency and aggregate
   completed/failed/unassessed coverage separately.
7. For direct CrUX, require the bound CrUX provenance/integrity contract first. Derive optional
   field device context and field distributions only after that gate succeeds.
8. For PSI, require `normalize_pagespeed_insights_evidence_bound(...)` plus
   `validate_bound_pagespeed_contract(...)` first. Derive PSI field device context/distributions
   only from the CrUX field component.
9. For direct Lighthouse, require `normalize_lighthouse_evidence_bound(...)` plus
   `validate_bound_lighthouse_contract(...)` before any derived lab artifact.
10. After the corresponding bound validator succeeds, derive lab execution context with either
    `normalize_direct_lighthouse_lab_context(raw_lighthouse, bound_lighthouse)` or
    `normalize_psi_lighthouse_lab_context(raw_psi, bound_psi)`, then require
    `validate_lighthouse_lab_context_contract(...)`.
11. Before trusting transported sampled observations, require
    `validate_performance_observation_source_binding(sample, observations)` and then
    `validate_performance_observation_provider_binding(sample, observations)`. The first proves
    sampled-request/source relationships; the second proves each field/lab component exactly
    matches an already-valid bound CrUX/PSI/Lighthouse provider envelope for that request.
12. Only after those binding gates succeed should
    `summarize_performance_evidence_coverage(sample, observations)` be trusted. Missing components
    stay unassessed; explicit non-connected states remain attempted-but-unmeasured.
13. Keep field and lab envelopes, distributions, device contexts, lab execution contexts and
    coverage separate through any future persistence/authority/customer logic. Repair priority/
    customer scoring remain integrator-owned.

A 500/1,000-page adaptive crawl must never imply 500/1,000 browser or Lighthouse executions.

## Latest provider-binding slice

`scanner-api/app/nextgen_browser_performance_observation_provider_binding.py` adds
`nextgen_performance_observation_provider_binding_v1`. It closes a transport gap between the
existing sampled request/source-binding layer and the provider-specific bound contracts. A base
field or lab dictionary can no longer be accepted merely because it is structurally valid and
points at a sampled URL: it must exactly match the corresponding base component contained in an
already-valid bound CrUX, PSI or Lighthouse envelope for that sampled request.

The helper preserves the evidence boundary deliberately: direct CrUX can satisfy field evidence
only, direct Lighthouse can satisfy lab evidence only, and PSI can carry both while the field and
lab component comparisons remain independent. Foreign/malformed requested identities,
credential-bearing selected identities, invalid provider-bound contracts, duplicate provider
kinds, cross-kind laundering, component tampering, duplicate observations and unused misleading
provider bindings fail closed. An empty observation set remains valid without claiming coverage;
coverage accounting is responsible for marking sampled pages unassessed.

`scanner-api/tests/test_nextgen_browser_performance_observation_provider_binding.py` adds **19
deterministic regressions** covering direct CrUX + Lighthouse binding, PSI dual-component
binding, origin-scoped CrUX, empty observations, credential-bearing identities, unknown/duplicate
provider kinds, invalid bound contracts, requested-identity mismatches, foreign CrUX evidence,
field/lab tampering, field↔lab laundering prevention, unused provider bindings, duplicate
observations, truthful rate-limited PSI state, and input immutability.

Isolated contract-boundary verification for this slice: **19/19 passed**; the new source and test
file also passed `py_compile`. This is not a claim that the complete repository suite or exact PR
head CI is green.

Prior Lane-C checkpoints recorded **283 focused tests across 23 test files**. Lane C therefore
records **302 focused tests across 24 test files**.

## Required exact-head gate

The exact branch should be verified in a full checkout with:

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
  tests/test_nextgen_browser_performance_sample_coverage.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance_source_binding.py \
  tests/test_nextgen_browser_performance_observation_provider_binding.py \
  tests/test_nextgen_browser_performance_parity_hardening.py \
  tests/test_nextgen_browser_performance_parity_source_binding.py \
  tests/test_nextgen_browser_performance_lighthouse_provenance.py \
  tests/test_nextgen_browser_performance_crux_provenance.py \
  tests/test_nextgen_browser_performance_crux_dimensions.py \
  tests/test_nextgen_browser_performance_cwv.py \
  tests/test_nextgen_browser_performance_lighthouse_units.py \
  tests/test_nextgen_browser_performance_parity_sufficiency.py \
  tests/test_nextgen_browser_performance_lighthouse_opportunities.py \
  tests/test_nextgen_browser_performance_lab_context.py

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
  app/nextgen_browser_performance_sample_coverage.py \
  app/nextgen_browser_performance_evidence_coverage.py \
  app/nextgen_browser_performance_source_binding.py \
  app/nextgen_browser_performance_observation_provider_binding.py \
  app/nextgen_browser_performance_parity_hardening.py \
  app/nextgen_browser_performance_parity_source_binding.py \
  app/nextgen_browser_performance_lighthouse_provenance.py \
  app/nextgen_browser_performance_crux_provenance.py \
  app/nextgen_browser_performance_crux_dimensions.py \
  app/nextgen_browser_performance_cwv.py \
  app/nextgen_browser_performance_lighthouse_units.py \
  app/nextgen_browser_performance_parity_sufficiency.py \
  app/nextgen_browser_performance_lighthouse_opportunities.py \
  app/nextgen_browser_performance_lab_context.py \
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
  tests/test_nextgen_browser_performance_sample_coverage.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance_source_binding.py \
  tests/test_nextgen_browser_performance_observation_provider_binding.py \
  tests/test_nextgen_browser_performance_parity_hardening.py \
  tests/test_nextgen_browser_performance_parity_source_binding.py \
  tests/test_nextgen_browser_performance_lighthouse_provenance.py \
  tests/test_nextgen_browser_performance_crux_provenance.py \
  tests/test_nextgen_browser_performance_crux_dimensions.py \
  tests/test_nextgen_browser_performance_cwv.py \
  tests/test_nextgen_browser_performance_lighthouse_units.py \
  tests/test_nextgen_browser_performance_parity_sufficiency.py \
  tests/test_nextgen_browser_performance_lighthouse_opportunities.py \
  tests/test_nextgen_browser_performance_lab_context.py
```

**302/302 exact-repository execution is not claimed.** The execution environment cannot
materialize the full branch from GitHub, and this integration-target draft does not receive the
normal main-target PR CI workflow.

## Current risks

The main evidence risk remains treating unavailable, mismatched, partial, unit-ambiguous or
failed provider/render observations as measured defects. Field and lab evidence must remain
separate.

Representative sample coverage is descriptive, not execution authorization. A high template
coverage ratio or high selected sampler-weight ratio must never expand the integrator-owned
browser/Lighthouse budget. The sample still requires both deterministic population binding and
site-origin binding before later execution can trust candidate identities.

Sample/request source binding is necessary but not sufficient for provider evidence. A
structurally valid field/lab component can still be forged or detached from the bound provider
envelope that produced it. Require the provider-binding validator before aggregate coverage.

Resolved parity must remain bound to the exact retained raw/rendered observations and render
outcome. A structurally valid transported parity envelope is insufficient on its own.

## Rollback

Because the lane remains unwired from shared orchestration, rollback is deletion of Lane-C
helper/test/docs/fixture files. No data migration, authority rewrite, customer projection
rewrite, historical reconstruction change, worker configuration change, or deployment action
is required.
