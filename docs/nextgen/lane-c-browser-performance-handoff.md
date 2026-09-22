# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest lane code/test checkpoint before this handoff refresh: `c65d60772ef55fc74c7b3ba2e7c425e89ec05586`

## Ownership boundary

This lane is limited to pure provider/browser evidence helpers, representative-page selection, integrity/binding helpers, deterministic tests, fixtures and documentation. It does **not** modify `scanner.py` / `run_scan`, global scan budgets, worker deployment configuration, repair priority/customer scoring, authority/persistence/projection, admission, release/deployment, schema/IAM/credentials, or production.

No helper in this lane performs a live CrUX/PSI/browser call or creates credentials. New behavior is unwired and shadow/off until the serialized integrator explicitly adopts it.

## Implemented contracts

Lane C currently provides:

- provider-neutral field-performance evidence with explicit `connected`, `disconnected`, `unavailable`, `rate_limited`, and `provider_error` states;
- direct CrUX and PageSpeed Insights normalization with CrUX field evidence and Lighthouse lab evidence kept in separate envelopes;
- documented CrUX `queryRecord` shape handling, URL/origin scope and coverage-period provenance;
- strict PageSpeed URL-vs-origin field fallback behavior;
- source-bound PSI provenance preserving requested/final identity, runtime-error behavior, origin fallback, analysis/fetch timestamps, Lighthouse version and strategy;
- bounded Lighthouse normalization for an allowlisted metric/opportunity set;
- deterministic representative template/high-value sampling, final-URL deduplication and a hard 12-candidate ceiling;
- `nextgen_performance_sample_binding_v1`, which recomputes the deterministic sample from the authoritative candidate population and fails closed on stale/forged/reordered selections, population drift, invalid requested limits, or non-absolute HTTP(S) selected identities;
- `nextgen_performance_evidence_coverage_v1`, which binds already-observed provider evidence back to the selected request population and reports field and lab attempted/connected/unassessed coverage independently;
- `nextgen_performance_observation_source_binding_v1`, which proves that connected CrUX/Lighthouse component sources belong to the sampled request, its origin, or an explicitly provenance-backed redirect final identity before connected coverage is trusted;
- raw-vs-rendered critical-content parity evidence for title/H1/canonical/indexability/main-content presence/important links/schema/product+entity facts;
- `nextgen_critical_content_parity_v2_resolved`, which resolves relative/protocol-relative canonicals against the document identity before delegating all other parity semantics to the existing comparator;
- `nextgen_critical_content_parity_v2_resolved_integrity_v1`, which re-validates the resolved envelope through the existing parity integrity contract;
- `nextgen_browser_parity_coverage_v2_contract_bound`, which refuses to count completed browser coverage until the representative sample and every resolved parity row pass their versioned contracts;
- raw/render identity, usability and extractor-presence fail-closed semantics;
- aggregate parity coverage that distinguishes completed, failed/unverifiable and unassessed selected URLs;
- fail-closed integrity validation for Lane-C field, lab, composite, sample and parity dictionaries.

## Serialized integration hook

The integrator, not this lane, owns execution and shared orchestration.

1. After accepted retained-page/template evidence exists, call `select_representative_performance_pages(...)` only to produce bounded candidates. This does not change Standard 150 selection or the assessed-page denominator.
2. Before trusting that sample, call `validate_representative_sample_binding(authoritative_pages, sample)`. The caller must provide the authoritative retained-page/template population. A valid binding proves deterministic selection only; it is **not** permission to execute all selected pages.
3. Feed only an integrator-budget-approved subset into the existing safe browser/render path, preserving existing DNS/SSRF/redirect/body/deadline/cancellation controls. Do not create a second renderer or hidden fetch budget.
4. For new NextGen parity evidence, call `compare_critical_content_parity_resolved(...)` only after successful already-observed raw/rendered evidence exists. Failed, skipped, challenged, deadline-exhausted, partial-identity or unusable observations remain `not_verified`.
5. Validate each resolved parity result with `validate_resolved_critical_parity_contract(...)`, then call `summarize_resolved_critical_parity_coverage(...)` over the original representative sample so forged/malformed rows cannot count as completed coverage and never-executed candidates remain unassessed. Existing v1 parity helpers remain compatibility-only.
6. For direct CrUX `queryRecord` payloads, prefer `normalize_crux_query_record_evidence(...)`. For PSI payloads, prefer `normalize_pagespeed_insights_evidence_bound(...)` so requested/final identity, runtime error, origin fallback and provider provenance remain explicit.
7. Assemble each already-observed provider result under the sampled request identity. Before trusting connected coverage, call `validate_performance_observation_source_binding(sample, observations)`. Connected component sources that differ from the sampled request must have explicit matching redirect provenance; origin-scoped field evidence must be a true origin identity.
8. Only after source binding succeeds, call `summarize_performance_evidence_coverage(...)`. Missing field/lab components remain unassessed, while explicit unavailable/rate-limited/provider-error states count as attempts but never as connected measurements.
9. Keep field and lab envelopes separate through any future persistence/authority/customer logic. Repair priority/customer scoring remain integrator-owned.

A 500/1,000-page adaptive crawl must never imply 500/1,000 browser or Lighthouse executions.

## Verification evidence

Executed checkpoints currently recorded for Lane C:

- original focused repository checkpoint: `tests/test_nextgen_browser_performance.py` → **17 passed**; corresponding `py_compile` passed;
- provider-shape hermetic checkpoint → **8/8 passed**; compile passed;
- PSI provenance hermetic checkpoint → **10/10 passed**; compile passed;
- parity-coverage hermetic checkpoint → **9/9 passed**; compile passed;
- representative-sample binding checkpoint → **9/9 passed in 0.07s** in a hermetic package containing the exact current selector logic plus the new helper/tests; compile passed;
- field/lab performance-coverage checkpoint → **9/9 passed in 0.04s** in a hermetic helper/contract-boundary harness; compile passed;
- performance observation source-binding checkpoint → **10/10 passed in 0.07s** in a hermetic package exercising the exact new helper/test logic against contract-shaped field/lab/sample fixtures; `py_compile` passed;
- resolved-canonical/contract-bound parity checkpoint → **10/10 passed in 0.07s** in a hermetic package exercising the exact new helper/test logic against contract-shaped parity/sample fixtures; new source/test `py_compile` passed.

Lane C now contains **102 focused tests across nine test files**. **102/102 exact-repository execution is not claimed.**

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
  tests/test_nextgen_browser_performance_parity_hardening.py
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
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance_evidence_coverage.py \
  tests/test_nextgen_browser_performance_source_binding.py \
  tests/test_nextgen_browser_performance_parity_hardening.py
```

The available execution container still cannot materialize the complete branch from GitHub, and this integration-target draft has no normal PR-triggered repository CI run. Until an approved repository runner executes the commands above, exact-head repository green remains a blocker for integration readiness.

## Risks

The main evidence risk is treating unavailable/mismatched/partial provider or render observations as measured defects. Contracts therefore preserve truthful unavailable/not-verified states and keep field vs lab evidence separate.

A second evidence risk is **source laundering**: placing a structurally valid connected component under a selected page's top-level request identity even though the component itself belongs to another page or origin. `nextgen_performance_observation_source_binding_v1` closes that gap for connected evidence and allows redirects only with explicit matching PSI provenance.

A third parity risk is false canonical drift caused only by representation differences such as relative vs absolute hrefs. `nextgen_critical_content_parity_v2_resolved` resolves those hrefs against each document identity before comparison, while preserving genuinely different resolved targets as `material_delta`.

A fourth parity risk is coverage inflation from a structurally forged completed result. `nextgen_browser_parity_coverage_v2_contract_bound` requires the full sample and per-result contracts before counting completion.

The main selection risk is trusting a stale or forged representative sample against the wrong page population. The sample-binding helper closes that gap only when the serialized integrator supplies the authoritative candidate population.

The main resource risk is treating the 12-candidate selector ceiling as an execution entitlement. It is only a pure-code candidate bound; the integrator must impose the actual browser/Lighthouse budget.

## Rollback

Because this lane remains unwired from shared orchestration, rollback is deletion of the Lane-C helper/test/docs/fixture files. No data migration, authority rewrite or historical reconstruction change is required.
