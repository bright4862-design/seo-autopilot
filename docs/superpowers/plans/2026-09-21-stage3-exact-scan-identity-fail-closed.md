# Stage 3 exact-scan identity fail-closed checkpoint

Date: 2026-09-21

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. Exact B19/B20/B22/B24 identity semantics in the approved spec control.

## Scope

This serialized slice hardens the shared Stage-3 exact-scan authority boundary used by B20 grouping, B22 signed preview source, and B24 signed handoff source. It does not change V7 persistence, production, admission, workers, schema/RLS, secrets, Premium, or Grok.

Fresh inspection found `_trusted_stage3_scan_id()` in `scanner-api/app/repair_contract_v2.py` accepted `scan_id` and `scan_run_id` through `_clean_text()`. Matching structured values such as the same dictionary were stringified into identical non-empty text and therefore treated as a trusted exact producer scan identity. That stringified private/debug content could then enter the signed Stage-3 source structures.

## RED

Commit: `f0d6f217ab338874fc13dd576f40195af06a0fac`

Regression file: `scanner-api/tests/test_stage3_exact_scan_identity_fail_closed.py`

The two adversarial cases require:

1. a matching structured `scan_id`/`scan_run_id` pair to produce no trusted identity;
2. B24 source construction to fail closed rather than serialize that structured identity or its private sentinel.

FixList CI: `35559679611`

Expected RED evidence:

- immutable checkout matched `f0d6f217ab338874fc13dd576f40195af06a0fac`;
- root scanner regressions: `115 passed`;
- scanner-api: `2 failed, 2081 passed, 18 skipped`; the two failures were exactly the new structured-identity regressions;
- the independent lint/typecheck/generated-contract/frontend/build job passed;
- corpus/frozen-revision/image steps did not run after the intentional scanner-suite RED failure.

## GREEN

Implementation commit: `08c94082bd731c371bc06946df5b821521aa3861`

`_trusted_stage3_scan_id()` now:

- requires both producer identity fields to be actual strings;
- strips whitespace only after type validation;
- requires both strings to be non-empty and exactly equal;
- returns no trusted identity for dictionaries, lists, booleans, numbers, or other structured/coercible values.

The RED→GREEN compare changes only `scanner-api/app/repair_contract_v2.py`, with 9 additions / 4 deletions. Valid literal exact scan identities preserve prior behavior.

Exact-head FixList CI: `35559929454`

GREEN evidence:

- both CI jobs passed;
- immutable checkout matched `08c94082bd731c371bc06946df5b821521aa3861`;
- root scanner regressions: `115 passed`;
- scanner-api: `2083 passed, 18 skipped`;
- both new exact-scan identity regressions passed;
- labelled Stage-1 corpus remained explicitly synthetic at `14 cases / 55 assertions`, with `full_30_site_gate=not_assessed`;
- frozen beta revision remained `01ebe8e90df1e6bd`;
- scanner image built as `sha256:2f2a1f8d5a35a1ccdba861061c5ad58e42c98152b32ce0e2d44990c5ff30d5b8`;
- lint, typecheck, generated release-contract verification, frontend contracts, and production build passed.

Environment note: workflow setup requested Node 20 but resolved Node `20.20.2`; exact Node `20.19.5` evidence is not claimed. GitHub Actions also emitted the Node-20 action-runtime deprecation warning.

## Requirement effect

- **B20:** exact-scan shared-root-cause grouping can no longer be established from stringified structured producer identity.
- **B22:** signed private-preview source requires the same literal exact producer identity and therefore fails closed for malformed identity shapes.
- **B24:** signed handoff-v2 source no longer serializes structured producer scan identity through the trusted-ID adapter.

This does not complete Stage 3. A genuinely fresh independent review of the latest shared B22/B24 authority/privacy boundary remains open, as do Stage-1 publication/non-owner acceptance, reconciliation onto accepted `main`, exact integrated-head CI, and real V7 persisted customer/card/export/preview proof.

## Release boundary

Direct `main` remained `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad` at the start of this slice. Current-main Stage-1 acceptance still recorded exact-source production publication and fresh non-owner acceptance as pending. No production deployment, merge, worker/admission mutation, production scan, schema/RLS change, secret rotation, provider fabrication, Premium enablement, or Grok enablement was performed.

The genuine provenance-labelled B25 30-site baseline/candidate gate remains `not_assessed`; synthetic corpus evidence is not a substitute.
