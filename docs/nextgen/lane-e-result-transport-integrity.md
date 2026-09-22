# Lane E — exact terminal verification-result transport

Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint is additive Lane-E-only hardening. It does not change `repair_verification_v3_contract_comparable`, durable authority/persistence, customer projection, `run_scan`, global budgets, admission, release/deploy, or production behavior.

## Problem closed

The existing result-level compatibility helpers intentionally normalize some transported strings. For example, terminal state and identity fields are cleaned before comparison, and the legacy verified-fixed consumer normalizes comparator state/contract strings. That compatibility remains useful for historical reads, but ambiguous transport must not become NextGen proof.

A transported value such as `state=" PASS "`, `criterion_id=" <id> "`, legacy `state=" verified_fixed "`, or `comparison_contract_state=" compatible "` is now rejected by a new pure strict boundary before it can authorize verified-fixed or regression reopening.

## New contracts

`fix_verification_result_transport_integrity_v1_exact_terminal_transport`

Requires:

- exact supported `fix_verification_result_v1` version;
- exact uppercase terminal state: `PASS`, `PARTIAL`, `FAIL`, or `COULD_NOT_VERIFY`;
- exact non-empty `repair_fingerprint` and `criterion_id` strings with no surrounding whitespace;
- strict non-boolean integer population counts;
- exact, duplicate-free resolved/unresolved evidence identities;
- exact machine-readable `unverifiable_scope` entries when present;
- successful delegation to the existing structural `verification_result_integrity` contract.

`COULD_NOT_VERIFY` remains a valid terminal transport state but is explicitly non-proving.

`fix_verified_fixed_legacy_comparison_transport_integrity_v1_exact_transport`

Requires the existing comparator result to carry exact `repair_verification_v3_contract_comparable` version, exact `state="verified_fixed"`, exact `comparison_contract_state="compatible"`, and strict population-count transport. This does not replace or loosen the existing comparator; the existing dual-proof transition still runs afterward.

New wrappers:

- `fix_verified_fixed_result_transport_replay_v1_exact_terminal_transport`
- `fix_regression_reopen_result_transport_replay_v1_exact_terminal_transport`

The regression wrapper also requires the previously added exact historical resolution-state integrity check before delegating to the existing regression decision.

## Safety semantics

- Normalization is never proof.
- Ambiguous/malformed terminal identity, state, count, scope, or legacy comparator transport fails closed to `COULD_NOT_VERIFY` / no transition.
- A disappeared required URL remains non-proof. An exact `COULD_NOT_VERIFY` result carrying `required_page_not_observed` remains non-proving and cannot reopen or verify a repair.
- Existing verified-fixed comparability behavior is unchanged; these are additive strict consumer boundaries.

## Focused regressions

`scanner-api/tests/test_nextgen_fix_verification_result_transport.py` adds 17 cases covering:

- exact PASS transport;
- whitespace and lowercase state rejection;
- whitespace identity rejection;
- boolean count rejection;
- duplicate evidence-scope rejection;
- malformed unverifiable evidence rejection;
- exact non-proving `COULD_NOT_VERIFY`;
- exact legacy verified-fixed transport;
- normalized legacy state/contract rejection;
- positive exact verified-fixed wrapper;
- result/legacy transport denial paths;
- positive exact FAIL regression reopening;
- conflicting historical resolution aliases;
- disappeared-required-URL non-proof.

Expected focused Lane-E total after this slice: **219 tests** (previous 202 + 17).

## Verification in this runtime

Repository checkout is unavailable because the runtime cannot resolve `github.com`. Before publication:

- new helper and test source were syntax-compiled locally;
- an isolated hermetic harness for the exact helper/wrapper logic passed **12/12** scenarios.

Do not claim the full **219/219** branch-native pytest gate until it runs against an exact checkout/head.

## Serialized integration handoff

For any future result-level persistence/authority consumer:

1. Recompute verification from observations through the newest plan+scan-bound wrappers whenever possible; do not trust client-supplied result objects.
2. If a transported terminal result must cross a serialized boundary, require `verification_result_transport_integrity(...)` before existing historical binding/comparability checks.
3. For durable `verified_fixed`, also require `legacy_verified_fixed_transport_integrity(...)`, then retain the existing dual-proof comparator gate.
4. For regression reopening, require exact historical resolution-state integrity and the strict result transport wrapper before any persistence mutation.
5. Treat every failure as `COULD_NOT_VERIFY` / no durable transition.
6. Persist/project nothing unless all existing authority, comparability, lineage, and persistence gates independently pass.
