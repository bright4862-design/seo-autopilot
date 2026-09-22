# Lane C — field scope coverage hardening

This slice adds a pure, provider-neutral scope-aware coverage layer for already-bound CrUX/PSI field evidence.

## Problem closed

A sampled page can legitimately receive connected field evidence that is **origin-scoped** rather than URL-scoped. The existing provider-binding layer proves that the evidence came from a valid bound CrUX/PSI envelope for the sampled request, but aggregate coverage must not turn one origin-level observation into several page-level field measurements just because several selected pages share that origin.

Likewise, URL-scoped PSI evidence may describe a provider subject reached after a redirect. That is connected field context, but it is not exact page-level evidence for the original sampled request unless the normalized source identity still matches the requested page.

## Contract

`scanner-api/app/nextgen_browser_performance_field_scope_coverage.py` adds:

- `nextgen_field_scope_coverage_v1`;
- `nextgen_field_scope_coverage_integrity_v1`;
- `summarize_field_scope_coverage(sample, observations)`;
- `validate_field_scope_coverage_contract(sample, observations, evidence)`.

The summary requires the representative-sample contract and the existing provider-envelope observation-binding validator first. It then keeps these cases distinct:

- exact URL-scoped connected evidence → page-level connected coverage;
- redirected URL-scoped connected evidence → connected context only, not exact page coverage;
- origin-scoped connected evidence → origin-level context only, deduplicated by origin;
- explicit non-connected provider states → attempted but unmeasured;
- missing field component → unassessed.

`page_level_connected_ratio` therefore counts only exact URL-scoped connected evidence. `connected_observation_ratio` remains separately available so downstream consumers cannot accidentally substitute one meaning for the other.

Lab/Lighthouse evidence is ignored by this field-only aggregate. No field result can be synthesized from lab strategy or lab measurements.

## Fail-closed behavior

The helper returns `not_verified` when the sample contract or provider binding is invalid, when connected field source identity is malformed, when connected scope is unsupported, or when an origin-scoped source does not match the sampled request origin.

The integrity validator recomputes the entire artifact from the sample and observations. A transported ratio, count, URL list, origin group, or fail-closed reason cannot be changed without invalidating the contract.

## Deterministic verification

`scanner-api/tests/test_nextgen_browser_performance_field_scope_coverage.py` adds 15 focused regressions covering:

- exact URL scope;
- origin-scope de-inflation and origin deduplication;
- redirected URL-scoped evidence;
- non-connected provider states;
- lab-only observations remaining field-unassessed;
- mixed exact/origin/non-connected/unassessed ratios;
- multiple origins;
- default-port identity normalization;
- observation-order determinism;
- empty samples;
- invalid sample/provider binding fail-closed behavior;
- integrity tamper detection;
- truthful fail-closed integrity;
- input immutability.

A hermetic contract-boundary harness for the new helper/test semantics passed 15/15, and the new implementation and test file passed `py_compile`. This is not a claim that the complete repository suite or exact PR head CI is green.

## Integrator hook

After `validate_performance_observation_provider_binding(sample, observations)` succeeds, derive and validate this scope-aware field coverage **before** any future consumer interprets field coverage as page-level coverage:

1. `summarize_field_scope_coverage(sample, observations)`
2. `validate_field_scope_coverage_contract(sample, observations, scope_coverage)`
3. keep exact URL page coverage, redirected URL context, and origin context separate in any later persistence/customer logic.

This contract is descriptive only. It does not grant provider/browser/Lighthouse execution budget, does not score customers or repairs, and does not modify `run_scan`, authority, persistence, projection, admission, release, deployment, credentials, provider accounts, or production.
