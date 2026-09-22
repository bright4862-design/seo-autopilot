# Agent E — exact recheck-plan transport hardening

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint remains inside the Agent E pure-helper/test/docs ownership boundary defined by `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

The strict observation boundary already rejected normalized top-level plan metadata, criterion metadata, current rule-evaluation metadata, and conflicting current observation identities. A remaining proving-transport gap existed inside `plan.requests`: the compatible evaluator deliberately uses `_clean(...)` for request `evidence_key`, `criterion_id`, and `rule`, and the published URL resolver accepts the request URL after normal compatibility handling. A transported request could therefore contain whitespace-padded or non-string metadata that normalized into the expected plan identity before the core population checks ran.

Historical evidence transport had a related compatibility edge: `_raw_affected_pages(...)` intentionally cleans historical values for read compatibility. At the final proving boundary, a whitespace-padded historical affected URL or a malformed non-null `affected_pages` container must not silently normalize or fall back into proof.

## New strict contract

`scanner-api/app/nextgen_fix_verification_observation_integrity.py` now reports:

- `fix_verification_observation_input_integrity_v2_exact_plan_request_transport`

Before `evaluate_verification_plan(...)` can produce PASS / PARTIAL / FAIL, the pure integrity layer now requires:

1. every supplied historical `affected_pages` identity to already be an exact non-empty string;
2. a non-null malformed historical `affected_pages` container to fail closed instead of being ignored in favor of `page_url` / `representative_page_url`;
3. fallback historical page identities, when needed, to be exact non-empty strings;
4. `plan.requests` to be a non-empty list of objects;
5. every request `url`, `evidence_key`, `criterion_id`, and `rule` to already be exact non-empty strings with no coercion or surrounding-whitespace normalization;
6. request `criterion_id` and `rule` to exactly equal the top-level plan values;
7. request evidence keys to be unique before the compatible evaluator runs;
8. every request to carry the exact versioned `required_observations` contract.

The core evaluator remains authoritative for canonical URL derivation, exact historical-population equality, page comparability, duplicate current observations, and rule-predicate truth. This checkpoint does not alter those semantics; it closes only the proving transport boundary around them.

Because the existing verified-fixed and regression-reopen observation replay helpers already route through the strict observation integrity evaluator, malformed request transport now becomes `COULD_NOT_VERIFY` before either a positive verified-fixed proposal or a regression reopen can be proven.

## Added deterministic regressions

New suite: `scanner-api/tests/test_nextgen_fix_verification_plan_transport_integrity.py`

Nine cases cover:

1. normal exact request transport remains valid;
2. whitespace-padded request `evidence_key` fails closed;
3. non-string request `criterion_id` fails closed;
4. whitespace-padded request URL fails before normalization;
5. whitespace-padded request rule fails closed;
6. whitespace-padded historical affected-page identity fails closed;
7. malformed historical `affected_pages` container cannot be silently replaced by a fallback URL;
8. whitespace-padded historical fallback page identity fails closed;
9. the strict evaluator returns `COULD_NOT_VERIFY` rather than upgrading normalized request transport into proof.

Lane E expected focused total is now **103 tests**:

- 18 core verification;
- 20 integrity/binding/reopen;
- 19 strict verified-fixed transition;
- 6 legacy-comparator replay;
- 6 verified-fixed observation replay;
- 8 exact observation-input metadata;
- 7 regression-reopen observation replay;
- 10 exact current-observation identity binding;
- 9 exact plan-request/historical-evidence transport.

## Verification performed in this runtime

- modified helper source compiled successfully with Python `compile(...)`;
- new test source compiled successfully with Python `compile(...)`;
- a hermetic pure-function transport-integrity harness passed **8/8** positive/negative boundary scenarios;
- an additional strict-wrapper scenario confirmed malformed request transport returns `COULD_NOT_VERIFY` before the compatible evaluator can prove a terminal state.

This is deliberately not represented as the exact repository-native 103-test result. The exact branch-native gate remains required in an approved checkout/runner:

```bash
cd scanner-api
PYTHONPATH=. python -m pytest -q \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py \
  tests/test_nextgen_fix_verification_observation_integrity.py \
  tests/test_nextgen_fix_regression_reopen_replay.py \
  tests/test_nextgen_fix_verification_observation_identity.py \
  tests/test_nextgen_fix_verification_plan_transport_integrity.py
python -m py_compile \
  app/nextgen_fix_verification.py \
  app/nextgen_fix_verification_integrity.py \
  app/nextgen_fix_verified_fixed_transition.py \
  app/nextgen_fix_verified_fixed_replay.py \
  app/nextgen_fix_verified_fixed_observation_replay.py \
  app/nextgen_fix_verification_observation_integrity.py \
  app/nextgen_fix_regression_reopen_replay.py \
  app/nextgen_fix_verification_observation_identity.py \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py \
  tests/test_nextgen_fix_verification_observation_integrity.py \
  tests/test_nextgen_fix_regression_reopen_replay.py \
  tests/test_nextgen_fix_verification_observation_identity.py \
  tests/test_nextgen_fix_verification_plan_transport_integrity.py
```

## Integration handoff

After Agents A-D integrate and the serialized integrator is ready for Lane E, keep using the observation-bound replay entrypoints already documented by this lane. Do not pre-normalize or repair malformed verification-plan request transport before calling them. Any failed `observation_input_integrity` is non-proof and must remain `COULD_NOT_VERIFY`; durable authority/persistence/customer projection remains outside this lane.

No `run_scan`, global budgets, repair priority, durable authority/persistence/customer projection, Base44 schema, admission, release/deployment, worker configuration, IAM, credentials, production, merge, or deployment behavior is changed by this checkpoint.
