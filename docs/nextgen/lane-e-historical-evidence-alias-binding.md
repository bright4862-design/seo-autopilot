# Lane E — historical evidence alias binding hardening

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

## Gap closed

Historical compatibility intentionally gives evidence fields deterministic precedence: a non-empty `affected_pages` list is authoritative; otherwise `page_url` wins over `representative_page_url`. That remains unchanged for legacy reads and for the existing `repair_verification_v3_contract_comparable` comparator.

At a proof boundary, however, a populated lower-precedence alias must not be silently ignored when it contradicts the evidence population actually being verified. Before this hardening, a record could carry `affected_pages=["/a", "/b"]` plus `page_url="/c"`, or could omit the explicit population while carrying `page_url="/a"` and `representative_page_url="/b"`; the compatibility selector would pick one source and ignore the contradiction.

## New pure contract

`scanner-api/app/nextgen_fix_verification_historical_evidence_aliases.py` adds:

- `fix_verification_historical_evidence_alias_integrity_v1_exact_population_membership`
- `verification_historical_evidence_alias_integrity(...)`

Rules:

- proof-bearing URL aliases must already be exact non-empty strings;
- the published evidence URL-identity version must be explicit and supported;
- if `affected_pages` is non-empty, every populated fallback alias must resolve to a member of that explicit population;
- if `affected_pages` is absent/empty, all populated fallback aliases must resolve to the same evidence identity;
- malformed, unresolvable, foreign, or conflicting aliases fail closed;
- duplicates that resolve to the same evidence identity remain harmless redundancy, matching existing population deduplication semantics.

No network work is introduced.

## Final-boundary integration

`evaluate_verification_observations_historical_bound(...)` now requires the new alias-integrity proof after historical repair-identity integrity and before value-bound PASS/PARTIAL/FAIL evaluation. Its version is now:

- `fix_verification_historical_bound_observation_v3_exact_historical_evidence_aliases`

Both authority-facing pure replay helpers inherit the same protection and are versioned accordingly:

- `fix_verified_fixed_observation_replay_v6_exact_historical_evidence_alias_binding`
- `fix_regression_reopen_observation_replay_v6_exact_historical_evidence_alias_binding`

Thus a contradictory historical fallback alias can neither support a future `verified_fixed` proposal nor prove a regression reopening. It yields `COULD_NOT_VERIFY` / no reopen.

## Focused regressions

`scanner-api/tests/test_nextgen_fix_verification_historical_evidence_aliases.py` adds 10 deterministic cases:

1. fallback aliases that are members of an explicit affected population remain valid;
2. `page_url` outside the explicit population fails closed;
3. foreign `representative_page_url` outside the explicit population fails closed;
4. matching fallback aliases without an explicit population remain valid;
5. conflicting fallback aliases without an explicit population fail closed;
6. malformed `affected_pages` transport fails closed;
7. the historical-bound evaluator returns `COULD_NOT_VERIFY` for an ignored fallback conflict;
8. the historical-bound evaluator preserves PASS for consistent aliases;
9. strict verified-fixed replay denies contradictory historical fallback evidence;
10. strict regression-reopen replay denies contradictory historical fallback evidence even when current observations would otherwise prove FAIL.

Expected Lane-E focused total after this slice: **158 tests** (previous 148 + 10).

## Serialized integration handoff

The serialized integrator should pass the uncollapsed historical repair record into the final Lane-E replay helpers. Do not pre-normalize away `page_url`, `representative_page_url`, or `affected_pages`; contradictory aliases must remain visible so the pure integrity boundary can fail closed. Continue sourcing scan origins from authoritative historical/current scan or crawl-scope records.

No durable authority/persistence/customer projection, `run_scan`, global budgets, repair priority, Base44 schema, admission, release/deploy, worker configuration, IAM, credentials, or production behavior is changed here. Nothing in this lane should be merged or deployed directly.
