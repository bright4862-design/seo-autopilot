# Agent E — historical evidence-population binding hardening

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint is additive and remains inside the Agent E pure-helper/test/docs ownership boundary defined by `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

The previous `fix_verification_result_binding_v1` bound a transported PASS/PARTIAL/FAIL result to the historical repair fingerprint and regenerated acceptance-criterion id. That prevented foreign criteria and stale repair identity claims from proving a transition, but it did not independently bind the transported population count or resolved/unresolved evidence keys back to the historical affected-page population.

A structurally complete result could therefore be fabricated over a subset or a same-sized foreign set while carrying the correct repair fingerprint and criterion id. If a similarly forged legacy comparison reported the same count, the strict verified-fixed consumer could not distinguish that transport from the actual full historical evidence population. That is inconsistent with the lane rule that disappeared/ambiguous evidence must never prove a fix or a regression.

## New binding contract

`scanner-api/app/nextgen_fix_verification_integrity.py` now reports:

- `fix_verification_result_binding_v2_population_bound`
- `fix_regression_reopen_v4_population_bound`

For proving PASS/PARTIAL/FAIL states, `verification_result_historical_binding(...)` now:

1. regenerates the historical acceptance criterion and stable repair identity as before;
2. rebuilds the historical affected-page evidence-key population under the published URL-identity contract;
3. accepts a caller-owned `previous_scan_origin` only as historical URL-identity context, never from transported result data;
4. fails closed when root-relative historical evidence cannot be resolved because that authoritative origin is unavailable;
5. requires the transported `required_population_count` to equal the regenerated historical population size; and
6. requires the union of `resolved_scope` and `unresolved_scope` to equal the exact regenerated historical evidence-key set.

COULD_NOT_VERIFY remains a valid non-proving terminal transport state and is never upgraded into repair or regression proof.

## Regression reopening

`strict_regression_reopen_decision(...)` forwards the authoritative historical scan origin into the binder. A complete-looking FAIL/PARTIAL over a subset or foreign evidence population now downgrades to effective `COULD_NOT_VERIFY` and cannot reopen a verified repair.

The helper remains pure data. It does not write authority, persistence, customer state, projections, or workflow status.

## Verified-fixed transition

`scanner-api/app/nextgen_fix_verified_fixed_transition.py` now reports:

- `fix_verified_fixed_transition_v4_population_bound`

The strict positive transition requires the NextGen PASS to be bound to the exact historical population before considering the existing `repair_verification_v3_contract_comparable` proof. It then requires the legacy comparator's `previous_affected_pages` count to match that independently regenerated historical population count.

Because a ready NextGen acceptance criterion requires explicit rule-definition and comparison-profile versions, a transported legacy comparison marked only `legacy_compatible` is rejected at this strict boundary. The legitimate companion state for a versioned historical repair is `compatible`.

This does not change `compare_repair_runs(...)`; it only hardens the pure consumer of its result.

## Added deterministic regressions

The integrity/binding suite grows from 13 to 17 cases, adding coverage for:

- complete FAIL whose scope is a same-sized foreign evidence set;
- structurally valid one-page subset FAIL against a two-page historical repair;
- root-relative historical evidence requiring authoritative `previous_scan_origin`; and
- missing historical affected-page population failing closed.

The verified-fixed transition suite grows from 13 to 16 cases, adding coverage for:

- complete PASS over a foreign evidence set;
- forged one-page PASS plus forged one-page legacy counts against a two-page historical repair; and
- rejection of `legacy_compatible` for the explicit-version NextGen transition.

Together with the existing 18 core verification tests, Lane E now contains **51 focused tests**.

## Verification performed in this checkpoint

A hermetic pure-function package executed the exact modified integrity and transition modules and their 33 focused scenarios:

```text
33 passed in 0.10s
```

The four modified module/test files also passed `py_compile` in the hermetic package.

This does not replace the exact repository gate. The automation runtime still cannot resolve `github.com` from the local container, so it cannot materialize the full branch for repository-native pytest. GitHub's connector remains usable for branch-safe commits.

Exact branch-wide Lane-E gate after this checkpoint:

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

No exact-head 51/51 repository claim should be made until that command succeeds in an approved checkout/runner.

## Serialized integration handoff

After Agents A-D are integrated and their gates remain green, the serialized integrator should:

1. obtain the historical scan origin from authoritative scan/crawl-scope metadata, not from repair/result transport fields;
2. pass that value as `previous_scan_origin` to the strict binding/reopen/verified-fixed helpers when historical affected URLs are root-relative;
3. continue obtaining the legacy comparison only from existing `compare_repair_runs(...)`;
4. treat any historical population reconstruction/count/scope mismatch as `COULD_NOT_VERIFY`;
5. keep durable authority/persistence/customer projection wiring outside this lane.

## Safety boundary

This checkpoint changes only Lane-E pure helpers, focused tests, and this handoff document. It does not modify `run_scan`, global budgets, repair priority, durable authority/persistence, customer projection, Base44 schema, admission, release/deployment, worker configuration, IAM, credentials, or production.
