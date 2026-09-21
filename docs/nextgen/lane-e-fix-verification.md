# Agent E — Fix Verification

Issue: #326  
Draft PR: #330  
Integration base: `nextgen/integration-20260921`

This lane implements only the pure Fix Verification planning/state layer defined in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Ownership boundary

Owned here:
- versioned machine-testable acceptance criteria;
- bounded targeted recheck plans;
- PASS / PARTIAL / FAIL / COULD_NOT_VERIFY evaluation;
- pure regression-reopen decisions;
- tests proving disappeared or incomparable evidence never becomes proof of repair.

Explicitly untouched:
- `scanner-api/app/scanner.py` / `run_scan` / global budgets;
- durable authority, seal, HMAC, persistence, or customer projection;
- repair priority or customer ranking;
- ScanRun schema or customer workflow state;
- admission, release, deployment, worker promotion, or production.

The current `verified_fixed` comparator remains authoritative and unchanged.

## Contracts implemented

Implementation: `scanner-api/app/nextgen_fix_verification.py`

Versions:
- `fix_acceptance_criterion_v1`
- `fix_verification_plan_v1`
- `fix_verification_result_v1`
- `fix_regression_reopen_v1`

### Acceptance criterion

A new NextGen criterion is `ready` only when the historical repair has:
- stable existing repair identity/fingerprint;
- explicit `rule_definition_version`;
- explicit `comparison_profile_version`;
- supported published `evidence_url_identity_version`.

Missing or ambiguous identity/version metadata blocks the criterion rather than guessing. This is additive: legacy `compare_repair_runs` behavior is not modified or backfilled.

The criterion is deterministic and carries a stable `criterion_id`. Its predicate is declarative: `defect_detected == false`, with `requires_actual_re_evaluation=true` over the complete required evidence population.

### Targeted recheck plan

`build_targeted_recheck_plan(...)` emits only pure data. It performs no fetches.

Each request names:
- original URL;
- published evidence key;
- stable repair fingerprint;
- rule/criterion identity;
- observations required from later execution: HTTP status, content type, indexability, and explicit rule-predicate evaluation.

The plan is hard-bounded to 150 evidence members. If a repair population exceeds the bound, the plan becomes `bounded_incomplete`; that state is useful for orchestration but can never yield PASS. Unresolvable/ambiguous prior URLs block verification.

### Plan integrity / historical population binding

The evaluator does not trust caller-supplied plan completeness flags by themselves. Before any PASS/PARTIAL/FAIL outcome it independently rebuilds the acceptance criterion and full historical evidence-key population from the historical repair under the declared published URL-identity contract.

A plan fails closed to `COULD_NOT_VERIFY` when:
- `population_count` is malformed or differs from the historical population;
- any historical evidence member is missing from `requests`;
- requests contain missing/duplicate/unexpected evidence keys;
- a request URL does not derive to its declared evidence key;
- criterion, rule, fingerprint, identity version, rule-definition version, comparison-profile version, or URL-identity version is tampered or inconsistent;
- a request omits or alters the required observation contract.

This makes plan objects untrusted declarative inputs rather than proof that the full repair population was actually requested.

### Result state machine

`evaluate_verification_plan(...)` reuses the existing repair comparability rules and fails closed.

- `PASS`: every required URL is re-observed in a comparable eligible state, every rule-evaluation row matches criterion/fingerprint/version identity, every predicate is actually re-evaluated, and the defect is absent everywhere.
- `PARTIAL`: the full population is comparable/evaluated, some members pass and some still detect the defect. `unresolved_scope` contains the exact remaining evidence keys.
- `FAIL`: the comparable/evaluated population still detects the defect with no resolved members.
- `COULD_NOT_VERIFY`: any missing page, disappeared URL, redirect/error/non-HTML/non-indexable ineligible evidence, missing predicate evaluation, duplicate/ambiguous evidence, identity mismatch, version mismatch, blocked criterion, incomplete/tampered plan population, or incomplete bounded population.

A URL disappearing from the crawl is therefore never proof of a fix.

### Existing `verified_fixed` semantics are preserved

`verified_fixed_transition_allowed(...)` is intentionally conjunctive. A future serialized integrator may map a NextGen result to durable `verified_fixed` only when:

1. the NextGen result is `PASS`; **and**
2. the existing `compare_repair_runs(...)` result independently remains `verified_fixed`.

This lane does not replace, weaken, or mutate the current comparator.

### Regression reopening

`regression_reopen_decision(...)` returns pure data only.

A previously PASS / `verified_fixed` repair is eligible to reopen only when the same stable repair fingerprint later produces `FAIL` or `PARTIAL`. `COULD_NOT_VERIFY` never proves a regression and never reopens by itself. For PARTIAL, `reopen_scope` is the exact unresolved evidence population.

No workflow state or durable row is changed by the helper.

## Behavioral regression coverage

`scanner-api/tests/test_nextgen_fix_verification.py` covers 18 focused cases:

1. deterministic versioned criterion identity;
2. missing stable identity/version metadata blocks planning;
3. hard 150-member bound and incomplete-population fail-closed behavior;
4. PASS requires complete re-observation and explicit predicate re-evaluation;
5. disappeared URL => COULD_NOT_VERIFY;
6. still detected everywhere => FAIL;
7. mixed resolution => PARTIAL with exact unresolved scope;
8. HTTP 404 evidence cannot verify a fix;
9. non-indexable search-facing evidence cannot verify a fix;
10. changed rule definition version fails closed;
11. duplicate/ambiguous rule evaluation fails closed;
12. NextGen PASS cannot replace the existing `verified_fixed` gate;
13. proven PARTIAL regression produces a pure reopen decision;
14. COULD_NOT_VERIFY does not reopen a previously verified repair;
15. removing a historical population member from an otherwise-ready plan => COULD_NOT_VERIFY;
16. malformed `population_count` fails closed without raising;
17. tampered acceptance-criterion identity => COULD_NOT_VERIFY;
18. request URL/evidence-key identity mismatch => COULD_NOT_VERIFY.

Focused isolated contract execution passed 18/18, and `py_compile` passed, after the population-integrity hardening. The isolated harness uses faithful local stubs for imported repair identity/coverage behavior; it is not a claim of full repository scanner regression execution. Full scanner-suite execution remains an integration-environment/serialized-integrator gate rather than weakening or retargeting repository CI.

## Serialized integration hook

The later integrator should keep all durable/shared wiring outside this lane and make the smallest possible patch:

1. Select a historical stable repair for targeted verification only after its versioned comparison metadata is available.
2. Call `build_targeted_recheck_plan(...)` to obtain bounded declarative evidence requests.
3. Execute those requests only through the existing safe crawler/browser/rule-evaluation machinery and its existing budgets; do not introduce a second fetch path.
4. Feed the resulting current pages + explicit per-page rule evaluations + current comparison contract into `evaluate_verification_plan(...)`.
5. Independently run the existing `compare_repair_runs(...)` comparator.
6. Allow durable `verified_fixed` only through `verified_fixed_transition_allowed(new_result, legacy_result)`.
7. If a previously verified fingerprint later returns FAIL/PARTIAL, use `regression_reopen_decision(...)` as proposed data only; the serialized authority/persistence layer must own any actual workflow/persistence mutation.
8. If verification plans/results are persisted later, add them conditionally under a new signed versioned repair sub-contract while preserving byte-for-byte historical reconstruction. Do not backfill old scans.

## Risks / fail-closed decisions

- Historical rows without explicit rule/profile/URL-identity versions are not silently upgraded into the NextGen path.
- More than 150 required evidence members cannot produce PASS until the integrator defines an approved complete-population strategy inside existing global budgets.
- Plan metadata is treated as untrusted input and independently rebound to the historical repair before evaluation.
- Extra, missing, malformed or duplicate evidence is treated conservatively; ambiguous identity cannot prove a repair.
- If historical and current origin context do not permit the same published evidence keys to be reconstructed, evaluation fails closed rather than assuming equivalence.
- No customer-facing state should consume PASS/PARTIAL/FAIL directly until authority/persistence and projection changes are separately reviewed and signed.

## Rollback

This lane is additive and unwired. Rollback is deletion of:
- `scanner-api/app/nextgen_fix_verification.py`
- `scanner-api/tests/test_nextgen_fix_verification.py`

plus restoration of this handoff document. No persisted data, production configuration, or customer state needs reversal.
