# Lane E — current fix population completeness binding

This Lane-E-only slice closes a verified-fixed proof gap in the legacy comparator replay path without changing the comparator itself.

## Problem

The existing strict replay correctly re-runs the historical `compare_repair_runs` comparator over the supplied `current_fixes` and current page evidence. However, a bare `current_fixes=[]` (or a truncated list) does not itself prove that the caller supplied the complete current-scan repair population. Treating an unproven empty population as authoritative could let absence of the repair row participate in a false `verified_fixed` decision.

This is distinct from regression reopening. Reopening is proven by positive re-observed defect evidence and does not depend on absence from `current_fixes`.

## New contracts

- `fix_verification_current_fix_population_v1_exact_complete_scan_population`
  - producer attestation over exactly five fields: version, scan id, completeness boolean, exact count, and population fingerprint;
  - `population_complete` must be exact `True`;
  - zero fixes is valid only when that empty population is explicitly attested complete.
- `fix_verification_current_fix_population_binding_v1_exact_complete_scan_population`
  - verifies exact scan identity, exact count, exact attestation fields, lowercase SHA-256 transport, and a fingerprint over the exact current-fix list transport;
  - rejects values that JSON would silently coerce (for example tuples) and non-finite floats.
- `fix_verified_fixed_current_fix_population_bound_replay_v1_exact_complete_scan_population`
  - new strict verified-fixed wrapper that requires the population-completeness binding before delegating to the existing evaluation-receipt-bound replay.

The population fingerprint is intentionally order-sensitive because it receipts the exact list handed to the legacy comparator. If a producer rewrites/reorders that list, it must publish a new attestation.

## Safety semantics

This change does **not** modify `compare_repair_runs`, `repair_verification_v3_contract_comparable`, durable authority, persistence, customer projection, `run_scan`, budgets, admission, release/deploy, or production behavior.

A disappeared URL is still never proof of a fix. Even with an exact complete empty current-fix population, a missing targeted page continues through the existing evaluator as `required_page_not_observed` => `COULD_NOT_VERIFY`.

An incomplete, missing, stale, malformed, foreign-scan, or mismatched current-fix population attestation also fails closed to `COULD_NOT_VERIFY` on the verified-fixed path.

Regression reopening deliberately keeps using the evaluation-receipt-bound path. No current-fix-population attestation is required there because positive defect re-observation, not current-fix absence, proves the reopen condition.

## Serialized integration handoff

The integrator should obtain the current fix population only from the authoritative current scan repair-generation output. At the point where that producer can truthfully assert the population is complete, it should create and retain an attestation with:

```text
version = fix_verification_current_fix_population_v1_exact_complete_scan_population
scan_id = authoritative current ScanRun id
population_complete = true
population_count = exact len(current_fixes)
population_fingerprint = current_fix_population_fingerprint(current_fixes, scan_id=scan_id)
```

Then call `strict_verified_fixed_transition_from_complete_current_fix_population(...)` as the strictest Lane-E verified-fixed pure entrypoint. Do not synthesize `population_complete=true` from an empty list alone, and do not infer completeness from report absence, UI projection, pagination exhaustion that is not authoritative, or a disappeared URL.

For regression reopening, continue using `strict_regression_reopen_from_evaluation_receipt_bound_inputs(...)`.

## Focused regressions

`scanner-api/tests/test_nextgen_fix_verification_current_fix_population.py` adds 13 deterministic tests covering:

- deterministic exact population fingerprinting;
- fingerprint change on population mutation;
- rejection of silent tuple coercion;
- complete empty-population proof;
- incomplete empty-population rejection;
- count mismatch;
- foreign scan id;
- malformed SHA-256 transport;
- stale attestation after mutation;
- unexpected attestation fields;
- verified-fixed PASS with a proven-complete empty current fix population;
- verified-fixed denial when emptiness is not proven complete;
- disappeared required page remaining `COULD_NOT_VERIFY` even when current-fix population completeness is proven.

Local publication-time checks for this slice:

- helper source `py_compile`: passed;
- focused test source `py_compile`: passed;
- hermetic pure-binding/delegation harness: 10/10 passed.

The full repository-native Lane-E gate still must run from a real checkout before integration acceptance.
