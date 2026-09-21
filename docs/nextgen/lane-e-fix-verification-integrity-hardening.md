# Agent E — Fix Verification result-integrity hardening

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint is additive and remains inside the Agent E ownership boundary from `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Why this checkpoint exists

The first Lane-E implementation correctly derives PASS / PARTIAL / FAIL / COULD_NOT_VERIFY from complete re-observation evidence and separately provides a pure regression-reopen helper. A serialized caller must still treat a persisted or caller-supplied verification-result object as untrusted data: a hand-constructed object that merely declares `FAIL` or `PARTIAL` must not be enough to reopen a previously verified repair.

This checkpoint adds a second fail-closed boundary around terminal-result consumption without changing authority, persistence, customer projection, `run_scan`, budgets, admission, release, deployment, or production.

## New contracts

Implementation: `scanner-api/app/nextgen_fix_verification_integrity.py`

Versions:
- `fix_verification_result_integrity_v1`
- `fix_regression_reopen_v2_integrity`

`verification_result_integrity(...)` validates terminal-result structure before PASS/PARTIAL/FAIL is allowed to count as proof. For a proving terminal state it requires:
- supported `fix_verification_result_v1` version;
- known terminal state;
- non-empty repair fingerprint and criterion identity;
- strict non-boolean integer population counts;
- positive required population;
- observed and evaluated counts equal to the full required population;
- list-shaped resolved/unresolved/unverifiable scopes;
- no duplicate or empty evidence identities;
- no unresolved/resolved overlap;
- no unverifiable evidence;
- exact scope cardinality equal to the required population;
- state-consistent scope semantics: PASS is all resolved, FAIL is all unresolved, PARTIAL contains both.

Any malformed proving result is effectively downgraded to `COULD_NOT_VERIFY` for regression purposes.

`strict_regression_reopen_decision(...)` then requires both a structurally proven current result and the same stable repair fingerprint before a previously PASS / `verified_fixed` / fixed / resolved repair may reopen. A malformed, incomplete, ambiguous, or hand-constructed FAIL/PARTIAL result cannot reopen anything. `COULD_NOT_VERIFY` remains explicitly non-proving.

The existing `regression_reopen_decision(...)` function remains untouched for compatibility with the earlier isolated lane checkpoint. The serialized integrator should use the strict v2 helper for any later authority/persistence wiring.

## Added focused regressions

`scanner-api/tests/test_nextgen_fix_verification_integrity.py` adds 9 deterministic cases:

1. complete FAIL is integrity-valid and reopens;
2. complete PARTIAL reopens only its exact unresolved scope;
3. incomplete/forged FAIL is downgraded to COULD_NOT_VERIFY and cannot reopen;
4. PARTIAL with overlapping resolved/unresolved scope cannot reopen;
5. FAIL carrying unverifiable evidence cannot reopen;
6. complete PASS remains closed, while malformed PASS downgrades fail-closed;
7. COULD_NOT_VERIFY is a valid non-proving terminal state and never reopens;
8. missing criterion/result identity fails closed;
9. changed repair fingerprint never reopens even when the current FAIL object is otherwise structurally valid.

Together with the previously passing 18-case Lane-E suite, the focused Lane-E total is now 27 test cases pending execution of this exact head.

## Verification status / exact blocker

The code and tests were committed to the lane branch, but this automation environment cannot execute the exact head at this checkpoint:

- the local container/Python runner returns infrastructure `ClientError` before command execution;
- the available remote YepCode runner requests interactive user authorization, which is unavailable in this non-interactive automation run;
- PR #330 targets the NextGen integration branch and has no GitHub Actions workflow run that can be used as a substitute test execution.

Therefore this checkpoint does **not** claim 27/27 passed. The previous code checkpoint remains genuinely 18/18 passed plus `py_compile` passed. The serialized integrator or next runnable lane turn must execute:

```bash
cd scanner-api
PYTHONPATH=. python -m pytest -q \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py
python -m py_compile \
  app/nextgen_fix_verification.py \
  app/nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py
```

No test result should be inferred from code review status alone.

## Serialized integration handoff

After A–D have been integrated and the full relevant suites remain green, the serialized integrator should:

1. produce a Lane-E result only through `evaluate_verification_plan(...)`;
2. independently retain the existing `compare_repair_runs(...)` / `verified_fixed_transition_allowed(...)` conjunctive rule for durable fixed transitions;
3. validate any later stored/transferred verification result with `verification_result_integrity(...)` before treating PASS/PARTIAL/FAIL as proof;
4. use `strict_regression_reopen_decision(...)`, not a bare state string, when proposing a regression reopen;
5. keep every durable workflow/persistence mutation in the existing signed authority path outside this lane.

## Safety boundary

This checkpoint changes only pure NextGen helper/test/docs files. It does not modify `run_scan`, global budgets, repair priority, durable authority/persistence, customer projection, admission, release, deployment, worker configuration, schema, credentials, or production.