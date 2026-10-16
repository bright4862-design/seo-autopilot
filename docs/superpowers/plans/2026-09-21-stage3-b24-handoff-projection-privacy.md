# Stage 3 B24 handoff-v2 customer projection privacy checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec's B24 semantics control: handoff v2 must remain authenticated, preserve historical-v1 compatibility, and must not expose suppressed/operator-only/private producer state to customer readers.

## Scope

This slice hardens the already-integrated B24 signed handoff source. It does not alter Stage-1 production, V7 routes, persistence schemas, admission, workers, Premium/Grok, or the held Stage-4 lane.

Fresh source inspection found that `build_handoff_v2()` and `_handoff_fix()` used a positive key shape but deep-copied or passed through values without a positive public type/schema projection. Because the canonical repair candidate intentionally contains richer producer/review state, structured private/debug values under otherwise allowed keys — and unknown keys inside `scan_identity` / `priority_factors` — could cross the signed handoff boundary.

## RED

Commit: `083e3a0c1a649be8162c40ee0d85f6ed0c66773c`

Regression file: `scanner-api/tests/test_stage3_b24_handoff_projection_privacy.py`

FixList CI: `35546672358`

Observed proof:

- root regressions: `115 passed`;
- scanner-api: `2 failed, 2071 passed, 18 skipped`;
- both failures were the new B24 regressions;
- one failure proved arbitrary `scan_identity.operator_debug` survived into `handoff["scan"]`;
- the second proved malformed string numeric evidence such as `priority_factors.impact="5"` survived without fail-closed projection;
- lint/typecheck/generated-release-contract/frontend-contract/build job passed;
- later corpus/image steps were skipped because the scanner-api job failed.

## GREEN implementation

Commit: `ef0204b9a7851a53c040b334f99e1e541097d4b3`

Implementation changes in `scanner-api/app/stage3_delivery.py`:

- `_handoff_text()` accepts only actual strings;
- `_handoff_scan_identity()` positive-allowlists the signed customer scan identity fields and drops unknown debug/operator keys;
- `_handoff_priority_factors()` positive-allowlists the exact versioned B19 public factor schema, reusing strict finite numeric/integer evidence rules and string-only explanation items;
- `_handoff_fix()` now type-projects rule/title/root-cause identity, URL provenance, dependency and vendor owner rather than passing structured values through;
- existing string filtering for family IDs, evidence refs and verification steps remains;
- `suppressed_findings` remains available only when `operator_authorized is True` literally; the normal customer signed source still calls B24 with operator authorization false;
- historical-v1 reader compatibility is unchanged.

Exact-head FixList CI: `35546802039`, both jobs passed.

Evidence:

- root regressions: `115 passed`;
- scanner-api: `2073 passed, 18 skipped`;
- both new B24 projection/privacy regressions passed;
- Stage-1 labelled corpus remained `provenance=synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd` matched;
- production scanner image built successfully: `sha256:9747d4e93d14e915ee07e4e86139fad22b7d7f8c7a2fd26185602a864f730a81`;
- lint, typecheck, generated release-contract verification, frontend contracts and production build passed.

Runtime evidence: Ubuntu 24.04.5, Python 3.12.14. `setup-node` requested major Node 20 and resolved `20.20.2`; this is not exact Node 20.19.5 evidence. GitHub also emitted the Node-24 action-runtime migration warning.

## Requirement state

B24 remains **partial**, not complete. This slice closes one customer-safe serialization defect in the signed handoff source, but the approved B24 gate still requires:

1. a genuinely fresh independent review of the corrected shared B22/B24 authority/privacy boundary;
2. Stage-1 exact-source publication plus fresh non-owner acceptance by the separate release operator;
3. reconciliation onto that accepted `main` with exact integrated-head CI;
4. real V7 producer → signed authority → persisted rows → exact-owner/exact-scan read/reload/history → customer/operator/card/export proof, including suppressed/operator privacy and historical-v1 compatibility.

Stage 4 remains held. B25's genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`.
