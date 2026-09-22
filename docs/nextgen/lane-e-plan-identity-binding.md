# Lane E — exact targeted-plan identity binding

## Scope

This Lane-E-only additive helper closes a remaining proof-transport gap after scan-lineage and terminal-result hardening. A targeted recheck plan can be structurally valid and bound to the correct historical scan, yet still be mutated after construction before it reaches the final verified-fixed or regression-reopen replay. Existing downstream checks catch many semantic mutations, but they do not provide one immutable identity for the exact plan transport that was approved for execution.

No durable authority, persistence, customer projection, `run_scan`, global budget, admission, release/deploy, worker, IAM, credential, or production surface is changed.

## Contract

`scanner-api/app/nextgen_fix_verification_plan_identity.py` adds:

- `fix_verification_plan_identity_binding_v1_exact_proof_contract_hash`
- `build_identity_bound_targeted_recheck_plan(...)`
- `bind_verification_plan_identity(...)`
- `verification_plan_identity_integrity(...)`
- `fix_verified_fixed_plan_identity_bound_observation_replay_v1_exact_plan_contract`
- `fix_regression_reopen_plan_identity_bound_observation_replay_v1_exact_plan_contract`

The fingerprint is SHA-256 over the complete ready plan transport after the existing plan-envelope and historical plan-lineage gates pass. The identity metadata itself is excluded from the hash. The committed material therefore includes the exact raw request targets, evidence keys, criterion and predicate contract, bounded-population metadata, required observations, blockers/state, and scan-lineage claims. Dict keys are canonicalized for hashing; list order and raw string transport are preserved. Unsupported/coercible transport values fail closed rather than being stringified.

A plan can prove identity only when:

1. the existing ready-plan envelope is valid;
2. the existing historical plan-lineage binding is valid for the caller-owned historical scan id;
3. identity version/state/reason are exact;
4. the declared fingerprint is exact lowercase SHA-256 transport; and
5. recomputing the hash from the received plan produces the same fingerprint.

Post-build changes that can otherwise look semantically equivalent—such as replacing `/a` with `https://example.com/a` while keeping the same evidence key—are therefore a different plan and fail closed before final proof.

## Final replay semantics

The new verified-fixed and regression-reopen wrappers run the exact plan-identity gate first, then delegate to the existing plan+scan-bound replay. The existing `repair_verification_v3_contract_comparable` behavior is unchanged. The new gate adds proof; it does not replace comparator, origin, scan-lineage, historical-identity, observation, plan-envelope, or result-integrity gates.

A missing required URL remains `COULD_NOT_VERIFY`. Plan identity only proves which plan was executed; it never converts disappearance into repair evidence.

## Focused regressions

`scanner-api/tests/test_nextgen_fix_verification_plan_identity.py` adds 14 deterministic cases covering:

- identity stamping and deterministic hashing;
- input immutability;
- exact raw URL transport mutation;
- required-observation mutation;
- acceptance-predicate mutation;
- unexpected transport-field mutation;
- missing or uppercase/non-exact SHA-256 transport;
- invalid historical scan identity;
- exact PASS propagation through verified-fixed replay;
- post-build mutation denial before verified-fixed proof;
- exact FAIL regression reopening plus mutation denial; and
- disappeared required URL remaining `COULD_NOT_VERIFY`.

Expected focused Lane-E total after this slice: **233 tests** (previous 219 + 14).

## Verification in the constrained runtime

- new helper source syntax-compiles;
- new focused test source syntax-compiles;
- hermetic identity/wrapper harness: **12/12 passed**;
- repository-native focused pytest remains the integration gate and is not claimed here because the execution container cannot resolve `github.com` for a checkout.

## Serialized integration handoff

The integrator should build future targeted verification work with `build_identity_bound_targeted_recheck_plan(...)`, using the authoritative historical ScanRun/crawl-scope scan id and origin. Final observation replay should prefer the new identity-bound wrappers. Treat a missing, malformed, stale, copied, or recomputation-mismatched plan fingerprint as non-proof and keep the effective state at `COULD_NOT_VERIFY`. Persistence/customer projection must remain behind the existing serialized authority gates.
