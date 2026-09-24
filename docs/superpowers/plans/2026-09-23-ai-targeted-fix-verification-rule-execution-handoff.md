# AI Layer Lane E — H1-4 originating-rule execution binding handoff

Status: additive Lane-E pure contract/test slice only. This checkpoint does not wire a customer endpoint, call a private worker, spend scheduler budget, execute a crawl, modify `run_scan`, alter Standard 150/V8, write authority or persistence, reopen a repair durably, change customer projection, modify schema/IAM/secrets, deploy, or touch production. No LLM/model call is permitted or performed.

## Why this slice exists

The prior strict Lane-E path bound the rule-evaluation receipt to the exact targeted execution window, scheduler receipts, recheck outcomes, current comparison contract, and exact `current_fixes` transport. One structural gap remained: the core `build_rule_evaluation_receipt()` derives `evaluated_evidence_keys` from the sealed plan, so that receipt alone does not prove that the originating deterministic rule actually ran against every exact page object produced by the protected targeted execution.

This slice closes that lane-owned structural gap without creating a second repair-truth engine. Final `PASS` / `PARTIAL` / `FAIL` / `COULD_NOT_VERIFY` still flows through the existing strict Lane-E stack and ultimately `repair_identity.compare_repair_runs()`.

## New contracts

`targeted_fix_verification_rule_execution_result_v1_exact_page_evidence` is one explicit per-page result emitted by the originating deterministic rule producer. An evaluated result is valid only when it carries:

- the exact targeted verification `plan_fingerprint`;
- the exact stable `repair_fingerprint`;
- the originating `rule_definition_version`, `comparison_profile_version`, and published evidence URL identity version;
- one exact planned `evidence_key`;
- the exact shared-scheduler `scheduler_evidence_ref` already bound to that recheck outcome;
- a SHA-256 fingerprint of the exact proof-bearing page object the rule evaluated;
- one strict deterministic target finding state: `finding_present` or `finding_absent`;
- `producer_contract = originating_deterministic_rule`;
- `model_calls_performed = false`.

Unknown fields, coercible values, a changed page fingerprint, a stale scheduler receipt, version drift, or model-backed execution fail closed.

`targeted_fix_verification_rule_execution_binding_v1_exact_execution_population` requires exactly one such evaluated result for every planned URL and no other URL. It reuses the existing stable repair identity matching helper to prove that the per-page `finding_present` / `finding_absent` declarations agree with the exact target repair population already supplied to the canonical comparator path. A matching current repair that expands outside the sealed repair set is rejected.

The binding fingerprints the complete rule-execution result population plus the already-existing execution-bound rule receipt. It does not itself decide whether the repair is fixed.

## Disappeared and unavailable URLs

A rule-execution result may be emitted only for `observed` targeted evidence. If a planned URL disappears, times out, is blocked, is challenged, is denied by robots, exhausts budget/deadline, or otherwise lacks comparable proof, Lane E must not create an `evaluated` originating-rule result for that URL.

A disappeared URL therefore remains non-proof. It cannot become `finding_absent`, cannot contribute to `verified_fixed`, and the repair remains `COULD_NOT_VERIFY`.

Robots/challenge and other evidence-integrity failures that still have a transport-level page object continue through the existing strict evidence gate and remain `COULD_NOT_VERIFY`; this binding does not weaken those checks.

## Trust boundary

`build_originating_rule_execution_result()` is a pure serializer and is **not authority by itself**. The serialized integrator must invoke it only inside the trusted producer for the same deterministic rule/version that created the originating repair, immediately after that rule evaluates the exact protected recheck page object. Do not construct these results in a client, endpoint handler, presentation layer, persistence reader, or from an arbitrary detached `current_fixes` payload.

If the originating deterministic rule cannot expose this producer seam without changing Standard 150, `run_scan`, authority/persistence, or protected-fetch semantics, stop and hand the requirement to the serialized integrator rather than weakening the contract.

## Serialized integration sequence

The intended shared integration sequence is:

1. authenticate the exact source/current scan context and one sealed stable repair through the existing owner-bound V8 authority path;
2. build the exact complete Lane-E bounded plan from that repair's sealed affected URL set;
3. take the existing shared scheduler preflight snapshot and pass the strict Lane-E budget-integrity gate;
4. execute only the planned URLs through the existing protected robots/SSRF/DNS/redirect/body/deadline path and existing shared scheduler;
5. capture the immediate postflight scheduler snapshot and one exact scheduler-bound recheck outcome per planned URL;
6. inside the originating deterministic rule producer, run the same rule/version against each exact observed page object and emit one `targeted_fix_verification_rule_execution_result_v1_exact_page_evidence` result;
7. build/validate `targeted_fix_verification_rule_execution_binding_v1_exact_execution_population`;
8. delegate unchanged through the existing rule-receipt/evidence-integrity Lane-E stack to `compare_repair_runs()` for repair truth;
9. let the serialized integrator own any durable `verified_fixed` transition, regression reopen write, customer projection, endpoint admission, or persistence operation.

No alternative comparator, URL normalizer, request budget, rule engine, or authority path should be introduced.

## Focused safety expectations

The new behavioral regressions cover canonical PASS/PARTIAL/FAIL preservation, regression reopening without historical mutation, missing/duplicate/outside-scope/foreign-host rule executions, plan/rule version drift, scheduler-receipt substitution, exact page-evidence substitution, finding-state contradiction against the canonical target repair population, type coercion, unknown-field smuggling, model-call prohibition, disappeared URL and timeout non-proof, robots/challenge fail-closed behavior, current repair identity conflict, matching-repair scope expansion, and non-serializable evidence.

## Remaining dependency

Lane E still depends on Rescan/Lane B and the serialized authority path for comparator-ready stable technical repair identity. Current persisted V8 fingerprints may be durable references while their explicit `repair_surface` and `remediation_family` remain provisional; those rows must stay `COULD_NOT_VERIFY` until an already-sealed stable source exists. Never synthesize stable identity from customer copy, categories, finding IDs, or the provisional fingerprint.

Current `main` at `3609acc1be5beda86b77e95115342798f043841f`
contains the source-type hardening reviewed in PR #351. Lane E now also pins
the release-blocking mixed transition: a stable historical `missing_h1` repair
plus a current repair carrying the same persisted fingerprint but no stable
technical identity stops at `COULD_NOT_VERIFY / current_fix_identity_conflict`,
both at the core evaluator and before execution-bound rule truth can be
consumed. Historical provisional rows remain unchanged; this regression does
not add producer identity or authorize runtime execution.

The customer endpoint, durable authority transition, persistence/customer projection, and protected runtime execution remain serialized-integrator ownership.
