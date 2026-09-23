# Lane E — execution-bound rule evaluation receipt handoff

Date: 2026-09-23  
Lane: AI Layer Lane E — Targeted Fix Verification  
Scope: additive pure verification contract only

## Slice

This slice adds `targeted_fix_verification_rule_receipt_binding_v1_exact_execution_bound_population`.

The existing targeted verification core already requires an exact sealed repair plan, shared-scheduler accounting, scheduler receipt binding, deterministic evidence admission, and the canonical `compare_repair_runs()` path for repair truth. This slice closes the remaining provenance gap between that exact protected execution and the deterministic rule-result population supplied to the comparison path.

The new receipt is an integrity/provenance artifact, not authority. It fingerprints the exact plan identity, preflight/postflight shared-scheduler snapshots, scheduler-bound recheck outcomes, current scan origin, originating comparison contract, canonical rule-evaluation receipt, and current deterministic fix population. It emits fingerprints/counts rather than raw page content.

## Required serialized integration order

1. Resolve one authoritative sealed repair with stable technical repair identity.
2. Build the existing exact bounded Lane-E recheck plan from that repair's complete affected URL set.
3. Use the existing shared bounded scheduler for preflight accounting.
4. Execute only through the existing protected robots/SSRF/DNS/redirect/body/deadline fetch path.
5. Capture the exact postflight scheduler snapshot and one bounded scheduler receipt per planned URL.
6. Bind recheck outcomes to those exact scheduler receipts with the existing Lane-E execution-evidence contract.
7. Run the same originating deterministic rule/version and evidence semantics over those execution-bound observations.
8. Inside that trusted deterministic-rule producer/integration seam, call `build_execution_bound_rule_evaluation_receipt(...)` over the exact rule-result population and exact execution inputs.
9. Pass the resulting receipt and the unchanged exact inputs to `evaluate_rule_receipt_bound_targeted_fix_verification_service(...)`.
10. Let the existing comparator-backed Lane-E stack decide `PASS`, `PARTIAL`, `FAIL`, or `COULD_NOT_VERIFY`.
11. Only the serialized integrator may map that pure result onto durable authority/persistence/customer projection.

## Fail-closed requirements

- Never accept a client-supplied receipt as proof of trust or authority. The evaluator only proves exact consistency by recomputation; producer trust belongs to the integrator seam.
- Never infer or manufacture stable repair identity.
- Never synthesize a page observation, scheduler receipt, or rule receipt for a disappeared/unobserved URL.
- A disappeared URL, redirect identity change, robots denial, challenge, timeout, budget failure, unsupported rule/evidence version, or any identity/evidence ambiguity remains `COULD_NOT_VERIFY`.
- Missing or extra execution outcomes, scheduler receipts, rule-result population changes, comparison-contract changes, or receipt tampering fail closed.
- An empty current-fix population can contribute to `PASS` only when every sealed affected URL was actually and comparably re-observed under the exact originating deterministic contract. Empty results never turn missing evidence into proof.
- `verified_fixed` and regression reopening remain governed by the existing comparison semantics; this receipt layer must not create a parallel truth engine.
- Historical scan/repair objects remain immutable in this lane.

## Ownership boundaries

Lane E does not:
- change global `run_scan` or Standard 150/V8 budgets;
- change scheduler request limits or protected fetch behavior;
- change robots/SSRF/DNS/redirect/body/deadline protections;
- write durable authority or persistence;
- update customer projection;
- expose a production/customer endpoint;
- call private workers directly;
- deploy, mutate Base44/GCP, or change schema/IAM/secrets.

## Integrator dependency

The latest Rescan lane remains the source of the canonical comparison/lineage semantics. Stable repair identity must be proved by the existing repair identity contract before any verified-fixed transition is considered. Persisted provisional fingerprints are not a substitute for stable technical identity.

## Acceptance for integration

The serialized integrator should consume this slice only after:
- exact Lane-E focused tests are green;
- exact branch-head broad relevant CI is green;
- the authoritative sealed repair input is stable;
- protected shared-scheduler execution is available without bypassing existing budgets/protections.

No production wiring is authorized by this handoff.
