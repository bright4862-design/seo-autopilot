# AI Lane E — Targeted Fix Verification Execution Evidence Binding Handoff

Status: lane-owned pure contract only. Do not merge, deploy, or wire customer/production surfaces from this document.

## Scope

This slice adds `targeted_fix_verification_execution_evidence_v1_exact_scheduler_outcome_binding` on `agent/ai-fix-verification-20260923`.

The prior Lane-E execution-accounting layer proves that one exact sealed repair plan ran inside an unchanged `SharedCoverageProbeScheduler` budget window. This slice closes the next provenance gap: the deterministic `recheck_outcomes` supplied to repair comparison must now be tied one-for-one to the exact scheduler observations produced in that execution window.

It does not perform I/O, reserve requests, call workers, mutate authority/persistence/customer projection, alter Standard 150/V8, change `run_scan` or shared budgets, change robots/SSRF/DNS/redirect/body/deadline protections, or decide repair truth.

## Contract

`validate_targeted_verification_execution_evidence_binding(...)` first requires the existing execution-accounting contract to be valid. It then requires:

- exactly one scheduler observation and exactly one recheck outcome for every URL in the sealed targeted plan;
- the outcome to echo the scheduler observation's exact non-empty `evidence_ref` as `scheduler_evidence_ref`;
- scheduler `not_verified` to remain `not_verified` with the exact same reason and without page evidence;
- scheduler `pass`/`fail` fetch observations to map only to an `observed` recheck outcome;
- exact HTTP status agreement between scheduler observation and proof-bearing page evidence;
- a non-empty scheduler `final_url` that exactly remains the sealed planned evidence URL;
- the page evidence `final_url` to exactly match that scheduler final URL.

A redirect/moved/disappeared planned URL is therefore incomparable in this targeted-verification contract. It returns `COULD_NOT_VERIFY`; it is never proof that the originating repair was fixed.

`evaluate_execution_bound_targeted_fix_verification_service(...)` applies the binding and then delegates unchanged to the existing execution-accounting -> evidence-integrity -> comparator-backed Lane-E stack. `PASS`, `PARTIAL`, and `FAIL` still come only from existing `compare_repair_runs()` semantics.

## Safety properties covered

Focused regressions cover:

- canonical PASS preservation;
- canonical PARTIAL and FAIL preservation;
- verified-fixed reappearance emitting regression-reopen evidence without historical mutation;
- stale/mismatched or missing scheduler evidence refs;
- scheduler/outcome terminal-state mismatch;
- exact `not_verified` reason binding and timeout remaining `COULD_NOT_VERIFY`;
- scheduler/page HTTP-status mismatch;
- redirect/final-URL identity change remaining `COULD_NOT_VERIFY`;
- page/scheduler final-URL mismatch;
- missing planned outcome never inferred from a scheduler receipt;
- foreign-host/scope expansion remaining rejected by existing shared execution accounting;
- robots denial/challenge remaining `COULD_NOT_VERIFY`;
- rule-version drift remaining `COULD_NOT_VERIFY`;
- pure validation not mutating plans, scheduler summaries, or outcomes.

## Rescan dependency

Latest refreshed Rescan lane at authoring time: `agent/ai-rescan-comparison-20260923 @ a059ac83fb4f3f64b6dd7d0b9ae17502004a5053`.

Lane E still depends on the authoritative Rescan/owner path to supply a sealed repair with stable technical identity and comparable historical/current scan lineage. If stable repair identity cannot be proved, verification must remain `COULD_NOT_VERIFY`.

The Rescan lane's latest regression hardening also preserves the invariant that an explicit fingerprint override can support regression proof only when it exactly matches a stable expected historical repair identity and does not contradict the current canonical repair identity.

## Serialized integration sequence

The integrator, not Lane E, owns the shared wiring:

1. Resolve source/current scans and the sealed repair through the exact-owner V8 authority path.
2. Require stable repair identity and the originating deterministic rule/comparison/evidence versions.
3. Build the exact complete Lane-E targeted plan from the sealed repair affected URL set.
4. Capture the existing shared scheduler preflight snapshot and pass the Lane-E budget-integrity gate.
5. Execute only through the existing protected shared scheduler/fetch path.
6. Capture the immediate postflight scheduler snapshot.
7. For each planned URL, construct the recheck outcome from that exact scheduler observation and echo its exact `evidence_ref` as `scheduler_evidence_ref`.
8. Preserve the exact scheduler status and final URL in the proof-bearing page evidence. A changed final URL must remain incomparable.
9. Run the same originating deterministic rule/version across the complete observed population and produce the existing complete rule-evaluation receipt only inside that trusted producer.
10. Call `evaluate_execution_bound_targeted_fix_verification_service(...)`.
11. Treat `COULD_NOT_VERIFY` as non-proof. Durable `verified_fixed`, regression reopening, persistence, authority and customer projection remain integrator-owned transitions.

## Remaining blocker / next safe slice

No new Lane-E core blocker is introduced by this slice. Customer exposure still depends on authoritative stable repair identity plus serialized protected execution and persistence/customer projection wiring.

The next safe Lane-E hardening slice is to bind the deterministic rule-evaluation receipt to the exact execution-bound recheck evidence population. `build_rule_evaluation_receipt()` must remain a receipt produced only inside the originating deterministic rule producer; it is not independent execution authority and must never be accepted from a client or inferred from an arbitrary `current_fixes` list.
