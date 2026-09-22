# Agent C — representative-sample binding hardening

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`

## Purpose

Lane C already emits deterministic representative performance samples, but a structurally plausible sample can still be transported alongside the wrong retained-page population. That is unsafe because a later browser/Lighthouse stage could otherwise trust a forged or stale selection while its counts still look reasonable.

This checkpoint adds a pure, fail-closed binding layer without changing `run_scan`, global budgets, worker configuration, repair/customer scoring, authority/persistence/projection, admission, release/deployment, or production.

## New pure binding helper

`scanner-api/app/nextgen_browser_performance_sample_binding.py` adds `nextgen_performance_sample_binding_v1` and `validate_representative_sample_binding(...)`.

The helper:

- requires the published sample to use the current `nextgen_performance_sample_v1` contract;
- rejects boolean/negative/non-integer requested limits rather than coercing them;
- recomputes `select_representative_performance_pages(...)` from the caller-supplied authoritative candidate population;
- binds all deterministic sample fields, including requested/bounded limits, eligibility/deduplication counts, template-family coverage, selected rows, order, selection reasons and high-value weights;
- therefore rejects plausible-count forgeries, stale samples, reordered selections and candidate-population drift;
- requires every recomputed selected execution identity to be an absolute HTTP(S) URL, so a relative/non-HTTP selector result cannot become trusted browser execution evidence;
- returns the expected selected URL list for audit/debugging, but does not authorize execution of those pages;
- performs no network/provider/browser calls and mutates neither pages nor sample evidence.

The serialized integrator must supply the authoritative retained-page/template population. Binding against an arbitrary subset only proves the sample against that subset; this helper does not decide authority.

## Deterministic regressions

`scanner-api/tests/test_nextgen_browser_performance_sample_binding.py` adds 9 pure regressions covering:

1. an exact deterministic sample binding successfully;
2. a forged lower-value selected URL with plausible counts failing closed;
3. reordered selected rows failing closed;
4. authoritative candidate-population drift failing closed;
5. final-URL deduplication preserving the deterministic winning observation;
6. an oversized request remaining hard-capped at 12 candidates;
7. relative selected identities failing closed before execution trust;
8. boolean requested limits being rejected rather than coerced;
9. input pages/sample evidence remaining immutable.

A hermetic harness containing the exact current representative selector logic plus the new helper/tests passed:

```text
9 passed in 0.07s
python -m py_compile app/nextgen_browser_performance_sample_binding.py tests/test_nextgen_browser_performance_sample_binding.py
```

This is execution evidence for the new pure binding slice only. It is not a claim that the complete repository branch is green.

Lane C now contains 73 focused tests across six test files.

## Exact repository gate still required

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

The current execution container still cannot resolve `github.com`, so the full branch cannot be materialized there. This integration-target draft also has no normal PR-triggered repository CI run. Exact-head 73/73 therefore remains uncertified until an approved repository runner executes the commands above.

## Integrator hook

After calling `select_representative_performance_pages(...)`, the serialized integrator should call `validate_representative_sample_binding(authoritative_pages, sample)` before treating the sample as execution evidence. Only a `valid=true` binding may feed an integrator-budget-approved subset into the existing safe browser/render path.

A valid binding is still not permission to execute all selected pages. Global browser/Lighthouse budgets, deadlines, cancellation and safe-request controls remain serialized-integrator-owned.

## Rollback

Rollback is deletion of the new helper/test/doc. No data migration, persistence rewrite or historical reconstruction change is required because this lane remains unwired from shared orchestration.
