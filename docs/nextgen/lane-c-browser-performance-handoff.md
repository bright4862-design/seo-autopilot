# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest lane code/test checkpoint before this handoff refresh: `5302e6991e7d85337dc7ad3c59f9f58036097c41`

## Ownership boundary

Lane C remains limited to pure provider/browser evidence helpers, representative-page
selection, integrity/binding helpers, deterministic tests, fixtures and documentation.
It does **not** modify `scanner.py` / `run_scan`, global scan budgets, worker deployment
configuration, repair priority/customer scoring, authority/persistence/projection,
admission, release/deployment, schema/IAM/credentials, provider accounts, or production.

No helper in this lane performs a live CrUX/PSI/Lighthouse/browser call or creates
credentials. New behavior is unwired and shadow/off until the serialized integrator
explicitly adopts it.

## Implemented contracts

Lane C currently provides:

- provider-neutral field-performance evidence with explicit `connected`, `disconnected`,
  `unavailable`, `rate_limited`, and `provider_error` states;
- direct CrUX and PageSpeed Insights normalization with CrUX field evidence and Lighthouse
  lab evidence kept in separate envelopes;
- documented CrUX `queryRecord` shape handling, URL/origin scope and coverage-period
  provenance;
- `nextgen_crux_bound_provider_v1` / `nextgen_crux_provenance_v1`, which fail closed unless
  a connected direct-CrUX observation has exactly one documented record identity, a true
  origin for origin-scoped records, and a valid provider collection period; embedded URL
  credentials, page-shaped origins, ambiguous raw keys, caller/record scope conflicts and
  source conflicts do not become connected field measurements;
- `nextgen_crux_bound_integrity_v1`, which re-validates source/scope/coverage provenance
  before connected direct-CrUX evidence is trusted;
- strict PageSpeed URL-vs-origin field fallback behavior;
- source-bound PSI provenance preserving requested/final identity, runtime-error behavior,
  origin fallback, analysis/fetch timestamps, Lighthouse version and strategy;
- bounded Lighthouse normalization for an allowlisted metric/opportunity set;
- `nextgen_lighthouse_bound_provider_v1` for direct Lighthouse observations, requiring
  provider-requested identity, preserving legitimate final-URL redirects, converting
  Lighthouse `runtimeError` into lab-only `provider_error`, excluding explicitly errored
  audits before normalization, and preserving fetch/version/strategy provenance;
- `nextgen_lighthouse_bound_integrity_v1`, which validates the additive direct-Lighthouse
  provenance and source relationship before connected lab evidence is trusted;
- deterministic representative template/high-value sampling, final-URL deduplication and a
  hard 12-candidate ceiling;
- `nextgen_performance_sample_binding_v1`, which recomputes the deterministic sample from
  the authoritative candidate population and fails closed on stale/forged/reordered
  selections, population drift, invalid requested limits, or non-absolute HTTP(S)
  selected identities;
- `nextgen_performance_evidence_coverage_v1`, which binds already-observed provider
  evidence back to the selected request population and reports field and lab
  attempted/connected/unassessed coverage independently;
- `nextgen_performance_observation_source_binding_v1`, which proves that connected
  CrUX/Lighthouse component sources belong to the sampled request, its origin, or an
  explicitly provenance-backed redirect final identity before connected coverage is trusted;
- raw-vs-rendered critical-content parity evidence for title/H1/canonical/indexability/
  main-content presence/important links/schema/product+entity facts;
- `nextgen_critical_content_parity_v2_resolved`, which resolves relative/protocol-relative
  canonicals against the document identity before delegating all other parity semantics to
  the existing comparator;
- `nextgen_critical_content_parity_v2_resolved_integrity_v1`, which re-validates the v2
  wrapper through the existing parity integrity contract;
- `nextgen_browser_parity_coverage_v2_contract_bound`, which refuses to count completed
  browser coverage until the representative sample and every resolved parity row pass
  their versioned contracts;
- raw/render identity, usability and extractor-presence fail-closed semantics;
- aggregate parity coverage that distinguishes completed, failed/unverifiable and unassessed
  selected URLs;
- fail-closed integrity validation for Lane-C field, lab, composite, sample and parity
  dictionaries.

## Serialized integration hook

The integrator, not this lane, owns execution and shared orchestration.

1. After accepted retained-page/template evidence exists, call
   `select_representative_performance_pages(...)` only to produce bounded candidates.
2. Before trusting that sample, call
   `validate_representative_sample_binding(authoritative_pages, sample)`. A valid binding
   proves deterministic selection only; it is **not** permission to execute all candidates.
3. Feed only an integrator-budget-approved subset into the existing safe browser/render
   path, preserving current DNS/SSRF/redirect/body/deadline/cancellation controls.
4. For new parity evidence, prefer `compare_critical_content_parity_resolved(...)`,
   validate each result with `validate_resolved_critical_parity_contract(...)`, then call
   `summarize_resolved_critical_parity_coverage(...)`.
5. For direct CrUX `queryRecord` payloads, prefer
   `normalize_crux_query_record_evidence_bound(...)`, then require
   `validate_bound_crux_contract(...).valid` before trusting connected field evidence.
   The earlier provider adapter remains the compatibility normalization layer underneath.
6. For PSI payloads, prefer `normalize_pagespeed_insights_evidence_bound(...)`.
7. For direct Lighthouse lab payloads outside PSI, prefer
   `normalize_lighthouse_evidence_bound(...)`, then require
   `validate_bound_lighthouse_contract(...).valid` before trusting connected lab evidence.
8. Assemble already-observed provider results under the sampled request identity. Before
   trusting connected coverage, call
   `validate_performance_observation_source_binding(sample, observations)`.
9. Only after source binding succeeds, call
   `summarize_performance_evidence_coverage(...)`.
10. Keep field and lab envelopes separate through any future persistence/authority/customer
    logic. Repair priority/customer scoring remain integrator-owned.

A 500/1,000-page adaptive crawl must never imply 500/1,000 browser or Lighthouse
executions.

## Verification evidence

Recorded Lane-C checkpoints:

- original focused repository checkpoint: 17 tests passed; corresponding compile passed;
- provider-shape hermetic slice: 8/8 passed;
- PSI provenance hermetic slice: 10/10 passed;
- parity-coverage hermetic slice: 9/9 passed;
- representative-sample binding hermetic slice: 9/9 passed;
- field/lab performance-coverage hermetic slice: 9/9 passed;
- performance observation source-binding hermetic slice: 10/10 passed;
- resolved-canonical/contract-bound parity hermetic slice: 10/10 passed;
- direct Lighthouse provenance/integrity hermetic slice: 10/10 passed;
- direct CrUX source/coverage provenance/integrity hermetic slice: **10/10 passed in 0.05s**
  against the current weaker base adapter semantics; new source/test `py_compile` passed.

Lane C now contains **122 focused tests across eleven test files**. **122/122 exact-repository
execution is not claimed.**

Required exact-head gate:

```bash
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance_source_binding.py \
  tests/test_nextgen_browser_performance_parity_hardening.py \
  tests/test_nextgen_browser_performance_lighthouse_provenance.py \
  tests/test_nextgen_browser_performance_crux_provenance.py

python -m py_compile \
  app/nextgen_browser_performance.py \
  app/nextgen_browser_performance_contract.py \
  app/nextgen_browser_performance_provider.py \
  app/nextgen_browser_performance_psi_provenance.py \
  app/nextgen_browser_performance_coverage.py \
  app/nextgen_browser_performance_sample_binding.py \
  app/nextgen_browser_performance_evidence_coverage.py \
  app/nextgen_browser_performance_source_binding.py \
  app/nextgen_browser_performance_parity_hardening.py \
  app/nextgen_browser_performance_lighthouse_provenance.py \
  app/nextgen_browser_performance_crux_provenance.py \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance_source_binding.py \
  tests/test_nextgen_browser_performance_parity_hardening.py \
  tests/test_nextgen_browser_performance_lighthouse_provenance.py \
  tests/test_nextgen_browser_performance_crux_provenance.py
```

The available local execution path still cannot materialize the complete branch from
GitHub, and this integration-target draft has no normal PR-triggered repository CI run.
Until an approved repository runner executes the commands above, exact-head repository
green remains a blocker for integration readiness.

## Current risks

The main evidence risk remains treating unavailable/mismatched/partial provider or render
observations as measured defects. Contracts therefore preserve unavailable/not-verified
states and keep field vs lab evidence separate.

Direct CrUX had an additional source-laundering risk: a superficially usable record could
carry ambiguous raw key material, a page-shaped `origin`, or missing/invalid collection
coverage while still looking connected. The bound CrUX adapter now rejects those cases
before measurements can be trusted, and the integrity contract rechecks transport-level
scope/source/coverage consistency.

Direct Lighthouse evidence has a parallel risk: a runtime-failed report or an audit
explicitly marked as errored could still contain numeric remnants. The bound direct-
Lighthouse adapter removes that ambiguity: runtime failure is `provider_error`; errored
audits are excluded; caller/requested/final identity is explicit.

The sample ceiling is still only a candidate bound. It is not an execution budget or
entitlement.

## Rollback

Because this lane remains unwired from shared orchestration, rollback is deletion of the
Lane-C helper/test/docs/fixture files. No data migration, authority rewrite, customer
projection rewrite, or historical reconstruction change is required.
