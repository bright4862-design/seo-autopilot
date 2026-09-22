# Lane E checkpoint — exact historical resolution-state binding

This Lane-E-only hardening closes a regression-reopen proof gap without changing legacy `repair_verification_v3_contract_comparable` behavior or any durable persistence/customer projection.

## Gap closed

The existing regression reopen helper intentionally preserves compatibility with historical records by selecting the first populated state alias from `state`, `verification_state`, `repair_verification_state`, or `status`, then accepting the existing resolved spellings (`PASS`, `verified_fixed`, `fixed`, `resolved`). That precedence is useful for historical reads but is too tolerant for a new authority-facing proof boundary: a record could carry `state=verified_fixed` and a contradictory `status=open`, or a whitespace/coercible value, and the first alias could hide the ambiguity.

## New contract

`fix_regression_reopen_source_state_integrity_v1_exact_historical_resolution_state`

The pure `verification_historical_resolution_state_integrity(...)` helper:

- requires every populated historical state alias to already be a non-empty exact string with no surrounding whitespace;
- preserves the existing resolved spellings and case-insensitive semantics;
- allows multiple legacy aliases only when they agree on the resolved/not-resolved classification;
- rejects conflicting resolved and unresolved aliases;
- rejects missing, whitespace-normalized, or non-string state proof;
- performs no persistence, projection, network, admission, release, deploy, or production work.

The final observation replay is versioned as `fix_regression_reopen_observation_replay_v5_exact_historical_resolution_state`. Before current FAIL/PARTIAL observations can reopen a repair, the historical record must now prove an exact, non-conflicting resolved state. Ambiguous historical state fails closed before recomputation and is surfaced as `COULD_NOT_VERIFY`/`should_reopen=False` at this pure decision boundary.

## Behavioral coverage

New focused regressions cover:

1. exact `verified_fixed` resolution proof;
2. coexistence of the existing `PASS` / `verified_fixed` / `fixed` / `resolved` spellings;
3. existing case-insensitive `PASS` semantics;
4. resolved-vs-open alias conflict;
5. whitespace-padded state rejection;
6. non-string state rejection;
7. missing historical resolution-state rejection;
8. exact non-resolved transport remaining non-authoritative;
9. input immutability;
10. final replay denial on conflicting aliases;
11. final replay denial on whitespace-normalized state;
12. final replay preservation of a real FAIL reopen when all historical aliases agree that the repair was resolved.

Expected focused Lane-E total after this slice: **148 tests** (previous 136 + 12 new tests).

## Serialized integration handoff

For a future durable regression reopen, call `strict_regression_reopen_from_observations(...)` only with the authoritative historical repair record and authoritative scan-origin/current observation inputs. Do not pre-normalize or collapse historical state aliases before Lane E. If historical state aliases conflict or cannot establish a prior resolved state, do not reopen and do not project a regression; retain the fail-closed result for integrator review.

No `run_scan`, global budgets, repair priority, authority/persistence/customer projection, Base44 schema, admission, release/deploy, worker configuration, IAM, credentials, or production behavior is changed by this checkpoint.
