# Lane C — critical parity sufficiency hardening

Issue: #324  
Draft PR: #331  
Lane: `agent/nextgen-browser-performance-20260921`

## Problem closed

The existing resolved raw-vs-rendered parity contract correctly fails closed on
invalid identity, unusable observations, missing extractors, and malformed result
dictionaries. One remaining interpretation risk was more subtle: a contract-valid
`matched` row could be produced when only one critical field was bilaterally
observed. That is useful partial evidence, but it is not sufficient evidence that
raw and rendered **critical content broadly match**.

The inverse is different. If one contract-valid observed critical field changed,
that positive delta is already evidence of a render-dependent difference even when
other fields remain unobserved.

## Additive contract

`scanner-api/app/nextgen_browser_performance_parity_sufficiency.py` adds:

- `nextgen_critical_parity_sufficiency_v1`;
- `nextgen_critical_parity_sufficiency_integrity_v1`;
- baseline match fields: title, H1, canonical, indexability, main-content presence,
  and important links;
- `verified_match` only when every baseline field is bilaterally verified and the
  resolved parity source is a contract-valid match;
- `verified_delta` when a contract-valid resolved parity source contains any
  material changed field, even if unrelated fields remain unassessed;
- `not_verified` for partial matches, render/provider failures, or invalid source
  contracts;
- exact source-binding validation by recomputing the expected assessment rather
  than trusting a mutable derived state;
- truthful fail-closed assessments remain integrity-valid even when the rejected
  source version itself is malformed, while any derived-state tampering still fails.

Optional structured-data and business/entity fact fields remain useful parity
evidence but are not universal prerequisites for a verified match.

## Integrator hook

After `compare_critical_content_parity_resolved(...)` and
`validate_resolved_critical_parity_contract(...).valid`, the serialized integrator
may call `assess_critical_parity_sufficiency(...)` before interpreting a `matched`
row as sufficiently observed. It must then bind the derived result with
`validate_critical_parity_sufficiency(parity, assessment)`.

This helper does not run a browser, grant browser budget, persist evidence, score
repairs/customers, or alter authority/projection.

## Deterministic verification

The focused slice adds 11 regressions covering:

1. complete baseline match;
2. partial match fail-closed behavior;
3. partial but positive material delta;
4. render failure;
5. malformed source contract;
6. resolved relative canonical coverage;
7. exact assessment/source binding;
8. missing-field tampering;
9. delta-to-match laundering;
10. input immutability;
11. truthful fail-closed integrity for a source with an invalid parity version.

A hermetic contract-shaped execution of the new logic passed 11/11 and both new
files passed Python syntax compilation before publication. Exact full-repository
Lane-C execution remains a separate integration-readiness gate.

No live provider calls, credentials, `run_scan`, global budget, worker deployment,
repair/customer scoring, authority/persistence/projection, admission, release,
deployment, or production changes are part of this slice.
