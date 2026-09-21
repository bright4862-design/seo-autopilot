# Stage 3 B22/B24 upstream projection coercion fail-closed

## Authority and scope

Authoritative requirement source: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`, especially B22 and B24. The approved semantics require evidence-led private preview and an authenticated customer-safe handoff-v2; missing/invalid evidence stays unknown and operator/debug structures must not become customer evidence merely because an upstream helper can stringify them.

This slice is implementation-only on `agent/full-blueprint-stage2-coverage-b06-20260919` / PR #303. It does not merge to `main`, deploy, promote a worker, mutate admission/queues/scheduler, run a production scan, alter schema/RLS/secrets, or enable Premium/Grok.

## Reproduction

RED source/test commit: `8800fa6f72caf814024b965b5c3eb5c59b5515db`.

FixList CI `35576295545` failed exactly two new signed-source regressions while the independent lint/typecheck/generated-contract/frontend/build job passed. Root scanner tests were `115 passed`; scanner-api was `2 failed, 2092 passed, 18 skipped`.

The reproduced defects were:

1. `scan_result.normalized_domain` accepted a structured mapping and `_clean_text()` stringified it before B24's strict serializer, so the signed customer handoff carried operator/debug material as plain text instead of `None`.
2. Structured `issue_title` and `evidence_refs` were stringified in `repair_contract_v2.py` before B22/B24 projection. The private preview title and handoff evidence could therefore carry producer/debug structure despite the downstream serializer's type checks.

The regressions run through `apply_canonical_repair_contract()` and `build_completion_envelope()` so the proof covers producer/review integration and the signed Stage-3 source fields rather than an isolated helper only.

## Implementation

Source correction commit: `5708b1b6b7fd661c7343d574ca08e785e3ba32f7`.

`scanner-api/app/repair_contract_v2.py` now has Stage-3-specific literal-string projection helpers instead of reusing the legacy coercive `_clean_text()` at the signed/customer boundary. The strict projection is applied to B20 group identity consumed by B24, member/family/evidence identifiers, B22 rule/title fallback, B24 rule/title/vendor owner, B24 scan metadata, B21 displayed IDs, and B23 root-cause cap identifiers. Structured values fail closed; valid literal strings retain existing behavior and fallback ordering.

RED-to-source-correction compare is one implementation file: `scanner-api/app/repair_contract_v2.py`, 46 additions / 27 deletions.

FixList CI `35576782551` proved both reproduced customer-source leaks were corrected, but retained one failing assertion because the new test incorrectly required the entire signed internal Review to omit the private sentinel. The canonical Review deliberately retains rich producer/review evidence; B22/B24 constrain the customer projections inside that signed Review. That run therefore finished `1 failed, 2093 passed, 18 skipped`, with root tests `115 passed`, while lint/typecheck/generated-contract/frontend/build passed. Corpus/frozen/image steps were skipped after the scanner test failure.

Test-scope correction commit: `dfb9043d3cbf510ec867c68a5cde02c7cea29323`.

The final regression verifies the two signed customer projections after completion-envelope construction rather than asserting that unrelated internal Review fields are customer-safe. This preserves the intended no-leak requirement without redefining the internal authority payload.

## Final verification

Exact-source FixList CI `35577052441` passed both jobs at `dfb9043d3cbf510ec867c68a5cde02c7cea29323`:

- immutable checkout matched the exact SHA;
- root scanner regressions: `115 passed`;
- scanner-api: `2094 passed, 18 skipped`;
- both new B22/B24 coercion regressions passed;
- labelled Stage-1 corpus: provenance `synthetic`, `14` cases / `55` assertions, `full_30_site_gate=not_assessed`;
- frozen beta revision matched `01ebe8e90df1e6bd`;
- scanner image built as `sha256:4e9407eba4ede42737012e22c730905ffa2dfe1dd9e06a5fbefe7f29eeead33e`;
- lint, typecheck, generated release contracts, frontend contracts and production build passed.

Runtime note: workflow setup requested Node 20 but installed Node `20.20.2`; exact Node 20.19.5 evidence is not claimed. GitHub also emitted the action-runtime Node-20 deprecation warning.

## Requirement state after this slice

- **B22 remains partial:** signed evidence-led preview source now also fails closed against upstream structured-text coercion. Fresh independent review and the real authenticated V7 exact-owner/exact-scan persisted customer preview remain open.
- **B24 remains partial:** handoff-v2 source now fails closed against structured scan metadata, title, identifiers, family/evidence references and vendor ownership before signing. Historical-v1 compatibility is unchanged. Fresh independent review plus durable V7 persistence/read/card/export/operator-privacy proof remain open.
- **B19/B20/B21/B23 remain partial:** this slice only tightens the shared Stage-3 trust seam; it does not claim their remaining durable customer acceptance.
- **Stage 3 is not complete. Stage 4 remains held. B25's genuine provenance-labelled 30-site gate remains `not_assessed`.**

## Next serialized action

Persist this source/test checkpoint in the two authoritative ledgers and PR #303, then run exact-head FixList CI on the final documentation checkpoint. Do not mutate production or integrate Stage 4. After a genuinely fresh independent review and the separate Stage-1 exact-source publication/non-owner acceptance gate close, reconcile onto the then-current accepted `main`, run fresh integrated-head CI, and prove the real V7 producer -> signed authority -> persisted rows -> exact-owner/exact-scan reload/history -> card/export/preview seams.
