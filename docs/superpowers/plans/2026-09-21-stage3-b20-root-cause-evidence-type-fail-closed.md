# Stage 3 B20 root-cause evidence type fail-closed — 2026-09-21

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

This serialized integration slice hardens the approved B20 explicit-evidence boundary and the downstream B24 signed handoff source. It does not alter production, `main`, crawl/admission state, schemas, RLS, secrets, Premium, Grok, or historical authority reconstruction.

## Defect

`scanner-api/app/stage3_root_causes.py` used the general `_clean()` helper for `root_cause_evidence.root_cause_id`, `repair_surface_id`, and individual `evidence_refs`. `_clean()` stringifies arbitrary objects. A structured producer/debug object therefore became a non-empty string and could satisfy B20's explicit-evidence checks, allowing malformed private/debug values to enter verified root-cause groups and downstream signed delivery state.

The approved semantics require stable explicit root-cause identities/evidence relationships; missing or invalid evidence remains unknown. Structured objects are not valid root-cause identifiers or evidence-reference strings and must fail closed rather than be coerced.

## RED proof

Regression commit: `089e55a1bad819a26b30302e46b71307eea132c8`

FixList CI: `35549637805` — expected failure.

Added `scanner-api/tests/test_stage3_root_cause_evidence_type_fail_closed.py` with two adversarial cases:

1. a mapping supplied as `root_cause_id` containing a private URL marker must not become a verified root-cause identity;
2. mapping-valued `evidence_refs` and `repair_surface_id` containing private/debug markers must not become verified provenance or surface identity.

CI evidence:

- root regressions: `115 passed`;
- scanner-api: `2 failed, 2073 passed, 18 skipped`;
- the two failures were exactly the new assertions: both malformed shapes were incorrectly classified as `verified`;
- lint, typecheck, generated release-contract verification, frontend contracts, and frontend build passed in the independent job;
- later scanner corpus/image steps were skipped because the intentional RED scanner-api failure stopped that job.

## GREEN correction

Implementation commit: `590dc20251952e76f265c76e40d4755299d0b6cc`

Exact-head FixList CI: `35549679233` — **SUCCESS** on both jobs.

The implementation adds a strict text projector used only for the explicit B20 root-cause identity/provenance fields. `root_cause_id`, `repair_surface_id`, and each `evidence_refs` entry now accept only actual strings; mappings, lists, numbers, booleans, and other structured/non-string values project to missing evidence and follow the existing fail-closed B20 path. Existing valid string evidence semantics are unchanged.

The source correction relative to the RED commit modifies only `scanner-api/app/stage3_root_causes.py`: 8 additions, 3 deletions.

Exact-head GREEN evidence:

- immutable checkout: `590dc20251952e76f265c76e40d4755299d0b6cc`;
- root regressions: `115 passed`;
- scanner-api: `2075 passed, 18 skipped`, including both new adversarial regressions;
- labelled Stage-1 synthetic corpus: 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision: `01ebe8e90df1e6bd` matched;
- production scanner image: `sha256:e70692e683320579176b608eead16394c399d7b9ae193f8b5ee9cf41009071b8`;
- lint, typecheck, generated release-contract verification, frontend contracts, and production build passed.

Hosted CI used Ubuntu 24.04.5 and Python 3.12.14. `setup-node` requested major Node 20 but resolved Node 20.20.2; this is not exact Node 20.19.5 evidence. GitHub also emitted the Node-24 action-runtime migration warning.

## Scope and remaining gates

This slice closes only the malformed-type gap at B20's explicit root-cause identity/surface/reference boundary. It does not claim every arbitrary producer field is customer-safe by itself; B24's positive customer projection remains independently required.

Stage 3 remains incomplete pending:

- a genuinely fresh independent review of the latest corrected B22/B24 shared authority/privacy boundary, including this B20 provenance hardening as it feeds handoff-v2;
- separate Stage-1 exact-source publication and fresh non-owner acceptance;
- reconciliation onto the then-current accepted `main`, preserving V7/#308, followed by exact integrated-head CI;
- real V7 producer → signed authority → persisted rows → exact-owner/exact-scan reload/history → customer card/export/preview proof for B19–B24.

Stage 4 remains held. The genuine provenance-labelled B25 30-site baseline/candidate gate remains `not_assessed`; synthetic fixtures do not satisfy it.
