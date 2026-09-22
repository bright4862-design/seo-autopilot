# Lane E — targeted verification-plan scan-lineage binding

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint remains inside the Agent E pure-helper/test/docs ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

The previous scan-lineage checkpoint bound the historical repair, current comparison contract, current page observations, current rule evaluations, and current fix rows to exact authoritative scan IDs. The targeted recheck plan itself, however, remained scan-agnostic transport data.

That left a provenance ambiguity: an otherwise identical ready plan could be copied from another historical scan that happened to contain the same stable repair identity, versions, and evidence population. The lower layers would still validate the repair and population semantics, but they could not prove which historical scan actually authored the plan. Lane E requires ambiguous identity/version/evidence provenance to fail closed, so the final strict path should not accept an unstamped or foreign plan.

Acceptance criteria remain deliberately repair/version contracts rather than scan-run identities. The recheck plan is different: it is execution intent derived from one historical evidence population, so this checkpoint binds that plan and each request to the authoritative historical scan.

## New pure/versioned contracts

Implementation: `scanner-api/app/nextgen_fix_verification_plan_lineage.py`

Versions:

- `fix_verification_plan_lineage_binding_v1_exact_historical_scan_id`
- `fix_verified_fixed_plan_scan_bound_observation_replay_v1_exact_historical_plan_lineage`
- `fix_regression_reopen_plan_scan_bound_observation_replay_v1_exact_historical_plan_lineage`

New helpers:

- `build_scan_bound_targeted_recheck_plan(...)`
- `verification_plan_lineage_integrity(...)`
- `strict_verified_fixed_transition_from_plan_scan_bound_observations(...)`
- `strict_regression_reopen_from_plan_scan_bound_observations(...)`

The existing `fix_verification_plan_v1` contract is not changed. The additive builder keeps that base version for compatibility and adds a separately versioned provenance envelope:

- `plan_lineage_version`
- exact top-level `source_scan_id`
- the same exact `source_scan_id` on every targeted request

If the caller-owned historical scan ID is missing, non-string, empty, or whitespace-normalized, the builder returns a blocked/non-complete plan rather than producing usable proof data.

## Fail-closed transport rules

`verification_plan_lineage_integrity(...)` treats every populated scan-id alias as a claim. On the plan and on each request:

1. the caller-owned `previous_scan_id` must be an exact non-empty string;
2. the base plan version must remain the supported verification-plan version;
3. the lineage-envelope version must be exact;
4. at least one source-scan claim must exist;
5. `scan_run_id`, `scan_id`, and `source_scan_id`, when present, must each be exact non-empty strings;
6. every present alias must equal the authoritative historical scan ID;
7. every targeted request must carry the same historical lineage.

Null, whitespace-normalized, conflicting, missing, or foreign aliases therefore become non-proof. The helper is pure and does not mutate the transported plan.

## Final strict replay behavior

The two new final wrappers require plan lineage first, then delegate to the existing scan-bound wrappers. This composes:

- exact historical plan provenance;
- exact historical/current scan lineage across proof-bearing evidence;
- exact scan-origin binding;
- historical repair identity/version binding;
- historical evidence-alias integrity;
- proving-value integrity;
- ready-plan envelope integrity;
- recomputed PASS/PARTIAL/FAIL/COULD_NOT_VERIFY evaluation;
- the unchanged historical `repair_verification_v3_contract_comparable` verified-fixed proof;
- strict regression-reopen semantics.

An unstamped legacy plan, a plan from another historical scan, or a plan/request with conflicting scan aliases cannot authorize `verified_fixed` and cannot reopen a regression. A disappeared required URL still reaches the existing evaluator as `COULD_NOT_VERIFY`; disappearance remains non-proof.

## Focused regressions

`scanner-api/tests/test_nextgen_fix_verification_plan_lineage.py` adds 14 deterministic tests covering:

1. exact plan/request stamping by the additive builder;
2. blocked output for a whitespace-normalized historical scan ID;
3. valid exact lineage without input mutation;
4. missing lineage-envelope version;
5. foreign top-level plan source scan;
6. a null source alias even when another alias matches;
7. missing request source lineage;
8. foreign request source lineage;
9. conflicting request scan aliases;
10. denial of an unbound legacy plan at the newest verified-fixed boundary;
11. positive verified-fixed replay for an exact plan + scan-bound PASS;
12. positive regression reopen for an exact plan + scan-bound FAIL;
13. denial of a plan bound to another historical scan;
14. disappeared required URL remains `COULD_NOT_VERIFY` under the newest final wrapper.

Expected focused Lane-E total after this checkpoint: **202 tests** (previous 188 + 14 plan-lineage regressions).

## Verification performed in this runtime

The new helper and test source pass `py_compile`. A hermetic composition harness exercising the exact new helper logic and stubbed existing scan-bound delegates passed **11/11** scenarios, including valid stamping, missing/foreign/null/conflicting plan/request lineage, invalid authoritative scan ID, final verified-fixed denial, positive verified-fixed delegation, positive regression delegation, and foreign-plan denial.

The full repository-native 202-test Lane-E gate is still required in an approved checkout/runner. This runtime cannot resolve `github.com` from the execution container, and the draft integration-target PR does not receive the normal `main`-targeted workflow trigger.

## Serialized integration handoff

After Agents A-D are integrated and the lane is transplanted, the serialized integrator should prefer `build_scan_bound_targeted_recheck_plan(...)` when creating any future targeted verification work. Obtain `previous_scan_id` only from authoritative historical ScanRun/crawl-scope lineage; never infer it from URL, timestamp, repair text, client input, or customer projection.

At consumption time, prefer the two plan+scan-bound final wrappers over accepting an unbound `fix_verification_plan_v1` transport. Carry the exact historical scan ID on the plan and every request, carry the exact current scan ID on current pages/evaluations/contracts/fixes, and preserve all existing comparability/authority gates independently.

No durable authority/persistence/customer projection, `run_scan`, global budgets, repair priority, Base44 schema, admission, release/deploy, worker configuration, IAM, credentials, production behavior, merge, or deployment change is part of this checkpoint.
