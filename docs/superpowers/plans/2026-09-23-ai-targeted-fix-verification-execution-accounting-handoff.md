# AI Layer Lane E — H1-4 Shared Scheduler Execution Accounting Handoff

Status: additive Lane-E pure execution-accounting contract only. Do not merge or deploy from this lane. This checkpoint does not expose a customer endpoint, perform network I/O, reserve/spend scheduler budget, call a private worker, mutate authority/persistence/historical repairs, change Standard 150/V8 budgets, alter protected fetch behavior, admission/release/schema/IAM, or project customer state.

## Refreshed baseline

- `main`: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`.
- Lane E parent head: `agent/ai-fix-verification-20260923 @ aebe7ea65c5e6951b3dcf13fb72579d233910944`.
- `repair_identity.py` still owns `repair_identity_v2_technical` and `repair_verification_v3_contract_comparable`; `compare_repair_runs()` remains the repair-truth engine.
- `SharedCoverageProbeScheduler` still owns one finite follow-up request pool under `coverage_probe_scheduler_v1_shared_request_budget`. It spends a permit before I/O, counts timeouts/transport failures, reuses exact request URLs from cache, and emits bounded accounting/observation summaries.
- Latest refreshed Rescan dependency: `agent/ai-rescan-comparison-20260923 @ a059ac83fb4f3f64b6dd7d0b9ae17502004a5053`.
- The refreshed Rescan handoff continues to fail closed when stable technical repair identity (`repair_surface` + explicit `remediation_family`) cannot be proved from sealed evidence.

Targeted verification is still not a customer feature.

## Gap closed

The existing pure service adapter correctly bound planning to one exact preflight scheduler snapshot, but real protected execution necessarily changes scheduler accounting. Passing the preflight snapshot again proves preflight integrity only; passing the postflight snapshot to the old evaluator correctly fails its exact preflight fingerprint check.

This slice adds a separate post-execution proof boundary instead of weakening the preflight binding.

## Versioned contract

`scanner-api/app/targeted_fix_verification_execution_accounting.py` adds:

`targeted_fix_verification_execution_accounting_v1_exact_shared_scheduler_delta`

`validate_targeted_verification_execution_accounting(...)` proves only scheduler/execution accounting. It never decides whether a repair is fixed.

For one exact ready complete plan it requires:

1. both preflight and postflight summaries pass the existing strict shared-scheduler snapshot validator;
2. scheduler version and immutable budget envelope remain unchanged;
3. consumed/reused request counters never move backwards;
4. new-request consumption during the targeted window does not exceed the plan's already-declared worst-case bound;
5. targeted purpose selected/attempted/terminal accounting covers the complete planned population;
6. scheduler observation history is append-only and untruncated;
7. the execution window adds exactly one targeted scheduler observation for each exact planned URL;
8. no scheduler observation can select a foreign host, a same-origin URL outside the sealed set, or a duplicate planned identity.

Any ambiguity fails closed to `could_not_verify`.

`evaluate_executed_targeted_fix_verification_service(...)` then composes this execution receipt with the existing pure service adapter. It passes the original exact preflight snapshot back through the old adapter and delegates repair truth unchanged to the existing evidence-integrity evaluator and ultimately `compare_repair_runs()`.

## Truth semantics unchanged

- `PASS` still requires complete comparable re-observation and canonical `verified_fixed` truth.
- `PARTIAL` still requires a complete comparable mixed population.
- `FAIL` still requires positive deterministic defect evidence from the canonical comparator.
- `COULD_NOT_VERIFY` remains mandatory for missing/disappeared URLs, robots/challenge/timeout/budget failure, rule/profile/evidence-version drift, unstable identity, incomplete receipts, scheduler history ambiguity, or execution-accounting ambiguity.

A disappeared URL is never proof of a fix. Scheduler accounting can prove only that a bounded attempt occurred; it cannot turn missing page evidence into PASS.

Regression reopening remains evidence only. The pure wrapper does not mutate the historical repair.

## Rate / budget accounting proposal

The integrator should capture two adjacent summaries from the same existing `SharedCoverageProbeScheduler`:

1. immediately before targeted execution;
2. immediately after the complete targeted window.

Actual new request use is the monotonic `requests_consumed` delta. Cache reuse is reflected separately by `requests_reused`; reuse may reduce real outbound requests but never expands the sealed URL set, the complete-population requirement, or the declared new-request upper bound.

Do not create a second request pool. Do not change `coverage_probe_request_limit`, Standard 150, `run_scan`, or global frontier/request ceilings.

## Serialized integration sequence

Only the serialized integrator should wire this path:

1. Verify the historical scan and sealed repair using the existing authority reader.
2. Require stable technical repair identity. If unavailable, return `COULD_NOT_VERIFY`.
3. Capture the existing shared scheduler preflight summary.
4. Call `prepare_targeted_fix_verification_service(...)`.
5. If ready, execute only the returned exact plan URLs through the same existing shared scheduler and protected robots/SSRF/DNS/redirect/body/deadline path under purpose `targeted_fix_verification`.
6. Record one bounded scheduler terminal observation per planned URL; never omit blocked, timed-out, exhausted, or otherwise unverifiable attempts.
7. Capture the postflight summary immediately after the targeted window.
8. Re-run the exact originating deterministic rule/evidence semantics for every planned URL and build the complete existing rule-evaluation receipt.
9. Call `evaluate_executed_targeted_fix_verification_service(...)`.
10. Only the integrator may apply any durable authority/persistence/customer-projection or regression-state transition.

If scheduler samples truncate, history is rewritten, the URL population does not exactly match the sealed plan, or the pre/post accounting cannot be proven, stop at `COULD_NOT_VERIFY`.

## Safety / abuse regression coverage

The focused suite covers:

- valid bounded execution and canonical PASS;
- cache reuse reducing outbound requests without expanding scope;
- canonical PARTIAL and FAIL preservation;
- verified-fixed reappearance producing regression-reopen evidence without mutating history;
- missing scheduler observations;
- same-origin outside-set and foreign-host scheduler-observation smuggling;
- duplicate scheduler observations;
- truncated scheduler receipts;
- rewritten scheduler history;
- mutation of the immutable shared-budget envelope;
- backwards request counters;
- new-request consumption above the declared plan bound;
- disappeared URL after otherwise valid scheduler execution;
- robots denial, challenge, timeout, and rule-version drift remaining `COULD_NOT_VERIFY`;
- substituted preflight snapshot remaining fail closed.

## Dependency / blocker

Lane E still depends on the Rescan/authority path supplying canonical stable technical repair identity. The refreshed Rescan lane head is `a059ac83fb4f3f64b6dd7d0b9ae17502004a5053`; its handoff explicitly preserves `could_not_verify` for persisted repairs whose technical identity remains provisional.

The integration also depends on the serialized integrator owning the real protected scheduler/fetch execution and durable writes. Lane E intentionally provides only pure machine-testable boundaries.

## Next step

Run the focused Lane-E suite and broad scanner regressions on the exact branch head. If green, leave this contract review-only for the integrator. Any customer endpoint, V8/persistence wiring, authority transition, or production execution remains outside Lane E.
