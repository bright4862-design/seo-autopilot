# Agent E — exact transported scope identity hardening

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint remains inside the Agent E pure-helper/test/docs ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Review gap closed

The previous population binder compared transported `resolved_scope` + `unresolved_scope` to the historical evidence population only after `_clean()` coercion/whitespace trimming. A malformed proving result could therefore carry a whitespace-padded evidence key such as `" https://example.com/a "`, normalize to the historical key, and incorrectly satisfy the exact-population invariant. Non-string values were also string-coerced before validation.

For proving PASS / PARTIAL / FAIL transports, evidence-key identity is now exact and fail-closed:

- every scope member must already be a `str`;
- every member must be non-empty after whitespace inspection;
- surrounding whitespace is rejected rather than normalized;
- dictionary/numeric/other non-string members are rejected rather than coerced;
- duplicates remain rejected;
- the historical-population comparison uses the raw validated scope strings, with no `str(...)` coercion or trimming.

A malformed scope therefore becomes effective `COULD_NOT_VERIFY`; it cannot prove PASS, cannot reopen a regression, and cannot authorize the strict verified-fixed transition.

## Versioned strict-consumer contracts

This hardening publishes new strict-consumer versions:

- `fix_verification_result_integrity_v2_exact_scope_identity`
- `fix_verification_result_binding_v3_exact_scope_identity`
- `fix_regression_reopen_v5_exact_scope_identity`
- `fix_verified_fixed_transition_v5_exact_scope_identity`

The transported `fix_verification_result_v1` envelope and existing legacy `repair_verification_v3_contract_comparable` comparator contract remain unchanged.

## Added deterministic regressions

Six pytest cases were added through two three-case parameterized tests:

1. whitespace-padded evidence key fails integrity, binding, and regression reopening;
2. dictionary evidence member fails integrity, binding, and regression reopening;
3. numeric evidence member fails integrity, binding, and regression reopening;
4. whitespace-padded PASS cannot prove the strict verified-fixed transition;
5. dictionary-member PASS cannot prove the strict verified-fixed transition;
6. numeric-member PASS cannot prove the strict verified-fixed transition.

Lane E now contains **57 focused tests** total:

- 18 core verification tests;
- 20 integrity/binding/reopen tests;
- 19 strict verified-fixed transition tests.

A small hermetic exact-scope harness executed the new `_scope` rules over valid, whitespace-padded, dictionary, numeric, whitespace-only, duplicate, and non-list inputs: **7/7 passed**.

## Exact repository gate still required

This automation runtime still cannot resolve `github.com` from its local container, so the exact branch cannot be materialized for repository-native pytest. Do not represent the full 57-test exact-head suite as green until an approved checkout/runner executes:

```bash
cd scanner-api
PYTHONPATH=. python -m pytest -q \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py
python -m py_compile \
  app/nextgen_fix_verification.py \
  app/nextgen_fix_verification_integrity.py \
  app/nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py
```

## Serialized integration handoff

After A–D integrate in order and their gates remain green, the serialized integrator should continue to:

1. obtain historical scan origin only from authoritative scan/crawl-scope metadata;
2. pass it as `previous_scan_origin` when historical affected URLs are root-relative;
3. obtain the legacy verified-fixed comparison only from existing `compare_repair_runs(...)`;
4. treat malformed scope identity, population mismatch, unresolved identity/version, or missing evidence as `COULD_NOT_VERIFY`;
5. keep durable authority/persistence/customer projection wiring outside this lane.

No `run_scan`, global budgets, repair priority, durable authority/persistence/customer projection, Base44 schema, admission, release/deploy, worker configuration, IAM, credentials, production, merge, or deployment changes are part of this checkpoint.
