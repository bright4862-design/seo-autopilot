# Stage 2 follow-up review hardening

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

Scope: final serialized B06–B18 hardening on PR #303 after the fresh whole-stage independent review. This record does not authorize production publication, admission mutation, worker promotion, live scans, schema/secrets changes, or Stage-3 integration.

## Independent review findings

The fresh CodeRabbit follow-up review reported two material P1 defects on the then-current Stage-2 source:

1. **Direct authority/signing helpers were not independently defensive.** The common post-crawl projection removed private Stage-2 producer fields during the normal scanner path, but direct calls to `build_authority_review_payload`, `build_completion_envelope`, and `build_limited_envelope` could still accept an unprojected result and sign/persist B10 fingerprints, the private B11 `_reachability_links` cache, B13 raw local-entity/contact observations, or B15 per-page freshness evidence.
2. **Optional provider timestamps accepted future observations.** CrUX/GSC adapter staleness logic checked only maximum age, so an `observed_at` later than the scan's `as_of` date could be admitted as current evidence.

## RED reproduction

Commit: `bea5d3d8a1ec5d7f77d7f68ca4919a45226ded42` — `test(stage2): reproduce review follow-up privacy and provider-time defects`.

`scanner-api/tests/test_stage2_followup_review_regressions.py` added three behavioral regressions:

- a raw Stage-2 result passed directly to the authority-review helper must have private producer sentinels removed;
- completion and limited-result signing helpers must project before sealing the scan payload;
- future-dated authorized CrUX/GSC payloads must fail closed as `unavailable`, with reason `provider_observation_time_invalid` and no admitted metrics.

FixList CI `35498446283` failed exactly as intended:

- root scanner regressions: **115 passed**;
- `scanner-api`: **3 failed / 1,990 passed / 18 skipped**;
- the three new follow-up regressions were the failures;
- lint/typecheck/generated contracts/frontend contract tests/frontend build passed.

## Corrections

### Future provider time

- `12d6c7a24b68a681cd9a5d1a0b78a996ae23edaa` — `optional_crux_adapter` and `optional_gsc_adapter` reject `observed_at > as_of` as `unavailable` with reason `provider_observation_time_invalid` before stale/current classification.
- `0e5a0ed176d764a9ac78bc2d96833f46a268911d` — connected CrUX/GSC scan wrappers preserve that fail-closed reason; GSC exposes the same normalized aggregate reason when all selected rows are invalid future observations.

No provider network call, connection, credential, permission or synthetic current-state claim was added.

### Direct authority/signing boundary

- `10798d00d1c0e7cc31a6dfaca3cd4fc67abeb354` — `build_authority_review_payload`, `build_completion_envelope`, and `build_limited_envelope` independently invoke `project_scan_result_for_external_boundary` before sampling, signing or persistence-envelope construction.

This makes the boundary defensive even if a future/internal caller bypasses the normal post-crawl projection seam. Historical seal algorithms and reader formats are unchanged.

## Intermediate verification and stale expectation

FixList CI `35499222707` on `10798d00d1c0e7cc31a6dfaca3cd4fc67abeb354` proved the new review regressions green but exposed one stale compatibility assertion:

- root scanner regressions: **115 passed**;
- `scanner-api`: **1 failed / 1,992 passed / 18 skipped**;
- lint/typecheck/generated contracts/frontend contract tests/frontend build passed.

The remaining failure was `test_stage2_local_entity_result_authority.py`, which still required the signed authority aggregate to equal the raw internal B13/B14 aggregate. That expectation contradicted the already-approved privacy contract because the external projection correctly removes exact entity IDs, exact page URLs and status-heading provenance.

Commit `f8175c496728d806085056a2b79cb42e5a0fc61c` replaced that raw-equality assertion with stronger external-boundary behavior:

- approved B13/B14 producer version/count/truncation/state diagnostics must survive;
- verified completeness/NAP state remains provable;
- exact entity IDs, exact page URLs, `entity_key`, `page_url`, and `contextual_status_provenance` must not survive the signed authority boundary;
- a verified cross-page NAP conflict retains its field/source-count/provenance evidence while removing the exact entity key.

The test was not weakened; it now asserts the intended privacy/product contract explicitly.

## Exact executable GREEN checkpoint

Exact executable head: `f8175c496728d806085056a2b79cb42e5a0fc61c`.

FixList CI `35499312736` — **SUCCESS** on both jobs:

- immutable checkout: passed;
- root scanner regressions: **115 passed**;
- full `scanner-api`: **1,993 passed / 18 skipped**;
- the three follow-up review regressions passed;
- the strengthened B13/B14 signed-authority privacy assertions passed;
- labelled Stage-1 corpus: `synthetic`, **14 cases / 55 assertions**, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image build: passed, image SHA `sha256:362269f3c43c8c60e57e32edcb8367b024d3da456d6ca1adb95410f40f9f3715`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

CI requested Node 20 but GitHub Actions resolved **Node 20.20.2**. Do not describe this run as Node 20.19.5 runtime evidence.

## Remaining Stage-2 gate

The two material independent-review findings now have RED reproduction, minimal fixes, behavioral coverage and exact-head green CI. Stage 2 is still **not recorded complete** until one fresh independent review covers the corrected stable head and reports no unresolved material finding.

If that review is clean, record B06–B18 complete and begin serialized integration of the existing Stage-3 B19–B24 lanes. If it reports a material issue, reproduce it first, correct the smallest safe surface, and require new exact-head CI.

Keep internal evidence-only B09/B10–B18 data internal unless a deliberate producer → Review → signed authority → persisted rows → customer/card/handoff/export contract is added. Preserve Standard 150, one finite probe budget, robots/DNS/SSRF/redirect/body/deadline controls, exact scan isolation, one active scan/account, cancellation/terminalization, historical readers/signatures, preview privacy and Python Review ranking authority.
