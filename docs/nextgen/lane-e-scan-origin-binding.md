# Lane E — exact scan-origin binding hardening

Status: **pure NextGen Lane-E helper/test work only**. No merge, deploy, persistence, customer projection, admission, `run_scan`, global budget, or production changes.

## Problem closed

Published-route evidence identity intentionally accepts a caller-owned `scan_origin` so root-relative observations can be resolved. That origin is therefore part of the proof context. Without an explicit source-binding gate, a relative observation from one scan could be interpreted under another origin if an integrator supplied the wrong caller context.

A disappeared URL is still never proof of a fix. This slice adds an earlier fail-closed rule: **URL evidence is not proof at all unless the historical repair population, targeted recheck plan, current page observations, and rule-evaluation identities are bound to one exact canonical scan origin.**

## Contract

New pure contract:

- `fix_verification_scan_origin_binding_v1_exact_authoritative_origins`

`verification_scan_origin_binding_integrity(...)` requires:

1. `previous_scan_origin` and `scan_origin` are non-empty exact strings;
2. each origin is already in canonical published-origin form (no whitespace, path, trailing slash, case/default-port normalization drift, or otherwise normalized transport);
3. historical and current origins are identical for same-page repair verification;
4. every historical affected URL/fallback identity resolves inside that origin;
5. every targeted request URL and declared evidence key resolves inside that origin and agrees exactly;
6. every populated current page URL alias resolves inside the current origin;
7. every rule-evaluation declared evidence key / URL alias resolves inside the current origin.

Any failure produces `COULD_NOT_VERIFY`; the helper never normalizes malformed caller transport into proof.

The pure evaluator `evaluate_verification_observations_origin_bound(...)` runs this gate before the existing historical-identity, proving-value, observation-identity, plan-transport, comparable-page, and rule-predicate gates.

## Final replay boundaries

The final positive-transition and regression-reopening replay helpers now consume the origin-bound evaluator:

- `fix_verified_fixed_observation_replay_v5_exact_scan_origin_binding`
- `fix_regression_reopen_observation_replay_v4_exact_scan_origin_binding`

The existing historical comparator `repair_verification_v3_contract_comparable` remains unchanged. `verified_fixed` still requires the existing comparator proof in conjunction with the recomputed NextGen PASS.

## Regressions

Added `scanner-api/tests/test_nextgen_fix_verification_origin_binding.py` with 10 deterministic cases covering:

- canonical same-origin success;
- non-canonical historical origin rejection;
- historical/current origin mismatch rejection;
- foreign historical affected-page identity rejection;
- foreign plan evidence-key rejection;
- foreign current-page identity rejection before predicate proof;
- foreign rule-evaluation evidence-key rejection;
- valid PASS preservation through the new boundary;
- final `verified_fixed` replay failing closed on origin mismatch;
- final regression-reopen replay failing closed on foreign current evidence.

Expected Lane-E focused total: **136 tests** (previous 126 + 10 origin-binding regressions).

This runtime validated the new module, both modified final replay modules, and new test source with `py_compile`. A hermetic origin-binding harness exercised 8 valid/invalid boundary scenarios and passed **8/8**. Repository-native pytest on the exact branch head remains the authoritative gate.

## Exact focused gate

```bash
cd scanner-api
PYTHONPATH=. python -m pytest -q \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py \
  tests/test_nextgen_fix_verification_observation_integrity.py \
  tests/test_nextgen_fix_verification_plan_transport_integrity.py \
  tests/test_nextgen_fix_verification_observation_identity.py \
  tests/test_nextgen_fix_verification_historical_identity.py \
  tests/test_nextgen_fix_regression_reopen_replay.py \
  tests/test_nextgen_fix_verification_observation_values.py \
  tests/test_nextgen_fix_verification_origin_binding.py
```

## Serialized integration handoff

After lanes A–D have been integrated, the serialized integrator should source `previous_scan_origin` and `scan_origin` only from the authoritative historical/current scan or crawl-scope records. Do not derive or normalize these origins from browser input, a repair row, a request payload, or whichever page happens to be present.

The page/evaluation collections passed to the final Lane-E replay helpers must come from the same authoritative current scan as `scan_origin`. Lane E deliberately does **not** add cross-scan authority/persistence wiring or a durable scan-ID envelope; those surfaces remain serialized-integrator ownership. If source scan identity cannot be established, integration must return/retain `COULD_NOT_VERIFY` rather than invoking the proof path with guessed context.
