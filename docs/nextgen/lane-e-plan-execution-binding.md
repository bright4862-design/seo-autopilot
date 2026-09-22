# Lane E — exact targeted-plan execution binding

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint remains additive and inside the Agent E pure-helper/test/docs ownership boundary from `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

The existing plan-identity boundary proves that the declarative targeted recheck plan received by a strict consumer is byte-for-semantic-transport identical to the plan that was identity-bound. Existing origin and scan-lineage gates separately prove where page/evaluation evidence came from.

Those facts do not by themselves prove that a rule-predicate re-evaluation was produced **for that exact targeted plan**. A rule-evaluation row carrying the right repair fingerprint, criterion id, URL identity, and scan id could otherwise be replayed against another valid plan for the same repair/scan population without an explicit execution-provenance claim.

That is ambiguous proof provenance. Lane E now fails it closed.

## New contract

Implementation: `scanner-api/app/nextgen_fix_verification_execution_binding.py`

Version:

- `fix_verification_plan_execution_binding_v1_exact_evaluation_plan_identity`

Strict final replay versions:

- `fix_verified_fixed_plan_execution_bound_observation_replay_v1_exact_plan_execution`
- `fix_regression_reopen_plan_execution_bound_observation_replay_v1_exact_plan_execution`

`verification_plan_execution_binding_integrity(...)` first requires the existing exact plan-identity gate to pass. It then requires the rule-evaluation population to match the targeted request population exactly and requires every evaluation row to carry:

- exact `verification_plan_fingerprint == plan.plan_fingerprint`;
- exact `verification_plan_identity_version == fix_verification_plan_identity_binding_v1_exact_proof_contract_hash`;
- an exact non-empty `evidence_key`;
- one and only one evaluation for every targeted request;
- no evaluation outside the targeted request population.

Missing, null, whitespace-normalized, duplicated, copied, stale, foreign, or extra execution provenance is non-proof.

This helper performs no network work and mutates no inputs.

## Why this is additive

The underlying acceptance criterion, targeted-plan semantics, observation evaluator, historical comparator, and `repair_verification_v3_contract_comparable` behavior are unchanged.

The new final wrappers run this execution-provenance gate and then delegate to the existing exact plan-identity-bound verified-fixed/regression wrappers. All earlier gates therefore remain active:

- historical repair identity/version integrity;
- historical evidence alias integrity;
- plan envelope, lineage, and exact plan identity;
- current observation type/value/URL identity integrity;
- origin and exact scan lineage;
- result transport integrity;
- existing historical verified-fixed comparability.

## Disappeared URLs remain non-proof

Execution binding only proves which plan a predicate evaluation belongs to. It does not prove that a required page was observed.

When a required current page is absent, the execution binding can be valid while the downstream observation replay still yields `COULD_NOT_VERIFY` with `required_page_not_observed`. A disappeared URL can therefore never authorize `verified_fixed`.

## Focused regressions

`scanner-api/tests/test_nextgen_fix_verification_execution_binding.py` adds 15 deterministic cases covering:

1. exact one-evaluation-per-request execution binding;
2. missing plan fingerprint claim;
3. foreign plan fingerprint claim;
4. whitespace-normalized plan fingerprint claim;
5. missing plan-identity version claim;
6. foreign plan-identity version claim;
7. missing targeted evaluation;
8. unexpected evaluation outside the plan;
9. duplicate evaluation identity;
10. mutated plan denied by the existing plan-identity gate before execution proof;
11. exact PASS propagation through verified-fixed replay;
12. foreign execution receipt denied as `COULD_NOT_VERIFY`;
13. exact FAIL regression reopening;
14. exact PARTIAL regression reopening with unresolved scope preserved;
15. disappeared required URL remaining `COULD_NOT_VERIFY`.

Expected focused Lane-E total after this slice: **248 tests** (previous 233 + 15).

## Verification in this constrained runtime

- new helper source syntax-compiles;
- new focused test source syntax-compiles;
- hermetic execution-binding/helper-wrapper harness: **10/10 passed**;
- repository-native focused pytest remains the authoritative gate and is not claimed here because this runtime cannot obtain a GitHub checkout.

Exact focused gate is the PR #330 Lane-E test list plus:

```bash
tests/test_nextgen_fix_verification_execution_binding.py
```

Do not claim 248/248 exact-head repository green until that focused pytest command succeeds in an approved checkout/runner.

## Serialized integration handoff

After lanes A-D are integrated and the relevant scanner regressions are green, the serialized integrator should:

1. build targeted work with `build_identity_bound_targeted_recheck_plan(...)`;
2. execute only that exact plan;
3. stamp every produced rule-predicate evaluation with the plan's exact `plan_fingerprint` and `PLAN_IDENTITY_BINDING_VERSION`;
4. pass only the exact targeted evaluation population to the new execution-bound replay wrappers;
5. source scan ids/origins from authoritative ScanRun/crawl-scope metadata, never request guesses;
6. treat any absent, malformed, duplicated, stale, copied, or foreign plan-execution claim as `COULD_NOT_VERIFY`;
7. preserve the existing legacy comparator gate before any durable `verified_fixed` transition;
8. keep durable authority/persistence/customer projection changes serialized outside Lane E.

No durable authority/persistence/customer projection, `run_scan`, global budgets, repair priority, Base44 schema, admission, release/deploy, worker configuration, IAM, credentials, production, merge, or deployment change is part of this checkpoint.
