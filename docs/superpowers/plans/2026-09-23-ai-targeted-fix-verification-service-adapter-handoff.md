# AI Layer Lane E — H1-4 Pure Service Adapter Handoff

Status: additive Lane-E pure adapter contract only. Do not merge or deploy from this lane. This checkpoint does not expose a customer endpoint, perform network I/O, reserve/spend scheduler budget, call a private worker, mutate authority/persistence/historical repairs, change Standard 150/V8 budgets, alter admission/release/schema/IAM, or project customer state.

## Refreshed baseline

- `main`: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`.
- Lane E branch before this slice: `agent/ai-fix-verification-20260923 @ 80c4a7310f4545a875c6bb572dab0edb0db69ad8`.
- Root `AGENTS.md` still requires production parity and preserves robots/SSRF/DNS/redirect/body/deadline and stable-repair-identity guardrails.
- `scanner-api/app/repair_identity.py` still owns `repair_identity_v2_technical` and `repair_verification_v3_contract_comparable`; `compare_repair_runs()` remains the only repair truth engine used by Lane E.
- `SharedCoverageProbeScheduler` remains the one finite follow-up request pool. Lane E only consumes its exact accounting snapshot through the existing strict budget-integrity helper.
- Latest refreshed Rescan dependency: `agent/ai-rescan-comparison-20260923 @ d231c588a4826b0cbb1aa34eb227385456c6c2f2`. Its handoff continues to fail closed when stable technical repair identity cannot be proved from sealed evidence.

Targeted verification is still not a customer feature.

## Slice implemented

This slice adds `scanner-api/app/targeted_fix_verification_service_adapter.py` with two versioned pure boundaries:

- `targeted_fix_verification_service_adapter_v1_pure_plan_budget_evidence`
- `targeted_fix_verification_prepared_v1_exact_plan_budget_snapshot`

### `prepare_targeted_fix_verification_service(...)`

The preparation step composes existing green Lane-E contracts only:

1. Builds the exact complete bounded plan from one already-authority-verified sealed repair.
2. Runs the strict shared-scheduler budget-integrity gate.
3. Binds the full plan, budget result, exact scheduler snapshot fingerprint, and no-side-effect execution contract into one deterministic prepared fingerprint.
4. Returns `state=ready` only if the complete sealed plan is ready and the existing shared scheduler has enough exact remaining capacity.

It performs no I/O and does not reserve budget. A ready envelope is a deterministic preflight receipt, not an authority seal or execution permit.

### `evaluate_prepared_targeted_fix_verification_service(...)`

The evaluation step:

1. validates the prepared envelope/version/fingerprint exactly;
2. requires the exact same captured scheduler snapshot and re-runs the existing strict budget-integrity gate;
3. rejects any plan/budget/snapshot substitution or mutation;
4. delegates evidence admission to `strict_evaluate_targeted_fix_verification(...)`;
5. therefore delegates actual fixed/still/came-back truth unchanged to `compare_repair_runs()`.

The adapter never synthesizes a rule-evaluation receipt. The serialized integrator must obtain that receipt only after running the same deterministic originating rule/evidence semantics for the complete targeted population.

## Verification states preserved

- `PASS`: only from complete safe re-observation where the existing comparator returns `verified_fixed` on every sealed URL.
- `PARTIAL`: only from a complete comparable mixture of canonical `verified_fixed` and `still_detected`/`came_back`.
- `FAIL`: only from canonical positive defect evidence.
- `COULD_NOT_VERIFY`: any plan/scope/version/identity/budget/scheduler/evidence/rule ambiguity, missing URL, robots/challenge/timeout failure, or incomplete rule receipt.

A disappeared URL remains non-proof and therefore `COULD_NOT_VERIFY`, never PASS.

Regression reopening remains evidence only: `reopen_regression=true` is surfaced only when the unchanged canonical comparator reports `came_back`. This adapter performs no historical mutation.

## Safety / abuse tests added

The new focused adapter suite covers:

- ready preflight binds exact plan + exact scheduler-budget snapshot;
- foreign-host selection is rejected;
- same-origin URL outside the sealed repair set is rejected;
- insufficient shared budget cannot become ready;
- deadline exhaustion cannot become ready;
- canonical PASS/PARTIAL/FAIL are preserved;
- verified-fixed reappearance preserves regression-reopen evidence without mutating the historical repair;
- disappeared planned URL => `COULD_NOT_VERIFY`;
- robots denial, challenge, and timeout => `COULD_NOT_VERIFY`;
- originating rule-version drift => `COULD_NOT_VERIFY`;
- prepared plan mutation => fail closed;
- scheduler snapshot substitution => fail closed;
- prepared budget mutation => fail closed;
- missing deterministic rule-evaluation receipt => `COULD_NOT_VERIFY`;
- every adapter result explicitly reports `side_effects_performed=false`.

## Shared integration handoff

Only the serialized integrator should wire this adapter:

1. Use the existing V8 authority reader to obtain one authoritative historical scan + sealed repair with stable technical identity.
2. Capture the existing `SharedCoverageProbeScheduler` summary.
3. Call `prepare_targeted_fix_verification_service(...)`.
4. Only if it returns `state=ready`, execute exactly the returned plan URLs through the existing shared scheduler and protected robots/SSRF/DNS/redirect/body/deadline path. The adapter itself never performs this execution.
5. Retain the exact preflight scheduler snapshot for the deterministic evaluation handoff. The real scheduler remains authoritative for actual permit spending before I/O.
6. Produce plan-bound observations from the protected fetch path.
7. Re-run the exact originating deterministic rule/evidence contract for every planned URL and create the existing complete-population rule receipt.
8. Call `evaluate_prepared_targeted_fix_verification_service(...)` with the same captured scheduler snapshot.
9. Durable persistence, authority transitions, customer projection, endpoint admission/rate policy, and regression-state writes remain integrator-owned.

Do not expose the pure adapter as a public endpoint without separate admission/authentication/entitlement work owned by the serialized integrator.

## Dependency / blocker

Lane E still depends on the Rescan/authority path supplying stable technical repair identity. The refreshed Rescan lane is at `d231c588a4826b0cbb1aa34eb227385456c6c2f2`; its latest change hardens verified-fixed integrity regression setup, and its handoff still records the production-shaped blocker that persisted FixItems can remain provisional without sealed `repair_surface` + `remediation_family`.

If that stable identity is absent or ambiguous, Lane E must remain `COULD_NOT_VERIFY`.

The second integration dependency is protected execution: only the existing shared scheduler/protected fetch path may perform network work. Lane E does not recreate it.

## Verification before branch update

The new adapter and test source syntax-compile locally. A hermetic composition harness covering the 14 new service-adapter scenarios passed `14/14`. Exact repository-native CI must still pass on the final branch SHA before any integrator consumes this slice.

## Next step

After exact-head repository CI is green, the next safe Lane-E task is review-only hardening of the adapter boundary against any CI/reviewer findings. Customer endpoint/service routing, durable writes, V8 projection, and production execution remain outside Lane E and should be handed to the serialized integrator.
