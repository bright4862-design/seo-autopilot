# Lane E — exact historical repair-identity binding

Checkpoint scope: Agent E only. This work is pure verification logic and tests; it does not write durable authority/persistence/customer projection, modify `run_scan` or global budgets, change repair priority, admission, release/deploy, workers, Base44 schema, credentials, or production behavior.

## Gap closed

The existing `repair_identity_v2_technical` builder intentionally normalizes historical values for read/comparison compatibility. That means source values such as rule IDs, repair surfaces, or remediation families can be string-coerced/trimmed before a stable fingerprint is derived. That historical tolerance must not itself become proof for a new PASS, `verified_fixed`, or regression reopen decision.

This checkpoint adds `fix_verification_historical_identity_integrity_v1_exact_source_binding` and `fix_verification_historical_bound_observation_v1_exact_repair_identity`.

Before current re-observation evidence may prove PASS/PARTIAL/FAIL:

- every populated stable-identity source alias (`rule_id`/`rule`/`type`/`issue_type`, repair-surface aliases, remediation-family aliases) must already be an exact string with no surrounding whitespace;
- the freshly derived repair identity must be stable and use the published repair-identity version;
- any persisted top-level identity metadata that is present (`repair_identity_version`, `repair_fingerprint`, `repair_identity_state`, `repair_identity_stable`) must agree with the freshly derived identity;
- any persisted nested `repair_identity` fields that are present must agree with the freshly derived identity;
- ambiguity or malformed identity transport returns `COULD_NOT_VERIFY` before current evidence can become proof.

Canonical `rule_id` and human-facing `rule` text are deliberately allowed to differ. Existing repair identity precedence remains unchanged; this checkpoint validates exact transport types/values without replacing historical identity semantics.

## Authority-facing replay changes

The final pure replay helpers now consume the historical-bound evaluator:

- `fix_verified_fixed_observation_replay_v4_exact_historical_repair_identity`
- `fix_regression_reopen_observation_replay_v3_exact_historical_repair_identity`

Therefore a copied/mismatched persisted fingerprint, numeric/whitespace-coerced stable identity source, or conflicting nested identity snapshot cannot authorize either a future `verified_fixed` proposal or a regression reopening proposal.

A disappeared required URL remains `COULD_NOT_VERIFY`; this layer does not alter the existing population/eligibility/comparability rules.

## Tests

Added `scanner-api/tests/test_nextgen_fix_verification_historical_identity.py` with 12 deterministic regressions covering:

1. canonical rule ID plus differing human display copy remains valid;
2. numeric canonical rule identity fails closed;
3. whitespace-padded repair surface fails closed;
4. mismatched persisted fingerprint fails closed;
5. matching persisted identity metadata remains valid;
6. conflicting nested identity snapshot fails closed;
7. the historical-bound evaluator preserves a normal PASS;
8. tolerantly coercible historical identity becomes `COULD_NOT_VERIFY`;
9. disappeared URL remains non-proof;
10. final `verified_fixed` replay rejects conflicting historical fingerprint;
11. regression reopen rejects malformed historical identity source;
12. valid PARTIAL evidence still reopens a previously verified repair.

Expected Lane-E focused total after this checkpoint: **115 tests** (previous 103 + 12 new).

Verification possible in the current runtime:

- new/modified Python sources and new test source passed `py_compile` locally;
- hermetic historical-identity helper harness: **8/8** scenarios passed;
- hermetic final-wrapper plumbing harness: **5/5** scenarios passed.

Exact branch-native pytest remains required because this runtime cannot resolve `github.com` for a checkout.

## Exact branch-native gate

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
  tests/test_nextgen_fix_verification_plan_transport_integrity.py \
  tests/test_nextgen_fix_verification_historical_identity.py

python -m py_compile \
  app/nextgen_fix_verification.py \
  app/nextgen_fix_verification_integrity.py \
  app/nextgen_fix_verified_fixed_transition.py \
  app/nextgen_fix_verified_fixed_replay.py \
  app/nextgen_fix_verified_fixed_observation_replay.py \
  app/nextgen_fix_verification_observation_integrity.py \
  app/nextgen_fix_verification_observation_identity.py \
  app/nextgen_fix_verification_historical_identity.py \
  app/nextgen_fix_verification_historical_bound.py \
  app/nextgen_fix_regression_reopen_replay.py \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py \
  tests/test_nextgen_fix_verification_observation_integrity.py \
  tests/test_nextgen_fix_regression_reopen_replay.py \
  tests/test_nextgen_fix_verification_observation_identity.py \
  tests/test_nextgen_fix_verification_plan_transport_integrity.py \
  tests/test_nextgen_fix_verification_historical_identity.py
```

## Serialized integrator handoff

After lanes A–D are integrated, use `strict_verified_fixed_transition_from_observations(...)` for any positive `verified_fixed` proposal and `strict_regression_reopen_from_observations(...)` for any durable reopen proposal. Do not normalize historical repair identity source fields or persisted identity metadata before calling these helpers. Treat failed `historical_identity_integrity` as non-proof. Existing durable authority/persistence/comparability gates remain independently required.
