# Agent C — Browser / Performance integration handoff

Issue: #324  
Draft PR: #331  
Lane branch: `agent/nextgen-browser-performance-20260921`  
Latest code/test checkpoint: `13ab76bc97939f30b767f91e2e28a621e552b0f3`

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
- parity identity/useability guards: missing raw identity, missing rendered identity, mismatched normalized identity, raw fetch/status/evidence-class failure, and render fetch/status/evidence-class failure all return `not_verified` and cannot become a content delta;
- scalar field-presence provenance (`raw_observed` / `rendered_observed`) so a missing extractor key is `not_verified`, while an explicitly observed empty value remains comparable to a non-empty observation;
- normalized important-link comparison so relative-vs-absolute forms and URL fragments do not create false render deltas;
- deterministic `verified_fields` / `changed_fields` summaries for downstream evidence consumers without creating customer Fixes or scores.

No function in the module performs provider or browser network I/O.

## Future serialized integration hook

The integrator, not this lane, owns shared orchestration.

1. After accepted retained-page evidence and template-family classification are available, call `select_representative_performance_pages(...)` to produce candidate URLs. Do not replace Standard 150 selection and do not expand the assessed-page denominator.
2. Feed only an integrator-approved subset of those candidates into the existing safe browser/render execution path. Prefer adapting the existing bounded render-followup seam rather than creating a second renderer or request budget.
3. Call `compare_critical_content_parity(...)` only with raw/rendered observations that preserve final identity and extraction presence. The helper itself fails closed for missing/mismatched identity and explicitly unusable observations. Failed, skipped, deadline-exhausted, challenged, partial-identity, or unusable observations must remain `not_verified`.
4. An authenticated provider layer may pass already-observed CrUX/PSI payloads into `normalize_crux_evidence(...)` or `normalize_pagespeed_insights_evidence(...)`. This lane does not create credentials, OAuth scopes, or provider calls.
5. Keep field and lab envelopes distinct through authority/persistence and any later repair logic. Customer scoring/repair priority remains integrator-owned.

## Resource-budget expectations

- Candidate selection has a hard pure-code ceiling of 12 pages even if a caller asks for hundreds.
- The hard ceiling is not permission to execute 12 browser/Lighthouse runs. Initial shadow integration should use a smaller global-budget-approved subset, typically 4–8 representative pages, and must obey the existing deadline, safe-request, cancellation, and renderer controls.
- A 500- or 1,000-page adaptive crawl must not imply 500/1,000 Lighthouse executions.
- Duplicate crawl observations resolving to the same normalized final URL count as one performance candidate.
- Provider evidence may be absent, rate-limited, invalid, or unavailable without failing the scan.

## Verification

Previous focused deterministic checkpoint `3e8dddccf22cf2fe2a3786e6c74160f4ac2b5a8e` was executed before this hardening:

`PYTHONPATH=. pytest -q tests/test_nextgen_browser_performance.py` → **17 passed**  
`python -m py_compile app/nextgen_browser_performance.py tests/test_nextgen_browser_performance.py` → **passed**

Exact code/test checkpoint `13ab76bc97939f30b767f91e2e28a621e552b0f3` adds six regressions, so the focused test file now contains **23 tests**. The new regressions cover:

- missing raw identity;
- missing rendered identity;
- explicitly unusable raw evidence;
- an absent scalar extractor key on the raw side remaining `not_verified`;
- an absent scalar extractor key on the rendered side remaining `not_verified`;
- an explicitly observed empty scalar remaining comparable when both extractors observed the field.

**Exact-head execution is not yet certified.** The available automation Python/container runners returned infrastructure `ClientError`; the remote sandbox required interactive authorization; this integration-target PR has no GitHub Actions run because repository CI triggers only for `main` pushes / `main`-targeted PRs; and CodeRabbit reports that its review sandbox prohibits running repository tests/builds. Do not infer a 23/23 result from the prior 17/17 checkpoint.

CodeRabbit independently reviewed exact code/test checkpoint `13ab76bc97939f30b767f91e2e28a621e552b0f3` and reported **no material issues**. It explicitly confirmed that the prior P1 identity/useability and P2 one-sided-scalar findings are addressed. This is static review evidence, not execution evidence.

The tests use only the checked-in PSI/Lighthouse fixture; they contain no live provider calls and require no credentials.

## Files owned/changed

- `scanner-api/app/nextgen_browser_performance.py`
- `scanner-api/tests/test_nextgen_browser_performance.py`
- `scanner-api/tests/fixtures/nextgen_psi_sample.json`
- `docs/nextgen/lane-c-browser-performance.md`
- `docs/nextgen/lane-c-browser-performance-handoff.md`

No `scanner.py` / `run_scan`, global scan-budget, worker deployment, repair priority/customer scoring, authority/persistence/projection, admission, release, deployment, or production surface is modified.

## Risks and rollback

The main semantic risk is treating browser/provider absence, partial extraction, or a wrong paired render as a defect. The contracts intentionally fail closed, distinguish provider absence from measured performance, reject missing/mismatched render identity, reject explicitly unusable observations, and keep missing extractor fields out of confirmed deltas.

The main resource risk is allowing representative selection to become an execution entitlement. The selector's 12-page cap is only an upper bound; the serialized integrator must impose the actual browser/Lighthouse budget.

The sampler normalizes to final URL for execution identity. Integrator wiring should preserve the original crawl URL separately if customer-facing provenance needs both redirect entry and final target; this lane does not alter persistence/projection.

Rollback is deletion of the lane-owned helper, focused test, fixture, and handoff/bootstrap docs. Because the implementation is not wired into shared orchestration, rollback does not require data migration or historical reconstruction changes.
