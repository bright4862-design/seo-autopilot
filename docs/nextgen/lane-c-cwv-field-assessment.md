# Lane C — field-only Core Web Vitals assessment

This checkpoint adds a pure, provider-neutral Core Web Vitals assessment over the existing Lane-C **field** evidence contract.

## Why this slice exists

Lane C already keeps CrUX field measurements and Lighthouse lab measurements in separate envelopes. A later integrator still needs a safe way to answer the narrower question: does trusted field evidence establish that all three Core Web Vitals are good?

The new helper intentionally does **not** use Lighthouse metrics for that decision. It accepts only a valid `nextgen_field_performance_v1` dictionary and rejects a lab envelope through the existing field-contract validator.

## Contract

`assess_core_web_vitals_field_evidence(...)` emits `nextgen_cwv_field_assessment_v1` with explicit coverage:

- required metrics: LCP, INP, CLS;
- observed and missing required metrics;
- per-metric numeric classification using bounded good / needs-improvement / poor thresholds;
- provider-rating disagreement is retained and causes `not_verified` rather than allowing contradictory evidence to claim pass/fail;
- `passed` only when all three required field metrics are present and good;
- `failed` when any observed required field metric is known not-good, even if another required metric is missing, because the all-good condition is already disproven;
- `not_verified` when the source field contract is invalid, the provider is non-connected, coverage is incomplete with no known failing metric, or provider category metadata contradicts the normalized numeric value.

The helper performs no provider call, browser execution, persistence, scoring, customer Fix creation, or shared orchestration.

## Deterministic verification

The new focused test file contains 10 regressions covering:

1. all-good pass at inclusive good thresholds;
2. needs-improvement transition just above good thresholds;
3. poor transition above poor thresholds;
4. known non-good metric with incomplete coverage;
5. incomplete all-good evidence remaining `not_verified`;
6. non-connected field state remaining `not_verified`;
7. Lighthouse lab evidence being rejected as field evidence;
8. malformed field units failing closed;
9. provider rating disagreement failing closed instead of claiming a CWV pass;
10. input immutability.

A hermetic contract-boundary execution passed **10/10** and the new source/test passed `py_compile`. Exact repository-head execution remains part of the lane-wide gate.

## Integration handoff

After direct CrUX or PSI field evidence has passed its existing Lane-C source/integrity validation, the serialized integrator may optionally call `assess_core_web_vitals_field_evidence(field)` to derive a field-only CWV assessment. Do not feed the PSI/Lighthouse lab envelope into this helper and do not use this helper to grant provider/browser execution.

This remains evidence-only. Repair priority, customer scoring, authority/persistence/projection, `run_scan`, budgets, worker config, admission, release, deployment, and production remain integrator-owned and unchanged.
