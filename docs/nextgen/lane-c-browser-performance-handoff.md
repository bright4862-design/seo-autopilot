# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest code/test checkpoint before this handoff refresh: `07758e044af24ca015751fd516feae5576a4f950`

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
- **`nextgen_lighthouse_lab_context_v1` + integrity**, normalizing already-bound direct
  Lighthouse and PSI-Lighthouse execution context into one lab-only provider-neutral shape:
  `device_class`, `throttling_mode`, `locale`, `observation_time`, `engine_version`, and
  `environment_benchmark_index`. Missing context remains explicit in `missing_fields`; it is
  never guessed from field evidence;
- deterministic representative template/high-value sampling, final-URL deduplication,
  hard 12-candidate ceiling, deterministic population binding, and authoritative-site-origin
  binding before later execution may trust a sample;
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
3. Bind that sample to the authoritative site identity with
   `bind_representative_sample_to_site_origin(...)`, then require
   `validate_representative_sample_origin_contract(...)`. These gates prove identity only;
   they do **not** grant browser or provider execution budget.
4. Feed only an integrator-budget-approved subset into the existing safe browser/render path,
   preserving existing DNS/SSRF/redirect/body/deadline/cancellation controls.
5. For parity evidence, use `compare_critical_content_parity_resolved(...)`, validate it,
   assess/validate sufficiency, and aggregate completed/failed/unassessed coverage separately.
6. For direct CrUX, require the bound CrUX provenance/integrity contract first. Derive optional
   field device context and field distributions only after that gate succeeds.
7. For PSI, require `normalize_pagespeed_insights_evidence_bound(...)` plus
   `validate_bound_pagespeed_contract(...)` first. Derive PSI field device context/distributions
   only from the CrUX field component.
8. For direct Lighthouse, require `normalize_lighthouse_evidence_bound(...)` plus
   `validate_bound_lighthouse_contract(...)` before any derived lab artifact.
9. After the corresponding bound validator succeeds, derive lab execution context with either
   `normalize_direct_lighthouse_lab_context(raw_lighthouse, bound_lighthouse)` or
   `normalize_psi_lighthouse_lab_context(raw_psi, bound_psi)`, then require
   `validate_lighthouse_lab_context_contract(...)`. This derived artifact is lab-only and must
   never be used to fill CrUX field device context.
10. Bind sampled observation sources before trusting aggregate performance coverage.
11. Keep field and lab envelopes, distributions, device contexts, and lab execution contexts
    separate through any future persistence/authority/customer logic. Repair priority/customer
    scoring remain integrator-owned.

A 500/1,000-page adaptive crawl must never imply 500/1,000 browser or Lighthouse executions.

## Latest lab-context slice

`scanner-api/app/nextgen_browser_performance_lab_context.py` adds a provider-neutral lab-only
execution-context artifact for already-bound direct Lighthouse and PSI Lighthouse evidence.
It rechecks requested/final/source identity plus bound fetch-time, engine-version, and device
strategy provenance before retaining context. Credential-bearing or malformed identities fail
closed. Unknown throttling/locale/benchmark context remains missing rather than inferred.
Field evidence cannot be laundered into this contract.

`scanner-api/tests/test_nextgen_browser_performance_lab_context.py` adds **16 deterministic
regressions** covering direct and PSI normalization, same-contract output, partial context,
unknown throttling, requested/final/fetch/version/device mismatches, credential-bearing URLs,
non-connected provider state, field-to-lab laundering, PSI lab-component enforcement,
integrity tampering, and input immutability.

Focused repository-shaped hermetic result for this slice: **16/16 passed**. The new source and
test file also passed `py_compile`.

Prior Lane-C checkpoints recorded **239 focused tests across 20 test files**. Lane C therefore
records **255 focused tests across 21 test files**.

**255/255 exact-repository execution is not claimed.** The execution environment cannot
materialize the full branch from GitHub, and this integration-target draft does not receive the
normal main-target PR CI workflow.

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
  tests/test_nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance_source_binding.py \
  tests/test_nextgen_browser_performance_parity_hardening.py \
  tests/test_nextgen_browser_performance_lighthouse_provenance.py \
  tests/test_nextgen_browser_performance_crux_provenance.py \
  tests/test_nextgen_browser_performance_crux_dimensions.py \
  tests/test_nextgen_browser_performance_cwv.py \
  tests/test_nextgen_browser_performance_lighthouse_units.py \
  tests/test_nextgen_browser_performance_parity_sufficiency.py \
  tests/test_nextgen_browser_performance_lighthouse_opportunities.py \
  tests/test_nextgen_browser_performance_lab_context.py
```

## Current risks

The main evidence risk remains treating unavailable, mismatched, partial, unit-ambiguous or
failed provider/render observations as measured defects. Field and lab evidence must remain
separate.

The new lab context is descriptive provenance, not a performance result and not an execution
entitlement. The integrator must validate the existing bound Lighthouse/PSI contract first;
then the derived context validator. Missing lab context remains unknown and must not be filled
from CrUX form factor or other field metadata.

The representative sampler has separate deterministic population and site-origin trust gates.
Neither gate authorizes execution. Foreign final redirects must remain foreign evidence and must
not silently become representative target-site browser candidates.

## Rollback

Because the lane remains unwired from shared orchestration, rollback is deletion of Lane-C
helper/test/docs/fixture files. No data migration, authority rewrite, customer projection
rewrite, historical reconstruction change, worker configuration change, or deployment action
is required.
