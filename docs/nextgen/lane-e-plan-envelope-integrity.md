# Lane E — targeted recheck plan envelope integrity

This slice adds `fix_verification_plan_envelope_integrity_v1_exact_ready_invariants` as a pure fail-closed boundary over the existing `fix_verification_plan_v1` contract.

The core evaluator already binds request identities to the historical repair population. The new boundary covers the plan's own readiness metadata so contradictory transport cannot be ignored: a plan marked `ready` must have `population_complete is True`, empty plan and criterion blockers, zero invalid and omitted population, exact integer counts and limits, request count equal to population count, a supported ready criterion, and a declared population that fits inside the bounded recheck limit.

The final positive replay is now `fix_verified_fixed_observation_replay_v7_exact_plan_envelope_invariants`, and the final regression replay is `fix_regression_reopen_observation_replay_v7_exact_plan_envelope_invariants`. Both reject an invalid plan envelope before current evidence can become either `verified_fixed` proof or regression-reopen proof. This does not alter `repair_verification_v3_contract_comparable`, historical reconstruction, persistence, customer projection, `run_scan`, budgets, admission, release/deploy, or production behavior.

Focused regressions add 15 cases: generated-plan validity; unsupported plan/criterion versions; non-ready plan/criterion state; exact `population_complete`; plan/criterion blocker contradictions; invalid/omitted population contradictions; boolean/coerced max limits; population-over-limit; request-count mismatch; and both final replay paths failing closed on contradictory ready-plan metadata.

Serialized integration guidance: preserve the full uncollapsed targeted-plan envelope. Do not rebuild or normalize away `state`, `population_complete`, `blockers`, `population_count`, `invalid_population_count`, `omitted_population_count`, `max_recheck_urls`, `requests`, or criterion readiness/blockers before Lane E verification. Any contradiction is non-proof and must remain `COULD_NOT_VERIFY`/denied at the durable wiring boundary.
