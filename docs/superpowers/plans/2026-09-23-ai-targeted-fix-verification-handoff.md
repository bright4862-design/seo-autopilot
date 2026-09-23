# AI Layer Lane E — H1-4 Targeted Fix Verification handoff

Status: lane-owned pure verification contracts only. No customer endpoint, production worker call, persistence mutation, authority/seal change, Standard-150 budget change, deployment, admission, schema, IAM, or customer projection is authorized by this lane.

## Refreshed baseline

- Source baseline: `main` at `c1080d75f7d1aacd748e74009be7a6c15aa40a93`.
- Lane branch: `agent/ai-fix-verification-20260923`.
- Existing truth source: `repair_identity.compare_repair_runs()` / `repair_verification_v3_contract_comparable`.
- Existing published URL evidence identity: `evidence_url_identity_v2_published_route`.
- Existing follow-up request accounting: `coverage_probe_scheduler_v1_shared_request_budget`.
- Latest Rescan Agent dependency refreshed from `agent/ai-rescan-comparison-20260923` at `9f2cc47be649d96094d8eb0637954158fdde6ba1`.

The current production/customer path does not expose targeted repair verification. This lane does not change that.

## Implemented H1-4 contracts

`scanner-api/app/targeted_fix_verification.py` adds pure, versioned helpers:

1. `targeted_fix_verification_criteria_v1_compare_repair_runs`
   - accepts exactly one already-authority-verified sealed repair plus source scan identity/origin;
   - requires stable technical repair identity, explicit originating rule-definition/comparison-profile versions, and published URL identity semantics;
   - freezes the complete sealed affected-URL evidence set;
   - declares machine-testable PASS/PARTIAL/FAIL/COULD_NOT_VERIFY acceptance semantics.

2. `targeted_fix_verification_plan_v1_sealed_repair_scope`
   - creates requests only from that sealed URL set;
   - rejects foreign-origin URLs, same-origin URLs outside the sealed set, duplicates, unresolved URL identities, and malformed selection transport;
   - never salvages an allowed subset from an abusive request;
   - never silently truncates an oversized repair into a smaller population that could later produce a false PASS;
   - hard-bounds automatic targeted population to the current shared scheduler's maximum follow-up allowance (18), while the real shared scheduler remains the execution-time authority.

3. `targeted_fix_verification_budget_v1_shared_scheduler`
   - is a proposal/check only, not a second request pool;
   - requires the existing shared scheduler summary/version;
   - compares the plan's worst-case new request count with the scheduler's `requests_remaining`;
   - deadline/budget exhaustion remains `could_not_verify`;
   - preserves existing scheduler semantics that a permit is spent before I/O and cache reuse may reduce actual requests.

4. `targeted_fix_verification_rule_receipt_v1_complete_population`
   - binds deterministic originating-rule output to the exact plan fingerprint, versions, complete evaluated URL population, and exact current-fix transport fingerprint;
   - prevents a bare/truncated `current_fixes=[]` value from being treated as sufficient absence evidence.
   - The serialized integrator must only create this receipt after the existing deterministic rule producer has evaluated the full targeted population. The helper is not an authority seal and does not prove producer execution by itself.

5. `targeted_fix_verification_result_v1_compare_repair_runs`
   - delegates the actual per-URL repair truth to existing `compare_repair_runs()`; it does not create a competing defect/fix engine;
   - maps canonical `verified_fixed` -> PASS and `still_detected`/`came_back` -> FAIL per URL;
   - aggregates all PASS -> PASS, all FAIL -> FAIL, and a fully comparable mix -> PARTIAL;
   - any comparator unknown, missing observation, failed/blocked/challenged fetch, robots denial, timeout, deadline/budget exhaustion, rule/profile drift, evidence identity ambiguity, origin mismatch, plan tamper, incomplete rule receipt, or scope ambiguity -> COULD_NOT_VERIFY;
   - an unobserved/disappeared URL is always COULD_NOT_VERIFY, never PASS;
   - returns `reopen_regression=true` only when the unchanged canonical comparator reports `came_back`; it does not mutate historical repair rows.

## Safety / abuse invariants

Focused regressions prove:

- a caller cannot add a foreign host;
- a caller cannot add a same-host path outside the sealed repair set;
- duplicate selection is rejected rather than deduped into a valid-looking request;
- a subset cannot be elevated into an authoritative full-repair verification;
- an oversized repair is not auto-truncated;
- extra or duplicate execution observations are rejected;
- observed page identity must exactly match the planned evidence key;
- a matching current repair cannot expand beyond the historical sealed repair scope;
- persisted/current technical identity conflicts fail closed only when the row claims to be the target repair; unrelated provisional persistence rows do not poison the target;
- plan transport tampering fails fingerprint validation;
- robots/challenge/rate-limit/timeout/request-budget/deadline uncertainty is never PASS;
- a disappeared URL is never evidence that a repair succeeded.

## Rescan Agent dependency

Lane B's latest H1-1 handoff remains the cross-scan dependency. It already delegates fixed/still-detected/came-back/could-not-verify truth to `compare_repair_runs()` and binds scan comparison to upstream authority receipts. Lane E must consume the same serialized source/current scan lineage and existing verified authority receipts when integrated; it must not invent a parallel scan-authority path.

A current integration blocker from the Rescan lane is intentionally preserved: production-shaped persisted FixItems may carry durable `repair_fingerprint` continuity while still having `repair_identity_state=provisional`, `repair_identity_stable=false`, and no sealed repair surface/remediation family. Targeted verification must remain COULD_NOT_VERIFY for those rows unless the serialized integrator can source the existing canonical stable technical identity from already sealed evidence. This lane does not change schema/persistence/authority to manufacture that identity.

## Serialized integration handoff

Only the integrator should wire execution:

1. Use the existing V8 authority reader to verify the historical scan and selected repair without mutating it.
2. Supply the sealed repair, exact source scan id, and authoritative scan origin to `build_targeted_recheck_plan()`.
3. Register only the returned ready-plan URLs with the existing hardened shared request/scheduler path. Do not call a private worker directly and do not create a new request pool.
4. Preserve the existing robots, DNS/SSRF, redirect, decoded-body, deadline, challenge/rate-limit and request-accounting protections. Translate any non-verifiable execution state to a plan-bound `not_verified` observation.
5. Run the same deterministic originating rule/evidence semantics for every planned URL and only then issue the complete-population rule evaluation receipt.
6. Call `evaluate_targeted_fix_verification()` with exact current scan origin/contract, complete plan-bound observations, current rule output, and the receipt.
7. Persistence of PASS/PARTIAL/FAIL/COULD_NOT_VERIFY, customer projection, regression reopening writes, entitlement/rate policy, and any public endpoint remain serialized integrator-owned changes.

No endpoint/service adapter is added in this slice. The core contract is green in the hermetic focused harness and has also passed the repository-native CI suite through draft PR #340; execution wiring still remains serialized-integrator work.

## Verification performed in this lane run

- `python -m py_compile app/targeted_fix_verification.py`: passed in the local hermetic workspace.
- Focused H1-4 contract/abuse harness: **38 passed**.
- The focused harness exercises the branch module against local semantic stubs matching the current `repair_identity`, published evidence identity, and shared scheduler contracts. It is not reported as repository-native CI.
- Repository-native CI was exercised through draft PR #340 against the lane branch. Run 2825 completed both `Scanner regression fixtures` and `Lint, typecheck, contract tests, and build` successfully, including the real Python scanner-api suite and production scanner image build. The subsequent documentation-only checkpoint is expected to receive the same PR gate and must be checked by exact head before integration.

## Next step

Let the serialized integrator review/cherry-pick the pure contract and wire a non-customer shadow adapter through the existing shared scheduler and existing authority reader. Any production/customer endpoint, persistence, V8 projection, entitlement/rate policy, or regression-reopen write remains out of lane.
