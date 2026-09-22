# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest implementation/test checkpoint before this handoff refresh: `9d0043ec8a448154e2908984fcc4de91fc647ade`

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
- raw-vs-rendered critical-content parity evidence for title/H1/canonical/indexability/main-content presence/important links/schema/product+entity facts;
- raw/render identity, usability and extractor-presence fail-closed semantics;
- aggregate parity coverage that distinguishes completed, failed/unverifiable and unassessed selected URLs;
- fail-closed integrity validation for Lane-C field, lab, composite, sample and parity dictionaries.

## Serialized integration hook

The integrator, not this lane, owns execution and shared orchestration.

1. After accepted retained-page/template evidence exists, call `select_representative_performance_pages(...)` only to produce bounded candidates. This does not change Standard 150 selection or the assessed-page denominator.
2. Before trusting that sample, call `validate_representative_sample_binding(authoritative_pages, sample)`. The caller must provide the authoritative retained-page/template population. A valid binding proves deterministic selection only; it is **not** permission to execute all selected pages.
3. Feed only an integrator-budget-approved subset into the existing safe browser/render path, preserving existing DNS/SSRF/redirect/body/deadline/cancellation controls. Do not create a second renderer or hidden fetch budget.
4. Build raw/rendered parity only from successful same-identity observations. Failed, skipped, challenged, deadline-exhausted, partial-identity or unusable observations remain `not_verified`.
5. After per-page parity construction, call `summarize_critical_parity_coverage(...)` over the original selected sample plus available parity rows so execution failures remain failed and candidates never executed remain unassessed.
6. For direct CrUX `queryRecord` payloads, prefer `normalize_crux_query_record_evidence(...)`. For PSI payloads, prefer `normalize_pagespeed_insights_evidence_bound(...)` so requested/final identity, runtime error, origin fallback and provider provenance remain explicit.
7. Keep field and lab envelopes separate through any future persistence/authority/customer logic. Repair priority/customer scoring remain integrator-owned.

A 500/1,000-page adaptive crawl must never imply 500/1,000 browser or Lighthouse executions.

## Verification evidence

Executed checkpoints currently recorded for Lane C:

- original focused repository checkpoint: `tests/test_nextgen_browser_performance.py` → **17 passed**; corresponding `py_compile` passed;
- provider-shape hermetic checkpoint → **8/8 passed**; compile passed;
- PSI provenance hermetic checkpoint → **10/10 passed**; compile passed;
- parity-coverage hermetic checkpoint → **9/9 passed**; compile passed;
- latest representative-sample binding checkpoint → **9/9 passed in 0.07s** in a hermetic package containing the exact current selector logic plus the new helper/tests; compile passed.

Lane C now contains **73 focused tests across six test files**. **73/73 exact-repository execution is not claimed.**

Required exact-head gate:

```bash
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py
python -m py_compile \
  app/nextgen_browser_performance.py \
  app/nextgen_browser_performance_contract.py \
  app/nextgen_browser_performance_provider.py \
  app/nextgen_browser_performance_psi_provenance.py \
  app/nextgen_browser_performance_coverage.py \
  app/nextgen_browser_performance_sample_binding.py \
  tests/test_nextgen_browser_performance.py \
  tests/test_nextgen_browser_performance_contract.py \
  tests/test_nextgen_browser_performance_provider.py \
  tests/test_nextgen_browser_performance_psi_provenance.py \
  tests/test_nextgen_browser_performance_coverage.py \
  tests/test_nextgen_browser_performance_sample_binding.py
```

The current execution container still cannot resolve `github.com`, so it cannot materialize the complete branch. This integration-target draft also has no normal PR-triggered repository CI run. Until an approved repository runner executes the commands above, exact-head repository green remains a blocker for integration readiness.

## Risks

The main evidence risk is treating unavailable/mismatched/partial provider or render observations as measured defects. Contracts therefore preserve truthful unavailable/not-verified states and keep field vs lab evidence separate.

The main selection risk is trusting a stale or forged representative sample against the wrong page population. The sample-binding helper closes that gap only when the serialized integrator supplies the authoritative candidate population.

The main resource risk is treating the 12-candidate selector ceiling as an execution entitlement. It is only a pure-code candidate bound; the integrator must impose the actual browser/Lighthouse budget.

## Rollback

Because this lane remains unwired from shared orchestration, rollback is deletion of the Lane-C helper/test/docs/fixture files. No data migration, authority rewrite or historical reconstruction change is required.
