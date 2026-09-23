# H1-1 repair identity source-type hardening

Base: `776e964b23b81a4759a590969ce981789a30d6d7` (AI integration).
Candidate only; shared V8/authority/persistence/UI/release files are untouched. Integration and deployment remain the serialized integrator's responsibility.

## Reproduced defect

`build_repair_identity()` used `_token()`/`str()` on technical rule, implementation surface and remediation family evidence. Objects, lists, booleans and numbers became non-empty strings and could establish a stable repair identity. A missing title repair with `repair_surface={"unexpected":"object"}`, an explicit string remediation family and a later usable/indexable page returned `verified_fixed` when the repair disappeared. This was reproduced against the real comparator, not a substitute.

Empty malformed preferred fields could also fall through Python `or` to a valid alias, concealing invalid evidence.

## Minimal correction

A narrow `_identity_field()` helper requires actual string identity evidence. Missing/null/empty-string fields may use existing aliases. A present non-string or whitespace-only preferred field cannot be rescued by another alias into a stable identity. Rule, surface and explicit remediation selection use this helper; the comparison engine and valid-string fingerprint algorithm remain unchanged.

Malformed inputs now stay provisional/insufficient and fail the existing stable-identity comparison gate. The fixture's valid technical fingerprint stays `449f1d37ab0f1cf0004e319d`. This does not supply missing historical identity or solve the remaining customer wiring. Do not rewrite historical snapshots or reseal old rows.

## Regression evidence

Initial RED: 24 failing malformed-input cases and 1 passing valid-string control. Independent direct reproduction returned `verified_fixed` for an object-valued surface before the fix.

Final focused GREEN: 153 passed across source-type regressions, repair identity, scan comparison/integrity and targeted verification/budget integrity. Includes 28 source-type cases/controls and a pinned valid-string fingerprint. No source fixture weakening.

Full-suite baseline/candidate comparison is recorded below after completion. A successful local focused gate is not exact-head CI, independent review or production acceptance. Before release the integrator must reconcile with the rescan lane, run generated release-contract checks and full CI, review compatibility, then follow exact-SHA deployment/acceptance discipline.

## Full-suite comparison

- Unmodified integration baseline: 29 failed, 2378 passed, 18 skipped, 3200 warnings in 36.63s.
- Final candidate: 29 failed, 2406 passed, 18 skipped, 3200 warnings in 31.45s.
- Exact failing test-ID sets match: 29 in each; no new failing test IDs. One inspected failure is missing local `jspdf`; not every failure is attributed to that dependency. The suite is not green and these existing/environment failures still need the repository CI gate.
- `git diff --check`: passed.
