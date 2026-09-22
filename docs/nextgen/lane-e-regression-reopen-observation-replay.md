# Lane E — observation-bound regression reopening

Branch: `agent/nextgen-fix-verification-20260921`

Scope: pure NextGen Fix Verification helper/test work only. This change does not mutate durable authority, persistence, customer projection, `run_scan`, global budgets, admission, release/deploy, worker configuration, or production behavior.

## Problem closed

`strict_regression_reopen_decision(...)` correctly validates a transported verification result against the historical repair identity, acceptance criterion, exact historical evidence population, and PASS/PARTIAL/FAIL structural invariants. That helper intentionally accepts a result object so its binding/state-machine behavior can be tested in isolation.

A serialized integration boundary must be stricter: a caller must not be able to fabricate a structurally valid FAIL or PARTIAL result with the right fingerprint/scope and use that transported object as proof that a previously verified repair regressed.

## New contract

`fix_regression_reopen_observation_replay_v1_recomputed_current_result`

`strict_regression_reopen_from_observations(...)` takes the historical repair, exact targeted plan, current page observations, current rule evaluations, current comparison contract, and authoritative historical/current scan-origin context.

It first recomputes the current verification result through `evaluate_verification_observations_strict(...)`, then passes only that newly recomputed result into the existing `strict_regression_reopen_decision(...)` historical binding/state-machine gate.

Consequences:

- FAIL/PARTIAL can reopen only when they are freshly derived from the supplied comparable observations.
- PASS leaves the repair verified and does not reopen it.
- a disappeared required URL produces `COULD_NOT_VERIFY`, never regression proof;
- duplicate/ambiguous rule evidence produces `COULD_NOT_VERIFY`;
- a truncated/tampered targeted plan cannot become regression proof;
- ambiguous scan-origin transport fails closed before recomputation;
- no network work or durable mutation occurs in this helper.

## Focused regressions

`scanner-api/tests/test_nextgen_fix_regression_reopen_replay.py` adds 7 cases:

1. recomputed FAIL reopens the full exact unresolved scope;
2. recomputed PARTIAL reopens only the exact unresolved member;
3. recomputed PASS does not reopen;
4. disappeared required URL => `COULD_NOT_VERIFY`, no reopen;
5. duplicate rule evidence => `COULD_NOT_VERIFY`, no reopen;
6. tampered plan population => `COULD_NOT_VERIFY`, no reopen;
7. whitespace-ambiguous historical scan origin is rejected before recomputation.

A hermetic wrapper harness exercised these seven branches successfully (`7/7`), and the new helper passes `py_compile`. This is not a claim that the exact branch-native pytest suite has run.

## Updated Lane-E focused gate

Expected focused total after this slice: **84 tests**.

```bash
cd scanner-api
PYTHONPATH=. python -m pytest -q \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py \
  tests/test_nextgen_fix_verification_observation_integrity.py \
  tests/test_nextgen_fix_regression_reopen_replay.py

python -m py_compile \
  app/nextgen_fix_verification.py \
  app/nextgen_fix_verification_integrity.py \
  app/nextgen_fix_verified_fixed_transition.py \
  app/nextgen_fix_verified_fixed_replay.py \
  app/nextgen_fix_verified_fixed_observation_replay.py \
  app/nextgen_fix_verification_observation_integrity.py \
  app/nextgen_fix_regression_reopen_replay.py \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py \
  tests/test_nextgen_fix_verification_observation_integrity.py \
  tests/test_nextgen_fix_regression_reopen_replay.py
```

## Serialized integration handoff

For any future durable regression-reopen decision, the integrator should prefer `strict_regression_reopen_from_observations(...)` over accepting a transported verification result as final proof. Supply `previous_scan_origin` only from authoritative historical scan/crawl-scope metadata and `scan_origin` only from authoritative current scan context. Persist/project a reopen only when `should_reopen is True` and all existing authority/persistence gates independently pass.

Do not wire this lane directly to durable workflow state in the lane branch.
