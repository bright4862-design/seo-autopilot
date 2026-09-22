# Agent E — exact page-receipt evidence identity binding

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint stays inside the Agent E pure-helper/test/docs ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

The prior `fix_verification_observation_execution_binding_v1_exact_page_plan_identity` layer proves that every present page receipt names a targeted evidence key and belongs to the exact targeted plan execution. The earlier observation-identity boundary proves that a page row's URL aliases (`url`, `final_url`, `page_url`, `path`) are internally consistent under the published evidence URL identity contract.

Those two facts still did not prove that the page receipt's declared `evidence_key` actually identifies the page described by its URL fields. A same-scan receipt could therefore carry the exact plan fingerprint and a targeted evidence key while the receipt's URL described a different targeted page. The core evaluator derives page identity from URL fields, so the result may still fail safely in some arrangements, but the transport itself is ambiguous and must never be accepted as proof.

This checkpoint closes that gap before PASS/PARTIAL/FAIL or regression reopening can become authority evidence.

## New versioned contract

Implementation: `scanner-api/app/nextgen_fix_verification_page_receipt_identity.py`

Versions:

- `fix_verification_page_receipt_identity_binding_v1_exact_evidence_key_url_identity`
- `fix_verified_fixed_page_receipt_identity_bound_replay_v1_exact_page_evidence_key`
- `fix_regression_reopen_page_receipt_identity_bound_replay_v1_exact_page_evidence_key`

The pure binding:

1. requires the existing exact observation-execution binding to pass;
2. requires the existing exact multi-field observation identity binding to pass;
3. requires an exact non-empty current scan origin and the published evidence URL identity version;
4. resolves every populated page identity alias under that exact origin/version;
5. requires all populated aliases to resolve to one canonical evidence identity;
6. requires each page receipt's exact declared `evidence_key` to equal that canonical page identity;
7. preserves missing targeted pages as missing evidence rather than treating their absence as a binding failure.

A swapped/copy-pasted page label, foreign-origin URL paired with a targeted key, conflicting redirect alias, malformed origin, or unsupported identity version therefore fails closed before the existing strict replay stack can prove anything.

## Disappeared URL invariant

A disappeared URL is still never proof of a fix.

This binding intentionally validates only page receipts that are actually present. If one targeted request has no current page receipt, the binding remains valid and exposes the missing targeted evidence key. The downstream strict evaluator then returns `required_page_not_observed` and effective `COULD_NOT_VERIFY`. The new layer never turns absence into PASS.

## Added deterministic regressions

`scanner-api/tests/test_nextgen_fix_verification_page_receipt_identity.py` adds 14 cases covering:

1. exact page receipt identity acceptance;
2. swapped targeted evidence-key labels;
3. a single mislabeled page URL;
4. conflicting page URL aliases;
5. unsupported URL-identity version;
6. whitespace-normalized scan origin rejection;
7. path-only page identity acceptance;
8. foreign-origin page paired with a targeted label;
9. exact PASS propagation through the verified-fixed wrapper;
10. fail-closed verified-fixed denial on swapped labels;
11. exact FAIL regression reopening;
12. PARTIAL reopen-scope preservation;
13. fail-closed regression denial on a mislabeled page; and
14. disappeared-page preservation as `COULD_NOT_VERIFY`.

Expected focused Lane-E total after this checkpoint: **275 tests** (previous 261 + 14 page-receipt identity regressions).

## Verification performed in this runtime

- new helper source: `py_compile` passed;
- new focused test source: `py_compile` passed;
- hermetic composition harness: **10/10** page-receipt identity / strict-wrapper scenarios passed;
- container Git cannot resolve `github.com`, so an exact repository-native 275/275 pytest claim is not made here.

Exact branch-native focused gate still required:

```bash
cd scanner-api
PYTHONPATH=. python -m pytest -q \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verified_fixed_observation_replay.py \
  tests/test_nextgen_fix_verification_observation_integrity.py \
  tests/test_nextgen_fix_verification_plan_transport_integrity.py \
  tests/test_nextgen_fix_verification_observation_identity.py \
  tests/test_nextgen_fix_verification_historical_identity.py \
  tests/test_nextgen_fix_regression_reopen_replay.py \
  tests/test_nextgen_fix_verification_observation_values.py \
  tests/test_nextgen_fix_verification_origin_binding.py \
  tests/test_nextgen_fix_regression_state_integrity.py \
  tests/test_nextgen_fix_verification_historical_evidence_aliases.py \
  tests/test_nextgen_fix_verification_plan_envelope.py \
  tests/test_nextgen_fix_verification_scan_lineage.py \
  tests/test_nextgen_fix_verification_plan_lineage.py \
  tests/test_nextgen_fix_verification_result_transport.py \
  tests/test_nextgen_fix_verification_plan_identity.py \
  tests/test_nextgen_fix_verification_execution_binding.py \
  tests/test_nextgen_fix_verification_observation_execution.py \
  tests/test_nextgen_fix_verification_page_receipt_identity.py
```

## Serialized integration handoff

After lanes A-D are integrated and the focused/full scanner suites are green, the serialized integrator should treat the new page-receipt identity-bound wrappers as the strictest Lane-E pure entrypoints:

- `strict_verified_fixed_transition_from_page_receipt_identity_bound_inputs(...)`
- `strict_regression_reopen_from_page_receipt_identity_bound_inputs(...)`

The current scan origin must come from authoritative ScanRun/crawl-scope metadata, not from repair rows or request-supplied guesses. Each targeted page receipt must be stamped with the exact plan fingerprint/identity version and the exact targeted evidence key for the page URL actually observed. Current scan IDs and comparison-contract lineage remain supplied from the existing authoritative scan metadata. Durable `verified_fixed` still requires the unchanged legacy `repair_verification_v3_contract_comparable` replay inside the existing strict stack.

No durable authority/persistence/customer projection, `run_scan`, global budgets, repair priority, Base44 schema, admission, release/deploy, worker configuration, IAM, credentials, production, merge, or deployment change is part of this checkpoint.
