# Agent E — exact rule-evaluation ↔ page-observation receipt binding

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint remains inside the Agent E pure-helper/test/docs ownership boundary defined in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

Earlier Lane-E layers prove that a verification plan is exact and identity-bound, that current page observations and rule evaluations come from the intended current scan, that both belong to the exact targeted-plan execution, and that each page receipt's declared evidence key matches its URL identity.

Those guarantees still leave one narrower provenance ambiguity: a rule-evaluation row for evidence key X can be paired with a different page observation for the same evidence key X from another same-plan fetch attempt. If the page changed between attempts, the transported predicate result no longer proves what the selected page receipt actually contained.

This checkpoint adds a versioned pure receipt-binding layer before PASS/PARTIAL/FAIL, verified-fixed, or regression-reopen proof can be consumed.

## New versioned contracts

Implementation: `scanner-api/app/nextgen_fix_verification_evaluation_receipt_binding.py`

Versions:

- `fix_verification_page_observation_receipt_v1_exact_proof_transport_sha256`
- `fix_verification_evaluation_receipt_binding_v1_exact_page_observation_receipt`
- `fix_verified_fixed_evaluation_receipt_bound_replay_v1_exact_page_observation_receipt`
- `fix_regression_reopen_evaluation_receipt_bound_replay_v1_exact_page_observation_receipt`

For each present current-page observation, the helper computes a lowercase SHA-256 over the versioned exact proof-bearing page transport: scan-lineage aliases, targeted evidence key, exact verification-plan identity, URL aliases, HTTP-status aliases, content-type aliases, indexability, evidence-class aliases, and robots aliases. No string coercion or whitespace normalization participates in the receipt.

Each rule-evaluation row for a present page must then carry both:

- `page_observation_receipt_version`; and
- `page_observation_receipt_fingerprint`.

The version must exactly match the published receipt version and the fingerprint must exactly match the current page receipt for that evidence key. Missing, malformed, uppercase-normalized, stale, swapped, or copied receipt claims fail closed before the existing strict replay stack can prove anything.

The helper composes the existing page-receipt identity binding first, so exact plan execution, page identity, and evidence-key ↔ URL binding remain prerequisites rather than being reimplemented.

## Disappeared URL invariant

A disappeared URL remains non-proof.

If a targeted page is not observed, the evaluation row for that target is not allowed to invent or claim a page-observation receipt. The receipt binding may remain structurally valid with the target listed in `missing_required_evidence_keys`; the downstream evaluator still emits `required_page_not_observed` and `COULD_NOT_VERIFY`.

Therefore page absence can neither authorize `verified_fixed` nor establish regression reopening.

## Added deterministic regressions

`scanner-api/tests/test_nextgen_fix_verification_evaluation_receipt_binding.py` adds 14 cases covering:

1. deterministic receipt hashing independent of dictionary insertion order;
2. receipt mutation when comparable page evidence changes;
3. exact evaluation↔receipt binding acceptance;
4. missing receipt fingerprint rejection for a present page;
5. unsupported receipt version rejection;
6. swapped same-plan page receipts;
7. stale receipt rejection after page transport mutation;
8. noncanonical SHA-256 transport rejection;
9. missing page retained as missing when the evaluation does not claim a receipt;
10. false receipt claim for a missing page rejection;
11. exact PASS propagation through the strict verified-fixed wrapper;
12. exact FAIL regression reopening;
13. exact PARTIAL reopen-scope preservation; and
14. disappeared-page preservation as `COULD_NOT_VERIFY` with `required_page_not_observed`.

Expected focused Lane-E total after this checkpoint: **289 tests** (previous 275 + 14 evaluation-receipt regressions).

## Verification performed for this slice

- new helper source: `py_compile` passed before publication;
- new focused test source: `py_compile` passed before publication;
- test source contains exactly 14 deterministic `test_` functions;
- hermetic receipt-binding/wrapper composition harness: **12/12** scenarios passed before publication.

A repository-native 289/289 claim is intentionally not made from this runtime because no local repository checkout is available here. The branch-native focused gate remains:

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
  tests/test_nextgen_fix_verification_page_receipt_identity.py \
  tests/test_nextgen_fix_verification_evaluation_receipt_binding.py
```

## Serialized integration handoff

After serialized integration, the strictest Lane-E pure entrypoints should be:

- `strict_verified_fixed_transition_from_evaluation_receipt_bound_inputs(...)`
- `strict_regression_reopen_from_evaluation_receipt_bound_inputs(...)`

The future executor should compute the page-observation receipt fingerprint from the exact finalized page observation transport after its proof-bearing observation fields are finalized and before emitting that page's rule-evaluation row. A rule evaluation for a present page must carry the exact receipt version/fingerprint. If a targeted page was not observed, no page-receipt claim should be invented; the existing downstream missing-page path must remain `COULD_NOT_VERIFY`.

This checkpoint does not change the existing `repair_verification_v3_contract_comparable` comparator or durable authority semantics. Durable `verified_fixed` still requires the existing legacy comparator proof inside the strict replay chain.

No durable authority/persistence/customer projection, `run_scan`, global budgets, repair priority, Base44 schema, admission, release/deploy, worker configuration, IAM, credentials, or production behavior is modified by this checkpoint. Nothing here should be merged or deployed from the lane branch.
