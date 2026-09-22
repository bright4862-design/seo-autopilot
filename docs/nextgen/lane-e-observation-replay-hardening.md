# Lane E — observation-bound verified-fixed replay hardening

Branch: `agent/nextgen-fix-verification-20260921`

This slice closes the remaining transport-trust gap at the strict `verified_fixed` consumer boundary without changing any durable workflow, authority, persistence, customer projection, scan orchestration, release, deployment, admission, or production surface.

## Problem

`strict_verified_fixed_transition_from_evidence(...)` already recomputes the existing `repair_verification_v3_contract_comparable` comparator from current fixes/pages/contract, so a transported legacy comparator cannot be copied from another repair. However, that helper still accepted a transported NextGen verification result.

A structurally valid transported PASS could therefore be bound to the correct historical repair identity and population while no longer being the result of the current rule observations presented at the final transition boundary. The legacy comparator remained authoritative and fail-closed, but the additional NextGen PASS was not independently replayed from the current plan + rule-evaluation evidence at that final consumer boundary.

## Contract

`fix_verified_fixed_observation_replay_v1_recomputed_nextgen_and_legacy`

`strict_verified_fixed_transition_from_observations(...)` accepts only raw pure evidence inputs:

- historical repair record;
- versioned targeted recheck plan;
- current page observations;
- current rule evaluations;
- current detected fixes;
- current comparison contract;
- authoritative previous/current scan origins supplied by the serialized integrator.

It then:

1. recomputes `evaluate_verification_plan(...)` from the supplied plan/pages/rule evaluations/contract;
2. passes only that recomputed result into `strict_verified_fixed_transition_from_evidence(...)`;
3. lets that existing replay layer recompute `compare_repair_runs(...)` from current fixes/pages/contract;
4. proposes `allowed=true` only when both freshly recomputed proofs satisfy the existing strict transition.

No caller-supplied NextGen PASS or legacy comparator is accepted by this boundary.

## Fail-closed semantics

- A disappeared historical URL produces `COULD_NOT_VERIFY`, never proof of a fix.
- Duplicate or ambiguous rule evidence produces `COULD_NOT_VERIFY`.
- A current FAIL/PARTIAL result cannot be overridden by an empty current-fix list that makes the legacy comparator look `verified_fixed`.
- A truncated/tampered plan population produces `COULD_NOT_VERIFY` before any transition can be proposed.
- Malformed evidence containers or scan-origin transport fail closed.

## Focused regressions

Added `scanner-api/tests/test_nextgen_fix_verified_fixed_observation_replay.py` with 6 deterministic cases:

1. positive dual replay over current evidence;
2. current FAIL while the legacy comparator independently reports `verified_fixed`;
3. PARTIAL with exact unresolved scope;
4. disappeared URL => `COULD_NOT_VERIFY`;
5. duplicate rule evidence => `COULD_NOT_VERIFY`;
6. truncated plan population => `COULD_NOT_VERIFY`.

Lane E expected focused total is now **69 tests**:

- 18 core verification;
- 20 integrity/binding/reopen;
- 19 strict verified-fixed transition;
- 6 legacy-comparator replay;
- 6 observation-bound dual-replay.

## Exact branch-native gate

```bash
cd scanner-api
PYTHONPATH=. python -m pytest -q \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py
python -m py_compile \
  app/nextgen_fix_verification.py \
  app/nextgen_fix_verification_integrity.py \
  app/nextgen_fix_verified_fixed_transition.py \
  app/nextgen_fix_verified_fixed_replay.py \
  app/nextgen_fix_verified_fixed_observation_replay.py \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py
```

## Serialized integration handoff

After lanes A-D are integrated, the serialized integrator should prefer `strict_verified_fixed_transition_from_observations(...)` at the final verification decision boundary. Supply historical/current origins only from authoritative scan/crawl-scope metadata. Persist/project nothing unless the returned `allowed` value is exactly `True` and all existing authority/persistence gates also pass.

This lane does not modify those shared integration surfaces.
