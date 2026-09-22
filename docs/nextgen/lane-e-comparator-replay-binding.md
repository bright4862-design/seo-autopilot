# Agent E — legacy comparator replay binding hardening

Issue: #326  
Draft PR: #330  
Branch: `agent/nextgen-fix-verification-20260921`

This checkpoint stays inside the Agent E pure-helper/test/docs ownership boundary from `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

## Gap closed

The strict verified-fixed transition already requires both a population-bound NextGen PASS and the existing `repair_verification_v3_contract_comparable` legacy proof. The legacy comparator result itself, however, does not carry a repair fingerprint or criterion id. A transported `verified_fixed` comparison copied from another repair with the same affected-page count could therefore be structurally valid without independently proving that it was produced for the same historical repair and current evidence.

The lane must not change the historical comparator contract. Instead, this checkpoint adds a pure replay boundary that recomputes the existing comparator from the exact historical repair plus current fixes/pages/contract immediately before applying the strict NextGen transition gate.

## New versioned replay contract

Implementation: `scanner-api/app/nextgen_fix_verified_fixed_replay.py`

Version:

- `fix_verified_fixed_replay_v1_recomputed_legacy_comparator`

Preferred serialized-integration entrypoint:

- `strict_verified_fixed_transition_from_evidence(...)`

The helper:

1. requires object/list-shaped historical repair, NextGen result, current fixes, current pages, and current comparison contract;
2. requires string scan-origin context without silent whitespace normalization;
3. calls the existing `compare_repair_runs(...)` comparator unchanged over those exact inputs;
4. feeds only that newly recomputed comparator output into `strict_verified_fixed_transition_decision(...)`;
5. allows a transition only when the recomputed legacy comparator and the population-bound NextGen PASS both prove the transition;
6. returns a pure-data denial on malformed inputs or comparator replay failure.

No persisted or caller-supplied legacy comparator object is accepted by this helper.

## Why this preserves historical compatibility

`compare_repair_runs(...)`, `repair_verification_v3_contract_comparable`, historical reconstruction, and persisted repair bytes are untouched. This helper is a stricter consumer boundary around the existing comparator, not a replacement comparator and not a change to its semantics.

This also makes the disappeared-URL rule executable at the final strict boundary: if a previously affected page is absent from the supplied current page evidence, the recomputed legacy comparator returns `could_not_verify`, so an old or copied NextGen PASS cannot authorize `verified_fixed`.

## Added deterministic regressions

`scanner-api/tests/test_nextgen_fix_verified_fixed_replay.py` adds six cases:

1. complete current evidence + NextGen PASS + recomputed legacy `verified_fixed` permits the pure transition proposal;
2. a matching current repair forces legacy `still_detected` and denies the transition even if a transported NextGen result says PASS;
3. a disappeared historical page forces legacy `could_not_verify` and denies the transition;
4. an HTTP 404 current page is non-comparable and denies the transition;
5. rule-definition version drift forces legacy `could_not_verify` and denies the transition;
6. malformed current-page container input fails closed without invoking a transition.

Lane E therefore contains **63 focused tests** after this checkpoint:

- 18 core verification tests;
- 20 integrity/binding/reopen tests;
- 19 strict verified-fixed transition tests;
- 6 comparator-replay binding tests.

## Verification in this runtime

The new helper and new test source both pass `py_compile`. A hermetic stubbed replay harness exercised the new helper's allow/still-detected/missing-page/malformed-origin/input-shape branches and passed **5/5** scenarios.

The exact repository-native 63-test Lane-E gate remains required because the local execution container cannot resolve `github.com` and this draft PR does not receive the repository's normal `main`-targeted workflow trigger:

```bash
cd scanner-api
PYTHONPATH=. python -m pytest -q \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py
python -m py_compile \
  app/nextgen_fix_verification.py \
  app/nextgen_fix_verification_integrity.py \
  app/nextgen_fix_verified_fixed_transition.py \
  app/nextgen_fix_verified_fixed_replay.py \
  tests/test_nextgen_fix_verification.py \
  tests/test_nextgen_fix_verification_integrity.py \
  tests/test_nextgen_fix_verified_fixed_transition.py \
  tests/test_nextgen_fix_verified_fixed_replay.py
```

Do not claim 63/63 exact-head repository green until that command runs in an approved checkout/runner.

## Serialized integration handoff

After lanes A–D are integrated and green, the serialized integrator should prefer `strict_verified_fixed_transition_from_evidence(...)` over accepting a transported legacy comparison. Supply historical scan origin only from authoritative historical scan/crawl-scope metadata, supply current scan origin from authoritative current scan scope, and pass the exact current repair/page/contract evidence already used by the current scan. Keep every malformed, missing, changed-version, disappeared-page, or non-comparable case fail-closed.

No durable authority/persistence/customer projection, `run_scan`, global budgets, repair priority, Base44 schema, admission, release/deploy, worker configuration, IAM, credentials, production, merge, or deployment change is part of this checkpoint.
