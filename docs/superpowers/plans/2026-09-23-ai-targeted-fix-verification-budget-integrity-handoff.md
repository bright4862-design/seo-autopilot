# AI Lane E — Targeted Fix Verification budget-integrity handoff

Checkpoint date: 2026-09-23

## Scope

This checkpoint is an additive, pure-contract hardening slice for H1-4 targeted repair verification. It does **not** execute probes, reserve budget, mutate scan/customer state, change Standard 150 limits, or alter the existing shared scheduler.

The implementation is intentionally layered on top of the existing Lane-E verification core and the existing `SharedCoverageProbeScheduler` contract. It does not create a second request pool or a parallel PASS/PARTIAL/FAIL engine.

## Exact implementation checkpoint before this documentation commit

- branch: `agent/ai-fix-verification-20260923`
- code/test head: `5eb962d46460e886e4c69ec4b7189b50e217e3dd`
- production baseline refreshed from `main`: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`
- latest Rescan Agent branch refreshed: `agent/ai-rescan-comparison-20260923` @ `9f2cc47be649d96094d8eb0637954158fdde6ba1`

## Added contract

`scanner-api/app/targeted_fix_verification_budget_integrity.py` adds:

- `TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION = "targeted_fix_verification_budget_integrity_v1_exact_shared_scheduler_snapshot"`
- `validate_shared_scheduler_snapshot(...)`
- `strict_targeted_verification_budget_proposal(...)`

The strict proposal performs two fail-closed gates before delegating the final fit/deadline/budget decision to the existing `targeted_verification_budget_proposal(...)` helper.

### 1. Exact sealed-plan transport gate

The plan must still match the sealed repair through the existing `_validate_plan_against_repair(...)` scope/identity/fingerprint checks. The additive integrity gate also requires:

- exact ready state, complete population, and no blockers;
- strict integer population counts (booleans and coercible values are rejected);
- selected population == sealed population == request count;
- declared targeted bound no larger than the existing `MAX_TARGETED_RECHECK_URLS`;
- exact canonical source origin;
- exact repair/rule/comparison/evidence identity strings;
- each request to retain the targeted-verification purpose, canonical URL/evidence key, same origin, stable repair identity, exact rule/profile/evidence versions, and uniqueness;
- the plan's shared-scheduler metadata to retain the current scheduler version, purpose, worst-case request count, shared-limit requirement, and cache-reuse semantics.

An attacker cannot turn a recomputed plan fingerprint into authority to add a same-origin URL outside the sealed repair population or move a request into another scheduler purpose.

### 2. Exact shared-scheduler snapshot gate

The supplied scheduler summary must use the existing `coverage_probe_scheduler_v1_shared_request_budget` version and exact, non-negative integer accounting fields:

- `configured_probe_requests`
- `shared_request_limit`
- `crawl_requests_consumed`
- `requests_consumed`
- `requests_reused`
- `requests_remaining`

`requests_remaining` must equal the same formula used by `SharedCoverageProbeScheduler`:

`min(configured_probe_requests - requests_consumed, shared_request_limit - crawl_requests_consumed - requests_consumed)`, each term floored at zero.

The helper rejects inconsistent accounting, impossible exhaustion flags, type coercion, and probe consumption above the configured probe allowance. Cache reuse is retained as an optimization only; it cannot be converted into future request capacity.

If the exact snapshot is valid, the existing Lane-E budget proposal remains the source of `fits` versus `could_not_verify` truth. Deadline exhaustion and insufficient shared request budget remain fail-closed.

## Verification states covered

This slice does not change the existing result-state evaluator. The Lane-E core continues to map deterministic comparison truth to:

- `PASS`
- `PARTIAL`
- `FAIL`
- `COULD_NOT_VERIFY`

The new budget integrity gate is pre-execution. Any invalid/ambiguous plan or scheduler snapshot returns `could_not_verify` and therefore cannot become proof for `PASS`.

The existing invariant is unchanged: a disappeared or unobserved URL is never proof of a repair. Missing/incomparable evidence cannot become PASS.

## Safety and abuse regressions

`scanner-api/tests/test_targeted_fix_verification_budget_integrity.py` adds coverage for:

- exact valid shared-scheduler accounting;
- inconsistent `requests_remaining`;
- bool/float/string/negative accounting coercion;
- requests consumed above configured allowance;
- impossible budget-exhausted metadata;
- coherent exhaustion remaining fail-closed;
- deadline exhaustion remaining fail-closed;
- cache reuse not creating future capacity;
- declared targeted-bound tampering;
- shared-scheduler purpose tampering;
- recomputed-fingerprint same-origin URL expansion outside the sealed repair set;
- request-purpose rewriting into another shared scheduler lane.

Local hermetic composition checks for this slice passed 12/12. The repository PR workflow for code/test head `5eb962d46460e886e4c69ec4b7189b50e217e3dd` completed successfully in both jobs: `Lint, typecheck, contract tests, and build` and `Scanner regression fixtures`.

## Dependency on Rescan lane

Lane E still depends on the Rescan/integration path for authoritative scan lineage and sealed repair inputs. The refreshed Rescan lane continues to delegate comparison truth to `compare_repair_runs(...)` and fails closed without stable repair identity/comparable contracts. Lane E must not synthesize missing repair identity, scan lineage, authority, or historical state.

This budget-integrity slice does not add or change Rescan persistence, scan comparison authority, customer projection, or historical scan records.

## Serialized integration handoff

The integrator should use the strict budget proposal only after it has an authoritative sealed repair and a bounded Lane-E recheck plan:

1. Build the Lane-E plan from exactly one sealed repair's affected URL population.
2. Obtain the summary from the **existing** `SharedCoverageProbeScheduler` instance that will own request accounting.
3. Call `strict_targeted_verification_budget_proposal(plan, sealed_repair, scheduler.summary())` before scheduling any verification probe.
4. Treat every `could_not_verify` result as non-proof; do not execute a fallback path that invents another budget or silently enlarges scope.
5. For actual probing, continue to use the existing shared scheduler/protected fetch path with purpose `targeted_fix_verification`. Do not call a private worker directly and do not create a Lane-E-specific request pool.
6. After deterministic page/rule evidence is collected, feed it into the existing Lane-E evaluator, which delegates fixed/still-detected/came-back truth to the existing repair comparison semantics.
7. Keep durable authority/persistence/customer projection changes in the serialized integrator, not in Lane E.

## Blocker / next step

No Lane-E core blocker is introduced by this slice. Customer exposure is intentionally blocked on serialized integration of authoritative scan/repair lineage, the shared protected probe execution path, and durable/customer projection wiring owned outside this lane.

Next safe Lane-E step: review the existing core for any remaining pure proof-envelope ambiguity around scheduler execution receipts or deterministic rule-evidence completeness. Add an endpoint/service adapter only after the pure core remains green; do not wire production or customer persistence from this branch.
