# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Implementation checkpoint before this handoff: `a95c3b26b9fc6907184885f5b4ab85db29c5b0aa`

## What this lane adds

Pure, network-free browser/performance evidence helpers live in `scanner-api/app/nextgen_browser_performance.py`.

The contract provides:

- provider-neutral field-performance evidence with explicit `connected`, `disconnected`, `unavailable`, `rate_limited`, and `provider_error` states;
- a CrUX normalizer and a PageSpeed Insights normalizer that keep CrUX field evidence and Lighthouse lab evidence in separate envelopes;
- bounded Lighthouse normalization for performance score, selected measurements, and an allowlisted opportunity set;
- deterministic representative-page selection across template families with high-value weighting and a hard ceiling of 12 candidates;
- raw-vs-rendered critical-content parity evidence for title, H1, canonical, indexability, main-content presence, important links, structured-data types, and product/entity facts;
- fail-closed render behavior: a failed/missing render is `not_verified`, never a confirmed site defect.

No function in the module performs provider or browser network I/O.

## Future serialized integration hook

The integrator, not this lane, owns shared orchestration.

1. After accepted retained-page evidence and template-family classification are available, call `select_representative_performance_pages(...)` to produce candidate URLs. Do not replace Standard 150 selection and do not expand the assessed-page denominator.
2. Feed only an integrator-approved subset of those candidates into the existing safe browser/render execution path. Prefer adapting the existing bounded render-followup seam rather than creating a second renderer or request budget.
3. For every successful paired raw/rendered observation, call `compare_critical_content_parity(...)`. Failed, skipped, deadline-exhausted, or challenged renders must be represented as `not_verified`.
4. An authenticated provider layer may pass already-observed CrUX/PSI payloads into `normalize_crux_evidence(...)` or `normalize_pagespeed_insights_evidence(...)`. This lane does not create credentials, OAuth scopes, or provider calls.
5. Keep field and lab envelopes distinct through authority/persistence and any later repair logic. Customer scoring/repair priority remains integrator-owned.

## Resource-budget expectations

- Candidate selection has a hard pure-code ceiling of 12 pages even if a caller asks for hundreds.
- The hard ceiling is not permission to execute 12 browser/Lighthouse runs. Initial shadow integration should use a smaller global-budget-approved subset, typically 4–8 representative pages, and must obey the existing deadline, safe-request, cancellation, and renderer controls.
- A 500- or 1,000-page adaptive crawl must not imply 500/1,000 Lighthouse executions.
- Provider evidence may be absent, rate-limited, or unavailable without failing the scan.

## Verification

Focused deterministic tests:

`PYTHONPATH=. pytest -q tests/test_nextgen_browser_performance.py`

Result at the implementation checkpoint: **11 passed**.

Syntax verification:

`python -m py_compile app/nextgen_browser_performance.py tests/test_nextgen_browser_performance.py`

Result: passed.

The tests use only a checked-in PSI/Lighthouse fixture; they make no live provider calls and require no credentials.

## Files owned/changed by the implementation checkpoint

- `scanner-api/app/nextgen_browser_performance.py`
- `scanner-api/tests/test_nextgen_browser_performance.py`
- `scanner-api/tests/fixtures/nextgen_psi_sample.json`
- existing lane bootstrap doc: `docs/nextgen/lane-c-browser-performance.md`

This handoff document is additive. No `run_scan`, global scan-budget, worker deployment, repair priority/customer scoring, authority/persistence/projection, admission, release, deployment, or production surface is modified.

## Risks and rollback

The main semantic risk is treating a browser/provider absence as a defect. The contracts intentionally fail closed and separate unknown/unavailable states from measured deltas.

The main resource risk is allowing representative selection to become an execution entitlement. The selector's 12-page cap is only an upper bound; the serialized integrator must impose the actual browser/Lighthouse budget.

Rollback is deletion of the lane-owned helper, focused test, fixture, and this handoff. Because the implementation is not wired into shared orchestration, rollback does not require data migration or historical reconstruction changes.
