# Agent E — verified-fixed transition integrity

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint is additive and remains inside the Agent E ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Why this checkpoint exists

Lane E already has a conjunctive compatibility helper requiring a NextGen PASS plus the existing `compare_repair_runs(...) = verified_fixed` outcome. The result-integrity checkpoint also protects regression reopening from hand-constructed FAIL/PARTIAL objects.

There was still a transport-boundary gap for the positive transition: a caller could hand-construct a `fix_verification_result_v1` object that merely says `PASS`, pair it with a hand-constructed legacy object whose state merely says `verified_fixed`, and satisfy the earlier boolean conjunction without independently validating either proof envelope or proving that both envelopes cover the same repair population.

This checkpoint does **not** change the historical comparator or durable authority. It adds a stricter pure consumer-side decision for the serialized integrator.

## New contract

Implementation: `scanner-api/app/nextgen_fix_verified_fixed_transition.py`

Version:
- `fix_verified_fixed_transition_v2_integrity`

`strict_verified_fixed_transition_decision(previous_record, current_result, legacy_comparison)` allows a future durable transition only when all of the following are true:

1. `verification_result_integrity(...)` accepts the current NextGen result;
2. the effective NextGen state is exactly `PASS`;
3. the result fingerprint matches the stable historical repair fingerprint;
4. the legacy comparison uses the existing `repair_verification_v3_contract_comparable` version;
5. the legacy state is exactly `verified_fixed`;
6. legacy population counts are strict non-boolean integers and the full previous population was rechecked and eligible;
7. the legacy comparison contract state is `compatible` or `legacy_compatible`;
8. the NextGen required population count exactly equals the legacy historical affected-page count.

Any malformed, incomplete, mismatched, ambiguous, or foreign-version input fails closed with `allowed = false` and a machine-readable reason.

The helper is pure data. It does not modify `compare_repair_runs(...)`, `verified_fixed_transition_allowed(...)`, persistence, authority, customer projection, workflow state, `run_scan`, admission, release, deployment, or production.

## Added deterministic regressions

`scanner-api/tests/test_nextgen_fix_verified_fixed_transition.py` adds 9 cases:

1. complete NextGen PASS + complete legacy `verified_fixed` proof allows the transition;
2. malformed/incomplete PASS is rejected;
3. PARTIAL is rejected even when legacy says `verified_fixed`;
4. unsupported legacy verification version is rejected;
5. legacy non-`verified_fixed` state is rejected;
6. changed repair fingerprint is rejected;
7. cross-contract evidence-population mismatch is rejected;
8. boolean/malformed legacy population counts are rejected;
9. an incomparable legacy comparison contract is rejected.

Together with the 27 Lane-E cases already present, the branch now contains 36 focused Lane-E test cases.

## Verification status

A hermetic pure-function harness mirroring the new helper and these nine tests executed successfully in the available local runner:

```text
9 passed
python -m py_compile: passed
```

That harness validates this new pure transition logic, but it is **not** being represented as an exact repository-suite run.

The exact branch-wide Lane-E suite still cannot be certified in this automation environment because:

- the local runtime has no DNS/network access to clone the public GitHub repository;
- the remote YepCode runner requires interactive authorization, which is unavailable in this non-interactive run;
- PR #330 targets the NextGen integration branch and currently has no GitHub Actions workflow run that can substitute for exact-head execution.

The next approved runner must execute:

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

No 36/36 exact-head claim should be made until that command succeeds.

## Serialized integration handoff

After Agents A–D have been integrated and the full relevant suites remain green, the serialized integrator should:

1. obtain the historical comparator result only from the existing `compare_repair_runs(...)` path;
2. obtain the NextGen result only from `evaluate_verification_plan(...)`;
3. pass the historical repair record, NextGen result, and legacy comparison into `strict_verified_fixed_transition_decision(...)`;
4. require `allowed == true` before even proposing a durable verified-fixed transition;
5. keep the actual durable workflow/persistence mutation inside the existing signed authority path outside this lane;
6. continue using `strict_regression_reopen_decision(...)` for later regression reopening.

This new helper is additive defense-in-depth and must not be used to bypass or replace the historical comparator.

## Safety boundary

This checkpoint adds only a pure Lane-E helper, its focused tests, and this handoff document. It does not modify durable authority/persistence/customer projection, `run_scan`, global budgets, repair priority, Base44 schema, admission, release, deployment, worker configuration, IAM, credentials, or production.