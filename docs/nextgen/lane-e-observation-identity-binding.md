# Agent E — exact current-observation identity binding

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint remains inside the Agent E pure-helper/test/docs ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

The existing strict observation metadata boundary proves exact repair/criterion/version transport, and the core evaluator binds the selected current evidence key to the complete historical affected-page population. A remaining ambiguity existed between those two layers: current page and rule-evaluation objects may carry more than one URL identity alias (`url`, `final_url`, `page_url`, `path`, or a declared `evidence_key`), while the legacy-compatible evaluator intentionally selects the first non-empty alias.

That tolerant lookup is useful for historical reads but is too permissive for a proving boundary. For example, a page object could carry the required historical URL in `url` while also carrying a different redirect target in `final_url`; selecting only `url` would hide contradictory evidence. Likewise, a rule-evaluation row could carry a matching declared `evidence_key` but a foreign URL alias. Ambiguous identity/evidence must fail closed rather than prove a fix or regression.

## New versioned contract

Implementation: `scanner-api/app/nextgen_fix_verification_observation_identity.py`

Version:

- `fix_verification_observation_identity_binding_v1_exact_multi_field_identity`

Entry points:

- `verification_observation_identity_binding(...)`
- `evaluate_verification_observations_identity_bound(...)`

The pure identity binder:

1. requires current page/rule-evaluation collections and the current comparison contract to have the expected container shapes;
2. requires the current evidence URL-identity version to be the published route-identity contract;
3. resolves every non-empty supplied page identity alias (`url`, `final_url`, `page_url`, `path`) under the caller-owned current scan origin;
4. requires all supplied aliases on one page to resolve to the exact same evidence identity;
5. resolves every non-empty rule-evaluation URL alias and requires them to agree;
6. requires any transported `evidence_key` to already be canonical under the same URL-identity contract and to agree with every supplied evaluation URL alias;
7. treats missing, whitespace-padded, non-string, unresolvable, non-canonical, or conflicting proving identities as `COULD_NOT_VERIFY`;
8. performs no network work and mutates no inputs.

Optional identity aliases may be absent or empty. If an alias is populated, it becomes proving transport data and must be exact. A redirect-like `url`/`final_url` conflict is therefore non-comparable evidence, not proof that the original defect disappeared.

## Final replay boundaries upgraded

The customer-authority boundaries remain pure and non-persistent, but now consume the identity-bound evaluator:

- `fix_verified_fixed_observation_replay_v3_exact_observation_identity`
- `fix_regression_reopen_observation_replay_v2_exact_observation_identity`

A conflicting current page/evaluation identity therefore cannot authorize a future `verified_fixed` proposal and cannot reopen a previously verified repair. Both become `COULD_NOT_VERIFY` before the existing historical binding/comparability state machines are asked to decide.

The existing `repair_verification_v3_contract_comparable` comparator itself is unchanged.

## Added deterministic regressions

`scanner-api/tests/test_nextgen_fix_verification_observation_identity.py` adds 10 focused cases:

1. equivalent `url` / absolute `final_url` / `path` aliases preserve normal PASS behavior;
2. conflicting `url` and `final_url` fail closed;
3. whitespace-padded page identity fails closed;
4. a current page with no usable identity fails closed;
5. conflicting rule-evaluation URL aliases fail closed;
6. a rule-evaluation `evidence_key` conflicting with its URL fails closed;
7. a non-canonical transported `evidence_key` fails closed;
8. the final verified-fixed replay denies a conflicting redirect identity;
9. the final regression-reopen replay does not reopen from a conflicting redirect identity;
10. the pure binder does not mutate current page/evaluation inputs.

Lane E therefore has an expected **94 focused tests** after this checkpoint:

- 18 core verification;
- 20 integrity/binding/reopen;
- 19 strict verified-fixed transition;
- 6 legacy-comparator replay;
- 6 verified-fixed observation replay;
- 8 exact observation-input metadata;
- 7 regression-reopen observation replay;
- 10 exact current-observation identity binding.

## Verification in this runtime

The container still cannot resolve `github.com`, so an exact branch checkout is unavailable here. A hermetic identity-boundary harness exercised equivalent aliases, redirect conflicts, whitespace identities, missing page identity, conflicting evaluation aliases, conflicting/non-canonical `evidence_key`, and evidence-key-only transport; **8/8 scenarios passed**.

Do not represent this as the exact repository-native 94-test suite. The exact branch-native gate remains:

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
  tests/test_nextgen_fix_verification_observation_identity.py
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
  tests/test_nextgen_fix_verification_observation_identity.py
```

## Serialized integration handoff

After Agents A–D are integrated and their gates are green, the serialized integrator should continue to obtain historical/current scan origins only from authoritative scan/crawl-scope metadata. For any future durable positive transition, call `strict_verified_fixed_transition_from_observations(...)`; for any future durable regression reopening, call `strict_regression_reopen_from_observations(...)`. Treat a failed `observation_identity_binding` as non-proof. Persist or project nothing unless the relevant pure decision is explicitly affirmative and all existing authority/persistence/comparability gates independently pass.

No durable authority/persistence/customer projection, `run_scan`, global budget, repair-priority, Base44 schema, admission, release/deploy, worker configuration, IAM, credential, production, merge, or deployment change is part of this checkpoint.
