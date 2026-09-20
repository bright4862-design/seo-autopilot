# Stage 2 B13/B14 — local entity and cross-page NAP evidence

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303

## Scope

This slice implements a conservative producer/evidence seam for B13 local entity completeness and B14 cross-page NAP consistency without introducing a new network request path, request budget, customer repair, score adjustment, or sitewide consistency claim.

The implementation consumes only accepted page HTML already obtained by the Standard-150 crawler. It does not infer entity identity from shared names, phone numbers, addresses, URL shape, or page-family similarity.

## Producer behavior

`scanner-api/app/stage2_local_entity_producer.py` parses bounded JSON-LD LocalBusiness/Store-family observations from accepted usable HTML and records bounded structured evidence for:

- name;
- address;
- phone;
- regular hours when explicitly present;
- structured entity type;
- explicit JSON-LD entity ID;
- optional holiday-hours/photos/sameAs/parent-entity presence.

Optional holiday-hours/photos/sameAs/parent fields are not universal requirements. Missing regular hours are not automatically a defect: when applicability is unknown they remain `not_verified`.

Malformed or oversized JSON-LD remains `not_verified`; an unusable HTTP page cannot contribute accepted local-entity evidence.

Page observations are bounded to 10 selected observations while preserving an exact unique candidate count. Scan aggregation is bounded to 20 selected observations and records whether selection was truncated.

## B14 identity and comparison rules

Cross-page NAP evidence is deliberately stricter than B13 completeness:

- only an explicit absolute HTTP(S) JSON-LD `@id` is currently accepted as verified cross-page identity;
- fragment/relative IDs such as `#store` are retained as observed IDs but are `unverified` until a trusted document base is available for correct resolution;
- shared names, addresses, phones, or page-family similarity never establish identity;
- an entity is comparable only when the same verified explicit ID is observed on at least two distinct page URLs;
- duplicate/conflicting JSON-LD on one page cannot become cross-page proof;
- one verified observation cannot produce a NAP-consistency pass;
- distinct explicit entity IDs remain separate even when they share a phone number;
- `sitewide_consistency_claim` is always false for this bounded assessed-page evidence.

These rules preserve unknown/ambiguous evidence rather than manufacturing a pass or failure.

## Behavioral regressions

`scanner-api/tests/test_stage2_local_entity_producer.py` covers:

- accepted structured entity completeness;
- unknown regular-hours applicability;
- verified cross-page inconsistency from the same explicit entity ID;
- verified cross-page matching NAP;
- same-page duplicate/conflicting identity remaining unverified for B14;
- separate explicit entities sharing a phone number;
- no-ID observations remaining unverified;
- unusable HTTP evidence rejection;
- malformed JSON-LD fail-closed behavior;
- unique candidate deduplication and bounded selection.

`scanner-api/tests/test_stage2_local_entity_identity.py` adds explicit regressions for relative/fragment JSON-LD IDs and preserves the verified absolute-ID path.

## Verification

Intermediate cross-page implementation head `b513c6c7a47e39d792b342f15d6ff31025f5d099` passed FixList CI `35484212032` on both jobs:

- root scanner regressions: 115 passed;
- scanner-api: 1,950 passed / 18 intentional skips;
- Stage-1 labelled corpus: synthetic, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:7c634b53988ff3a865b0af809edd93f3f8b583b4e0973e6a501e4c6c801639e8`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

Final exact executable head for this slice: `fe3d18cc63f7b0acdf0e97679db5b14e47966e10`.

FixList CI `35484333097` passed both jobs on that exact head:

- immutable checkout verified `fe3d18cc63f7b0acdf0e97679db5b14e47966e10`;
- root scanner regressions: **115 passed**;
- scanner-api: **1,952 passed / 18 intentional skips**;
- Stage-1 labelled corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:e776770dc976cf7c4b434e134db31323f61278c0f8c460c53ca890cc50d11bb9`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow resolved Node `20.20.2`; this is not Node `20.19.5` runtime evidence.

## What is not yet proven

B13/B14 are **not source-complete** yet.

The page-level structured observations are produced on accepted crawler pages, and the scan-level `build_local_entity_scan_evidence(pages)` adapter is tested, but the bounded scan-level summary is not yet attached to the shared `run_scan` result/authority path. No B13/B14 customer repair/card/export or score change is introduced by this slice.

The current producer also does not claim generic visible-text/store-form entity identity, Coming Soon status inference, or complete store-finder/form parity. Those require explicit provenance rather than heuristics.

## Next serialized action

Wire the bounded scan-level B13/B14 evidence into the shared scanner result without changing the Standard-150 assessed set or request budget. Keep it evidence-only unless/until an authenticated Review → authority → persistence → customer/card/handoff/export path is added. Then continue B15 contextual freshness, direct B17 transfer bytes/CrUX states, and B18 GSC states.
