# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest code/test checkpoint: `3e8dddccf22cf2fe2a3786e6c74160f4ac2b5a8e`

## What this lane adds

Pure, network-free browser/performance evidence helpers live in `scanner-api/app/nextgen_browser_performance.py`.

The contract provides:

- provider-neutral field-performance evidence with explicit `connected`, `disconnected`, `unavailable`, `rate_limited`, and `provider_error` states;
- CrUX and PageSpeed Insights normalizers that keep CrUX field evidence and Lighthouse lab evidence in separate envelopes;
- fail-closed provider semantics for invalid states and missing payloads, retaining truthful `provider_state_invalid` / `provider_payload_missing` reasons rather than silently reclassifying them;
- bounded Lighthouse normalization for performance score, selected measurements, and an allowlisted opportunity set, rejecting out-of-range scores and preferring explicit `overallSavingsMs` when present;
- deterministic representative-page selection across template families with high-value weighting and a hard ceiling of 12 candidates;
- deterministic final-URL deduplication for representative sampling, with duplicate-observation telemetry and final URL preferred over redirect-entry URL;
- raw-vs-rendered critical-content parity evidence for title/H1/canonical/indexability/main-content presence/important links/structured-data types/product+entity facts;
- parity identity guards so mismatched raw/rendered URLs and explicitly unusable render observations become `not_verified`, never content-delta claims;
- normalized important-link comparison so relative-vs-absolute forms and URL fragments do not create false render deltas;
- deterministic `verified_fields` / `changed_fields` summaries for downstream evidence consumers without creating customer Fixes or scores.

No function in the module performs provider or browser network I/O.

## Future serialized integration hook

The integrator, not this lane, owns shared orchestration.

1. After accepted retained-page evidence and template-family classification are available, call `select_representative_performance_pages(...)` to produce candidate URLs. Do not replace Standard 150 selection and do not expand the assessed-page denominator.
2. Feed only an integrator-approved subset of those candidates into the existing safe browser/render execution path. Prefer adapting the existing bounded render-followup seam rather than creating a second renderer or request budget.
3. For every successful paired raw/rendered observation, call `compare_critical_content_parity(...)`. The caller should pass the observed final/render URL when available. Failed, skipped, deadline-exhausted, challenged, identity-mismatched, or explicitly unusable render observations must remain `not_verified`.
4. An authenticated provider layer may pass already-observed CrUX/PSI payloads into `normalize_crux_evidence(...)` or `normalize_pagespeed_insights_evidence(...)`. This lane does not create credentials, OAuth scopes, or provider calls.
5. Keep field and lab envelopes distinct through authority/persistence and any later repair logic. Customer scoring/repair priority remains integrator-owned.

## Resource-budget expectations

- Candidate selection has a hard pure-code ceiling of 12 pages even if a caller asks for hundreds.
- The hard ceiling is not permission to execute 12 browser/Lighthouse runs. Initial shadow integration should use a smaller global-budget-approved subset, typically 4–8 representative pages, and must obey the existing deadline, safe-request, cancellation, and renderer controls.
- A 500- or 1,000-page adaptive crawl must not imply 500/1,000 Lighthouse executions.
- Duplicate crawl observations resolving to the same normalized final URL count as one performance candidate.
- Provider evidence may be absent, rate-limited, invalid, or unavailable without failing the scan.

## Verification

Focused deterministic tests executed against the exact module/test contents in code checkpoint `3e8dddccf22cf2fe2a3786e6c74160f4ac2b5a8e`:

`PYTHONPATH=. pytest -q tests/test_nextgen_browser_performance.py`

Result: **17 passed**.

Syntax verification:

`python -m py_compile app/nextgen_browser_performance.py tests/test_nextgen_browser_performance.py`

Result: **passed**.

The tests use only the checked-in PSI/Lighthouse fixture; they make no live provider calls and require no credentials.

New hardening regressions cover:

- missing/invalid provider payload semantics;
- invalid Lighthouse score rejection and explicit-savings precedence;
- input-order-independent final-URL deduplication in representative sampling;
- raw/rendered identity mismatch fail-closed behavior;
- explicit unusable-render fail-closed behavior;
- relative-vs-absolute important-link normalization;
- deterministic changed-field summaries.

## Files owned/changed

- `scanner-api/app/nextgen_browser_performance.py`
- `scanner-api/tests/test_nextgen_browser_performance.py`
- `scanner-api/tests/fixtures/nextgen_psi_sample.json`
- `docs/nextgen/lane-c-browser-performance.md`
- `docs/nextgen/lane-c-browser-performance-handoff.md`

No `scanner.py` / `run_scan`, global scan-budget, worker deployment, repair priority/customer scoring, authority/persistence/projection, admission, release, deployment, or production surface is modified.

## Risks and rollback

The main semantic risk is treating browser/provider absence or a wrong paired render as a defect. The contracts intentionally fail closed, distinguish provider absence from measured performance, and reject identity-mismatched render pairs.

The main resource risk is allowing representative selection to become an execution entitlement. The selector's 12-page cap is only an upper bound; the serialized integrator must impose the actual browser/Lighthouse budget.

The sampler now normalizes to final URL for execution identity. Integrator wiring should preserve the original crawl URL separately if customer-facing provenance needs both redirect entry and final target; this lane does not alter persistence/projection.

Rollback is deletion of the lane-owned helper, focused test, fixture, and handoff/bootstrap docs. Because the implementation is not wired into shared orchestration, rollback does not require data migration or historical reconstruction changes.