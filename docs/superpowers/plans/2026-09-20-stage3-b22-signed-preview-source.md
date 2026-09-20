# Stage 3 B22 signed private-preview source checkpoint

Authoritative requirement: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md` B22.

B22 requires an evidence-led private preview: prefer individually verified impact-4/5 findings, otherwise the best verified finding; permit a good-shape message only with an explicit coverage qualification; preserve existing entitlements and no-leak rules.

## Scope and release boundary

This slice proves the Python producer/review/signed-authority source only. It does not create, copy, or mutate V7 persistence/customer routes and does not grant an entitlement. The source explicitly records `entitlement_state=requires_authenticated_customer_gate`. Exact owner/customer access remains the V7 responsibility after Stage-1 accepted-main reconciliation.

`main` remains release-frozen at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad` until the existing Stage-1 release operator records exact-source production publication and fresh non-owner acceptance.

## RED

Regression commit: `29aea5f3ed958805ed21bd2ce75e393e7330ca8f`.

FixList CI `35519071373` failed intentionally in the Python scanner-api job while the independent lint/typecheck/contracts/frontend job passed. The new regression failed with `KeyError: 'stage3_private_preview_source'`, proving that the shared signed source did not yet exist. Scanner-api summary at RED: 1 failed, 2037 passed, 18 skipped.

The regression requires:

- exact trusted producer `scan_id == scan_run_id`;
- individually verified findings only;
- evidence-led top-two selection;
- a strict customer-safe whitelist of `rule_id`, `title`, `impact`, and `evidence_summary`;
- exclusion of private debug, suppressed finding and affected-page fields;
- inclusion in the existing completion-HMAC signed Review;
- fail-closed absence when producer scan identity is not exact.

## Implementation

`20849a58acc968a25bd29e72c24abb42626bcb17` factors the pure evidence-led selector in `stage3_delivery.py`. Existing `select_private_preview` keeps its authority/exact-owner/exact-scan checks and delegates only the already-authorized candidate selection.

`2f6eb233d89e68475030a18d2157fc3d08b95938` integrates `stage3_private_preview_source` into canonical Review before completion signing. The source:

- requires exact trusted producer scan identity;
- derives candidates only from canonical reviewed repairs;
- allows only exact `verification_state=verified` repairs into preview eligibility;
- ranks with B19 impact/composite evidence and the reviewed B22 selector;
- carries only bounded allowlisted preview fields;
- carries an explicit coverage qualification only when one exists; no good-shape text is fabricated;
- records `entitlement_state=requires_authenticated_customer_gate` instead of fabricating owner authorization;
- fails closed when producer scan identity is unavailable or mismatched;
- is authenticated by the existing completion HMAC as part of Review.

## GREEN verification

Executable SHA: `2f6eb233d89e68475030a18d2157fc3d08b95938`.

FixList CI `35519385104` completed successfully on both jobs:

- root regressions: 115 passed;
- scanner-api: 2038 passed, 18 skipped;
- new B22 signed-preview tests: 2 passed;
- labelled Stage-1 corpus: synthetic, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen beta revision: `01ebe8e90df1e6bd` matched;
- production scanner image built as `sha256:8a1237919d53b62b02dd338173bae69bb8cecabc255d2cf6c4dda655f1496810`;
- lint, typecheck, generated release contracts, frontend contracts and production frontend build passed.

CI requested Node 20 but hosted setup resolved Node `20.20.2`; this run is not exact Node 20.19.5 evidence. Python was 3.12.14 on Ubuntu 24.04.5.

## Requirement state

B22 is **partial**, not complete overall. Signed producer/review authority source and no-leak source projection are RED->GREEN proven. Remaining applicable acceptance is:

1. fresh independent review of the combined shared B22/B24 authority/privacy surface;
2. after Stage-1 accepted-main reconciliation, consume this authenticated source through the real V7 persistence/read/customer preview path without recreating routes;
3. prove exact owner/scan entitlement, two-finding cap, reload/history/card/export privacy and no suppressed/operator leakage;
4. prove a customer-facing good-shape message only when the signed source contains an explicit sufficient coverage qualification.

No deployment, `main` merge, admission/worker mutation, production scan, schema/RLS change, secret rotation, Premium enablement, or Grok enablement occurred in this slice.
