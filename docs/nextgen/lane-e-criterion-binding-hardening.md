# Agent E — historical criterion binding hardening

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint is additive and remains inside the Agent E ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

The previous integrity layer proved that transported PASS/PARTIAL/FAIL results were structurally complete, and the previous verified-fixed transition layer also required the existing `repair_verification_v3_contract_comparable` proof. A remaining transport-boundary gap was that a structurally valid result could still carry a foreign `criterion_id`, or a copied fingerprint could be paired with historical repair metadata whose stored identity/version claims no longer matched the repair identity regenerated from the historical record.

That is not enough for a durable transition or regression reopen. Ambiguous identity/version evidence must fail closed.

## New binding contract

`scanner-api/app/nextgen_fix_verification_integrity.py` now exposes:

- `fix_verification_result_binding_v1`
- `verification_result_historical_binding(previous_record, current_result)`

The binder treats both objects as untrusted pure data and requires:

1. the transported result passes `fix_verification_result_integrity_v1`;
2. `build_acceptance_criterion(previous_record)` regenerates a `ready` criterion;
3. the historical repair regenerates a stable repair identity under the current repair-identity contract;
4. any stored top-level `repair_fingerprint` / `repair_identity_version` agrees with that regenerated identity;
5. any nested `repair_identity` claim, when present, is an object and agrees on fingerprint/version/stable state;
6. the transported result fingerprint exactly matches the regenerated historical fingerprint;
7. the transported result `criterion_id` exactly matches the criterion regenerated from the historical rule/profile/URL-identity versions.

Any mismatch yields `valid = false` and an effective `COULD_NOT_VERIFY` state for the strict consumers.

## Regression reopening

`strict_regression_reopen_decision(...)` now reports contract version:

- `fix_regression_reopen_v3_criterion_bound`

A valid FAIL/PARTIAL can reopen only after historical binding succeeds. A foreign criterion id, historical rule-version drift, stale stored fingerprint, malformed nested identity claim, or changed repair identity cannot reopen a previously resolved repair.

The reopening helper remains pure data and does not mutate persistence, authority, customer projection, workflow state, or production.

## Verified-fixed transition

`strict_verified_fixed_transition_decision(...)` now reports:

- `fix_verified_fixed_transition_v3_criterion_bound`

It first requires the same historical binding, then requires the existing legacy comparator proof and exact population-size agreement. This preserves the existing verified-fixed comparability gate while preventing a well-shaped but foreign PASS from satisfying the positive transition boundary.

## Added deterministic regressions

The integrity suite now has 13 cases, adding coverage for:

- structurally valid FAIL with a foreign criterion id;
- conflict between stored historical fingerprint and regenerated identity;
- historical rule-definition version drift after a result was produced;
- malformed nested historical repair-identity transport.

The transition suite now has 13 cases, adding coverage for:

- complete PASS with a foreign criterion id;
- conflicting stored historical fingerprint;
- historical rule-version drift;
- nested repair-identity version mismatch.

Together with the existing 18 core verification tests, Lane E now contains 44 focused tests.

## Verification performed in this checkpoint

A hermetic pure-function harness using the exact new binder/strict-decision logic executed the 13 integrity scenarios and 13 transition scenarios successfully:

```text
13/13 integrity scenarios passed
13/13 transition scenarios passed
module/test source compilation passed
```

This validates the new pure logic but is not represented as an exact repository-suite run.

The exact branch-wide Lane-E gate remains:

```bash
cd scanner-api
PYTHONPATH=. python -m pytest -q \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py
python -m py_compile \
  app/nextgen_fix_verification.py \
  app/nextgen_fix_verification_integrity.py \
  app/nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py
```

No exact-head repository 44/44 claim should be made until that command succeeds in an approved checkout/runner.

## Serialized integration handoff

After Agents A-D are integrated and relevant regressions are green, the serialized integrator should:

1. obtain the NextGen result from `evaluate_verification_plan(...)`;
2. obtain the legacy comparison only from `compare_repair_runs(...)`;
3. use `strict_verified_fixed_transition_decision(...)` before proposing any durable verified-fixed transition;
4. use `strict_regression_reopen_decision(...)` for later regression reopening;
5. treat any failed historical binding as `COULD_NOT_VERIFY`, never as proof of a fix or a regression;
6. keep durable authority/persistence/customer projection wiring outside this lane.

## Safety boundary

This checkpoint changes only Lane-E pure helpers, focused tests, and this handoff document. It does not modify `run_scan`, global budgets, durable authority/persistence, customer projection, repair priority, Base44 schema, admission, release/deployment, worker configuration, IAM, credentials, or production.