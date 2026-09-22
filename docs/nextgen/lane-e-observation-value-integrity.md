# Agent E — exact proving observation values

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint stays inside the Agent E pure-helper/test/docs ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

The existing NextGen proof path already binds repair identity, criterion/version metadata, the exact historical evidence population, plan-request transport, and all supplied URL aliases. The legacy page-comparability helper remains intentionally tolerant for historical compatibility, however. In particular, it converts HTTP status through `int(...)`, tokenizes content-type/evidence metadata through string conversion, and treats unknown indexability as comparable so older scans remain readable.

Those compatibility rules must not become new proof. A current observation such as `status_code="200"` or `status_code=200.0` could previously reach the compatibility helper and be interpreted as HTTP 200. A non-string content type such as `["text/html"]` could stringify to text containing `html`. A non-boolean `indexable="true"` could become `unknown`, which the historical comparator intentionally keeps comparable. Contradictory status or robots/indexability aliases could also be silently resolved by precedence.

## New versioned value-integrity boundary

Implementation: `scanner-api/app/nextgen_fix_verification_observation_values.py`

Version:

- `fix_verification_observation_value_integrity_v1_exact_proving_values`

Preferred current-observation evaluator:

- `evaluate_verification_observations_value_bound(...)`

Before the existing identity-bound evaluator may produce PASS/PARTIAL/FAIL, every supplied current page now proves:

1. an HTTP status exists in the comparator-recognized `status_code` / `status` fields;
2. every supplied status is an exact Python integer, never `bool`, string, float, or another coercible value;
3. supplied status aliases agree exactly and are in the HTTP 100–599 range;
4. an exact non-empty string `content_type` / `mime_type` exists, with aliases agreeing when both are supplied;
5. `indexable` exists as an exact boolean;
6. optional evidence-class and robots metadata are exact strings when supplied and aliases do not conflict;
7. `indexable=True` cannot coexist with a supplied `noindex` robots directive;
8. rule evaluations carry exact boolean `evaluated` and `defect_detected` values.

Malformed or contradictory proving values return `COULD_NOT_VERIFY`; they can never prove a fix or a regression.

`scanner-api/app/nextgen_fix_verification_historical_bound.py` now composes this boundary after exact historical repair-identity validation. Its version is:

- `fix_verification_historical_bound_observation_v2_exact_repair_identity_and_observation_values`

This means both existing final pure replay paths—verified-fixed proposal and regression reopening—inherit the new fail-closed proving-value boundary without changing the existing `repair_verification_v3_contract_comparable` implementation or historical read semantics.

## Deterministic regressions

`scanner-api/tests/test_nextgen_fix_verification_observation_values.py` adds 11 cases covering:

- exact typed evidence preserving PASS;
- numeric-string and float HTTP statuses failing closed;
- conflicting `status_code` / `status` aliases;
- non-string content type that would stringify to HTML;
- missing content type;
- string indexability;
- `indexable=True` conflicting with `noindex`;
- final verified-fixed replay denial for coerced status evidence;
- final regression-reopen denial for coerced status evidence;
- input immutability.

The expected Lane-E focused total is therefore **126 tests** (previous 115 + 11).

## Verification performed in this checkpoint

The new module, updated historical-bound module, and new test source pass `py_compile`. A hermetic pure-helper harness exercises exact valid evidence plus the status/content/indexability/robots malformed branches.

The exact branch-native focused gate remains required before claiming 126/126:

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
  tests/test_nextgen_fix_verification_observation_values.py
```

Do not claim exact-head repository green until that command runs in an approved checkout/runner.

## Serialized integration handoff

After lanes A–D integrate and their gates remain green, the serialized integrator should use the historical-bound / final replay path and preserve this exact observation-value contract. Do not normalize or coerce proof-bearing page observations before this boundary. If the producing scanner cannot supply exact HTTP status, content type, indexability, and predicate values for a required page, the correct result is `COULD_NOT_VERIFY`.

A disappeared URL remains non-proof. No durable authority/persistence/customer projection, `run_scan`, global budgets, repair priority, Base44 schema, admission, release/deploy, worker configuration, IAM, credentials, production, merge, or deployment change is part of this checkpoint.
