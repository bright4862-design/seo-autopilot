# Lane E — exact page-observation execution binding

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint remains additive and inside the Agent E pure-helper/test/docs boundary defined in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

The prior targeted-plan execution boundary proves that every rule-predicate evaluation belongs to the exact identity-bound targeted recheck plan. Existing scan-lineage and origin gates separately prove which scan/site the page observations came from.

That still leaves one ambiguity: a current page observation from another recheck batch inside the same scan could be paired with an otherwise valid rule-evaluation receipt for the approved plan. Since page metadata (`http_status`, `content_type`, `indexability`) is proof-bearing, same-scan provenance alone is not enough to prove that the page row was produced for the exact targeted-plan execution.

Lane E now fails that ambiguity closed.

## New contract

Implementation: `scanner-api/app/nextgen_fix_verification_observation_execution.py`

Version:

- `fix_verification_observation_execution_binding_v1_exact_page_plan_identity`

Strict final replay versions:

- `fix_verified_fixed_observation_execution_bound_replay_v1_exact_page_plan_identity`
- `fix_regression_reopen_observation_execution_bound_replay_v1_exact_page_plan_identity`

`verification_observation_execution_binding_integrity(...)` first requires the existing exact rule-evaluation execution binding. It then requires every **present** page observation to carry:

- an exact non-empty `evidence_key` targeted by the plan;
- exact `verification_plan_fingerprint == plan.plan_fingerprint`;
- exact `verification_plan_identity_version == fix_verification_plan_identity_binding_v1_exact_proof_contract_hash`;
- no duplicate page evidence key;
- no page observation outside the targeted population.

Missing, null, whitespace-normalized, duplicated, copied/stale, foreign, or untargeted page execution claims are non-proof and fail closed before PASS/PARTIAL/FAIL can become authoritative evidence.

## Disappeared URLs remain non-proof

This boundary intentionally does **not** require every targeted page to be present. If a required URL disappears, the binding records it in `missing_required_evidence_keys` and delegates to the existing evaluator. The downstream evaluator then preserves the established `required_page_not_observed` outcome and returns `COULD_NOT_VERIFY`.

That distinction is deliberate: disappearance is an observation gap, not proof of a fix and not a reason to fabricate a page-execution integrity failure.

## Compatibility preserved

The new wrappers delegate to the existing exact plan-execution-bound replay after this additional page-execution check. Therefore all prior gates remain active, including stable repair identity, complete historical evidence population, exact criterion/plan identity, observation identity/value integrity, origin/scan lineage, exact rule-evaluation execution provenance, result transport, and the unchanged historical `repair_verification_v3_contract_comparable` gate.

No existing comparator implementation is modified.

## Focused regressions

`scanner-api/tests/test_nextgen_fix_verification_observation_execution.py` adds 13 deterministic cases covering exact page/evaluation execution receipts, malformed/foreign/duplicate page receipts, PASS propagation, FAIL/PARTIAL regression reopening, and the disappeared-page invariant.

Expected focused Lane-E total after this slice: **261 tests** (previous 248 + 13).

## Verification in this constrained runtime

- new helper source syntax-compiles;
- new focused test source syntax-compiles;
- hermetic page/evaluation execution-binding harness: **10/10 passed**;
- repository-native focused pytest remains authoritative and is not claimed here because this runtime cannot resolve `github.com` for a checkout.

Exact focused gate is the PR #330 Lane-E test list plus:

```bash
tests/test_nextgen_fix_verification_observation_execution.py
```

Do not claim 261/261 exact-head repository green until that focused pytest command succeeds in an approved checkout/runner.

## Serialized integration handoff

After lanes A-D are integrated and the relevant scanner regressions are green, the serialized integrator should:

1. build targeted work with `build_identity_bound_targeted_recheck_plan(...)`;
2. execute only that exact plan;
3. stamp every produced rule-predicate evaluation **and every page observation produced by that targeted execution** with the plan's exact `plan_fingerprint` and `PLAN_IDENTITY_BINDING_VERSION`;
4. stamp page observations with the exact targeted `evidence_key` they satisfy;
5. pass only those execution-bound page/evaluation objects to the new observation-execution-bound replay wrappers;
6. continue sourcing historical/current scan ids and origins only from authoritative ScanRun/crawl-scope metadata;
7. treat absent/malformed/duplicated/stale/copied/foreign page execution claims as `COULD_NOT_VERIFY`;
8. preserve missing-page handling as `required_page_not_observed`, never as PASS;
9. preserve the existing legacy comparator gate before any durable `verified_fixed` transition;
10. keep durable authority/persistence/customer projection wiring serialized outside Lane E.

No durable authority/persistence/customer projection, `run_scan`, global budgets, repair priority, Base44 schema, admission, release/deploy, worker configuration, IAM, credentials, production, merge, or deployment change is part of this checkpoint.
