# Stage 2 B17/B18 disconnected provider result integration

Status: implemented on `agent/full-blueprint-stage2-coverage-b06-20260919`; source behavior is CI-verified, final Stage-2 independent review is still open.

## Scope

This slice completes the ordinary Standard-150 no-provider path for the optional B17 CrUX and B18 GSC contracts without granting provider access or accepting browser/task-supplied metrics.

The shared post-crawl result now carries a deterministic `connected_provider_evidence_v1` bundle for the exact retained assessed set when no authenticated provider connection exists. The bundle is also included in `technical_audit_summary`, so the existing authority review payload authenticates the explicit disconnected state. It does not create a repair, customer card, score change, network request, external-account connection, or new request budget.

The disconnected bundle deliberately has no durable `scan_id`, no provider source `scan_id`, no metrics and `provider_data_admitted=false`. A later connected-response path must still use `build_crux_scan_evidence` / `build_gsc_scan_evidence` after an exact durable scan id is known. Those builders continue to require owner authorization, exact scan identity, current observation time, and—GSC specifically—exact membership in the retained Standard-150 URL set. Missing, stale, disconnected, unavailable or conflicting provider evidence fails closed.

## Changed files

- `scanner-api/app/stage2_connected_provider_evidence.py`
  - adds the deterministic disconnected bundle;
  - records provider state, adapter versions, no-coverage claim and retained assessed URL count without retaining a hidden URL list;
  - leaves connected/stale evidence admission behind the existing exact-scan builders.
- `scanner-api/app/indexability_postprocess.py`
  - attaches the disconnected bundle to the shared result and `technical_audit_summary` from the final retained page set;
  - does not add findings or change health score.
- `scanner-api/tests/test_stage2_provider_result_integration.py`
  - proves no metrics/scan identity are fabricated;
  - proves the shared result/technical summary carry the disconnected state;
  - proves the authority review payload preserves that state while still refusing to borrow the later durable scan id.

## Verification

Exact executable SHA: `910206d34a298ab840cf610542a55809a76b0115`.

FixList CI: `35490060294` — SUCCESS on both jobs.

Fresh CI evidence:

- immutable checkout verified `910206d34a298ab840cf610542a55809a76b0115`;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,978 passed / 18 intentional skips**;
- new shared provider-result regressions: **3 passed**;
- existing connected-provider contract regressions: **7 passed**;
- direct B17 transfer-body regressions: **4 passed**;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:afc5d05e3a0c36639b02c40de8545d87d3d897711969c17e13029f01c6ee9ba1`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow resolved Node `20.20.2`; this checkpoint is not evidence of Node `20.19.5` execution.

## Requirement coverage

### B17

Direct transfer-body bytes are measured at the hardened raw-response boundary before content decoding, remain distinct from decoded HTML and inline bytes, cannot be spoofed by a remote response header, and stay unknown for access-limited pages. Optional CrUX absence is now explicitly authenticated as disconnected on the ordinary scan path. Controlled connected/stale/unavailable CrUX responses remain covered by the pure exact-scan adapter tests; no live provider connection is claimed.

### B18

The ordinary scan path now authenticates GSC as disconnected instead of silently omitting provider state. Controlled connected/stale/unavailable GSC responses remain covered by the exact-scan adapter tests, including exact retained-URL membership, conflict rejection and the Standard-150 ceiling. No live GSC connection or traffic/indexing claim is made.

## Remaining Stage-2 gates

This does not by itself make Stage 2 complete. Before shared Stage-3 integration:

1. resolve any remaining B09/B10 downstream exposure/privacy decisions only if those evidence types are actually promoted to customer-visible findings;
2. obtain a fresh independent review of the combined B06–B18 source shape and fix any material findings with regressions;
3. run fresh exact-head combined CI after any review correction;
4. keep provider-specific live/account claims out unless an owner-authorized connection is actually available and verified.

No production deployment, admission mutation, worker promotion, live scan, schema change, secret change, provider connection or customer-data mutation belongs to this checkpoint.
