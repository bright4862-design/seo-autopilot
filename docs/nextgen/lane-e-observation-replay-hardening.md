# Lane E — observation-bound verified-fixed replay hardening

Branch: `agent/nextgen-fix-verification-20260921`
Issue: #326
Draft PR: #330

This slice stays inside the Lane-E pure helper/test/docs boundary from `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not change durable workflow, authority, persistence, customer projection, scan orchestration, global budgets, release, deployment, admission, or production behavior.

## Problem closed

`strict_verified_fixed_transition_from_evidence(...)` already recomputes the existing `repair_verification_v3_contract_comparable` comparator from current fixes/pages/contract, so a transported legacy comparator cannot be copied from another repair. The first observation-replay boundary then removed analogous trust in a transported NextGen PASS by recomputing `evaluate_verification_plan(...)` from current observations.

A remaining transport-integrity gap was that the underlying compatibility helpers intentionally use tolerant text cleanup for historical read compatibility. At a proving boundary, that tolerance is unsafe: a numeric version value such as `3` can be coerced to `"3"`, and whitespace-padded criterion ids, repair fingerprints, version strings, or rule-evaluation evidence keys can be normalized into apparently matching proof.

The Lane-E requirement is stricter: ambiguous identity/version/evidence must fail closed to `COULD_NOT_VERIFY`.

## New exact observation-input contract

Implementation: `scanner-api/app/nextgen_fix_verification_observation_integrity.py`

Version:

- `fix_verification_observation_input_integrity_v1_exact_identity_and_versions`

Entrypoints:

- `verification_observation_input_integrity(...)`
- `evaluate_verification_observations_strict(...)`

Before the existing evaluator may prove PASS/PARTIAL/FAIL, this layer requires exact non-empty strings, with no coercion and no surrounding-whitespace normalization, for:

- historical rule-definition, comparison-profile, and evidence-URL-identity versions;
- plan repair identity version, repair fingerprint, criterion id, rule, and comparison versions;
- the nested criterion's corresponding identity/version fields and predicate identity;
- current comparison-contract versions;
- each rule-evaluation criterion id, repair fingerprint, comparison versions, and any transported evidence identity (`evidence_key`, `url`, `page_url`).

Every rule-evaluation row must carry an explicit evidence identity. Existing `evaluate_verification_plan(...)` remains authoritative for URL resolution, exact historical-population matching, duplicate detection, page eligibility, current contract comparability, and predicate truth. No network work is added.

If exact transport metadata cannot be proven, `evaluate_verification_observations_strict(...)` emits `fix_verification_result_v1` with `state=COULD_NOT_VERIFY`; it never upgrades or normalizes the malformed evidence.

## Final observation replay contract

`strict_verified_fixed_transition_from_observations(...)` now reports:

- `fix_verified_fixed_observation_replay_v2_exact_proving_metadata`

It now:

1. validates exact proving identity/version transport through `evaluate_verification_observations_strict(...)`;
2. recomputes the NextGen verification result from the supplied plan/pages/rule evaluations/contract;
3. passes only that recomputed result into `strict_verified_fixed_transition_from_evidence(...)`;
4. lets that existing replay layer recompute `compare_repair_runs(...)` from current fixes/pages/contract;
5. proposes `allowed=true` only when both freshly recomputed proofs satisfy the existing strict transition.

No caller-supplied NextGen PASS or legacy comparator is accepted by this boundary.

## Fail-closed semantics

- A disappeared historical URL remains `COULD_NOT_VERIFY`, never proof of a fix.
- Duplicate or ambiguous rule evidence remains `COULD_NOT_VERIFY`.
- Numeric/non-string comparison versions cannot be string-coerced into compatibility.
- Whitespace-padded plan/criterion fingerprints or ids cannot normalize into proof.
- Whitespace-padded rule-evaluation evidence identities cannot normalize into proof.
- A current FAIL/PARTIAL result cannot be overridden by an empty current-fix list that makes the legacy comparator independently report `verified_fixed`.
- A truncated/tampered plan population remains `COULD_NOT_VERIFY` before any transition can be proposed.
- Malformed evidence containers or scan-origin transport fail closed.

## Focused regressions

Existing `scanner-api/tests/test_nextgen_fix_verified_fixed_observation_replay.py` retains 6 deterministic dual-replay cases.

New `scanner-api/tests/test_nextgen_fix_verification_observation_integrity.py` adds 8 deterministic cases:

1. canonical exact metadata preserves normal PASS behavior;
2. numeric historical version fails closed rather than being string-coerced;
3. whitespace-padded current-contract version fails closed;
4. whitespace-padded plan identity fails closed;
5. whitespace-padded nested criterion identity fails closed;
6. whitespace-padded rule-evaluation evidence key fails closed even without a URL fallback;
7. numeric rule-evaluation version fails closed when its string form would otherwise compare equal;
8. the final observation-replay boundary uses the exact-metadata gate and denies transition.

Lane E expected focused total is now **77 tests**:

- 18 core verification;
- 20 integrity/binding/reopen;
- 19 strict verified-fixed transition;
- 6 legacy-comparator replay;
- 6 observation-bound dual-replay;
- 8 exact observation-input metadata tests.

## Verification in this runtime

The new pure exact-metadata layer and updated observation-replay plumbing were exercised in a hermetic package with deterministic stubs around the unchanged legacy comparator/evaluator dependencies. The focused harness passed **8/8** scenarios and `py_compile` passed for the new/updated helper modules.

This is not represented as the complete branch-native test suite. The current automation execution environment still cannot resolve `github.com` for a checkout, so the exact repository-native 77-test gate remains required.

## Exact branch-native gate

```bash
cd scanner-api
PYTHONPATH=. python -m pytest -q \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py \
  tests/test_nextgen_fix_verification_observation_integrity.py
python -m py_compile \
  app/nextgen_fix_verification.py \
  app/nextgen_fix_verification_integrity.py \
  app/nextgen_fix_verified_fixed_transition.py \
  app/nextgen_fix_verified_fixed_replay.py \
  app/nextgen_fix_verified_fixed_observation_replay.py \
  app/nextgen_fix_verification_observation_integrity.py \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py \
  tests/test_nextgen_fix_verification_observation_integrity.py
```

Do not claim 77/77 exact-head repository green until that command succeeds in an approved checkout/runner.

## Serialized integration handoff

After lanes A-D are integrated, the serialized integrator should prefer `strict_verified_fixed_transition_from_observations(...)` at the final verification decision boundary. Supply historical/current origins only from authoritative scan/crawl-scope metadata. Persist/project nothing unless the returned `allowed` value is exactly `True` and all existing authority/persistence gates also pass.

The integrator should not recreate tolerant string-normalization around the new exact observation-input proof boundary. Historical read compatibility can remain tolerant elsewhere; positive verification authority must stay exact and fail closed.
