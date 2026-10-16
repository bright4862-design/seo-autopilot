# Stage 2 shared `run_scan` integration checkpoint — 2026-09-19

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`
PR: #303

## Exact integrated code checkpoint

- Code/test commit: `ca70b7380011e93437fc993185e511a5847618e6` — `feat(scanner): wire shared Stage 2 probes into run_scan`
- Integration proof workflow: `Stage2IntegrationRun` run `35469815094` — **success**
- Focused Stage-2 integration regressions: **51 passed**
- Root scanner regressions: **115 passed**
- Full `scanner-api`: **1,901 passed / 18 intentional skips**
- Python compile check: passed
- `git diff --check`: passed

The temporary integration workflow/patch script used only to execute the serialized shared-interface edit were deleted by the verified commit and are not part of the resulting product source.

## What this checkpoint integrates

1. **Real Standard-150 producer wiring for the shared Stage-2 probe pool.** After the existing B06 unsampled-link registration/fetch, `run_scan` now invokes `run_stage2_shared_probe_orchestration` for the Standard-150 budget (`max_pages >= 150`) using the same `SharedCoverageProbeScheduler`, the canonical scan origin/effective scope, current robots policy, and `fetch_and_extract` hardened request path. No second request pool is created and probe-only URLs are not appended to assessed `pages`.
2. **Fail-closed hardened fetch boundary.** Active B07/B09/B16 probes run only when the active fetch callback can accept both the robots policy and scheduler request-provider contract. Legacy/injected callbacks that cannot enforce the shared provider do not receive active probes; the evidence records `not_verified` instead of bypassing the finite request pool. Basic/quick/deep behavior and their historical request-identity tests remain unchanged.
3. **B07 grouped provenance hardening.** `group_findings` no longer lets a versioned lead/sample lend `observed_evidence_version` or `verified_observed_pages` to an unversioned member. Group-level observed authority is restored only when every grouped member carries the same non-empty version, using `uniform_observed_group_provenance`.
4. **B08 customer wording generalized to the evidence contract.** Wrong-destination repairs now describe an “unrelated or catch-all destination,” not only homepage collapse, matching the B08 redirect-meaning classifier while preserving the existing repair rule/identity.
5. **Compatibility regression.** The first full integration attempt exposed legacy monkeypatched fetch callbacks and lower scan modes that intentionally do not implement the active-probe request-provider boundary. The final patch keeps those paths compatible while retaining the hardened Standard-150 contract; the full scanner suite is green without weakening assertions.

## Requirement status

- **B06:** source-complete from the earlier checkpoint.
- **B07:** the missing real producer seam is now connected and its shared-budget/provenance behavior is regression-covered. Downstream active-soft404 authority/customer projection was already covered by the earlier B07 integration tests. Independent combined review and normal exact-head FixList CI still gate closing B07/Stage 2.
- **B08:** classifier plus authenticated downstream path existed on the lane; shared customer copy is now reconciled on the integration branch. Combined review/CI still required.
- **B09/B16:** feature modules now have a real shared scheduler/fetch orchestration seam on Standard 150. Exact sitemap root/child provenance enrichment and any customer-visible promoted findings still require authenticated integration before source-complete status.
- **B10–B15/B17–B18:** helper contracts are present but actual producer/extraction/authenticated customer wiring remains open. Do not mark these requirements or Stage 2 complete yet.

## Next serialized engineering slice

Complete B10–B15/B17–B18 producer integration without inventing evidence:

- authenticated sanitized main-text evidence for B10;
- stable sample-scoped crawl-depth/navigation provenance for B11;
- bounded raw/rendered five-hub pairing for B12;
- applicable local entity/status/NAP envelopes for B13/B14;
- explicit current-intent + scoped temporal evidence for B15;
- measured transfer/decoded/inline-byte inputs for B17; CrUX remains optional/disconnected unless actually authorized;
- GSC remains optional and disconnected/stale/unavailable unless an owner-authorized current provider response exists.

Any newly customer-displayed evidence/counts/findings must be proven through producer → Review → signed authority → persisted rows → verified customer/card/handoff/export. Missing, challenged, stale, disconnected or otherwise unverified evidence stays unknown. Preserve Standard 150 assessed-page cap, shared finite probe budget, robots/DNS/SSRF/redirect/body/deadline limits, historical signatures and preview privacy.

After that slice, obtain independent review and normal exact-head FixList CI before recording Stage 2 source-complete or starting shared Stage-3 integration.
