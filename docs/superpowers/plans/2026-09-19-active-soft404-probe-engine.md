# B07 active soft-404 probe engine plan

Status: implementation in progress on `agent/full-blueprint-stage2-coverage-b06-20260919` / PR #303. The evidence engine checkpoint is committed; scanner orchestration, signed persisted output and customer-output acceptance are still open. Do not mark B07 source-complete until every acceptance item below is green on one exact head.

## Dependency and invariant

B07 consumes the B06 `SharedCoverageProbeScheduler`. It must not create another request pool or alter the Standard 150 assessed-page limit. Synthetic missing-path probes are follow-up evidence only: they stay outside `pages`, share the crawler's finite frontier-request ceiling, reuse actual request identities, and retain the existing safe DNS/SSRF/redirect/body/deadline/robots controls. Budget/deadline/robots/access exhaustion remains unknown/not-verified.

The approved B07 contract is conservative: deterministic non-existent paths establish a baseline only from complete accepted responses. Challenge/block/rate-limit/incomplete responses cannot become error-page baselines. Redirected synthetic probes remain unknown here; redirect meaning is B08 evidence rather than something B07 should infer.

## Engine checkpoint completed

Source checkpoint: `62e9af3029f3ff35c76deb2213dc4124b0d50314` (`feat(scanner): add active soft-404 probe evidence engine`).

Implemented in `scanner-api/app/coverage_probes.py`:

1. `SOFT_404_PROBE_VERSION = soft_404_probe_v1_active_baseline` and purpose-version authentication for scheduler observations.
2. Deterministic same-origin/scope-preserving synthetic path candidates: one scope-root probe plus at most three representative parent-directory probes per observed page-template family.
3. Stable `__fixlist-missing-<hash>` paths avoid observed URLs, never expand to sibling hosts and carry bounded synthetic/page-family/path-family provenance.
4. A complete accepted-response gate: 2xx, usable HTML, no fetch error, no raw truncation, no redirect hop and no access challenge/block/rate-limit.
5. Missing-page intent evidence from bounded title/H1/meta fields, with the synthetic marker stripped before comparison.
6. Baseline classification: hard 404/410 is a correct missing response (`pass`); verified 2xx missing-intent HTML establishes a soft-404 baseline (`fail`); generic 2xx, incomplete content, challenges and transport uncertainty remain `not_verified`.
7. Assessed-page comparison requires both missing-page intent and corroborating similarity to a verified active baseline. Generic app shells and unknown baselines cannot create a positive result.
8. Bounded signature tokens support deterministic comparison without persisting response-body copy.
9. Scheduler metadata is allowlisted and bounded; untrusted metadata cannot silently enter authenticated observations.

Behavioral regressions in `scanner-api/tests/test_coverage_probes.py` cover request-identity reuse, the shared request ceiling, deterministic scoped family candidates, correct hard-missing behavior, challenge/incomplete rejection, no positives from unknown/generic baselines, positive intent+similarity matching and version/provenance metadata.

Exact source verification: [FixList CI 35452713440](https://github.com/bright4862-design/seo-autopilot/actions/runs/35452713440), success at `62e9af3029f3ff35c76deb2213dc4124b0d50314`. Scanner suite: **1,812 passed / 18 intentional skips**. Scanner lint/typecheck, generated-contract checks, labelled synthetic acceptance corpora, frozen-revision check and production scanner-image build passed. The frontend/deploy contract job also passed.

This checkpoint does **not** change persisted or customer-displayed soft-404 output. Therefore it is an engine foundation, not B07 completion.

## Required integration sequence

1. In the real `run_scan` path, derive B07 candidates from the canonical scan origin and effective scope/start path plus actually observed page-template families.
2. Register every candidate as `soft_404_baseline` on the existing shared scheduler. Do not instantiate another scheduler or increase the assessed-page cap.
3. Apply the existing robots/ownership policy to every synthetic path before request. Owner-only robots override behavior must remain exactly the existing contract.
4. Fetch through the existing hardened scan request path with `request_provider=probe_scheduler.fetch_once` (or the exact equivalent already used by B06), so safe DNS/SSRF checks, redirect validation, decoded-body limits, shared deadline and shared request accounting remain authoritative. Redirect/retry requests spend that same pool.
5. Run normal evidence/access classification on each probe. Challenge/block/rate-limit/incomplete/truncated responses must be recorded as unknown/not-verified, never as a baseline.
6. Build the active baseline record and, only for a verified active baseline, attach bounded `soft_404_signature_tokens`; record the exact B07 version and synthetic provenance in the scheduler observation.
7. Compare complete accepted assessed pages against verified active baselines and attach bounded active evidence to the page. Synthetic probe URLs themselves must never enter the assessed-page collection or its denominator.
8. Integrate with `indexability_quality.annotate_indexability_quality` compatibly: an active fail can add `active_baseline_match`; active unknown must not erase or upgrade historical passive information. Do not remove the passive heuristic used by historical/current readers.
9. In `build_indexability_quality_findings`, authenticate active findings with `observed_evidence_version=SOFT_404_PROBE_VERSION` and verified observed assessed-page URLs. Preserve historical signatures and fallback behavior for reports that predate B07.
10. Add a real producer regression using `run_scan` through review → canonical authority → persisted rows → verified customer/chat/card/handoff/export helpers. Prove the active soft-404 finding and its counts/version/provenance survive reload, while the synthetic baseline never becomes an assessed affected page.
11. Add negative end-to-end cases for 429/challenge, robots rejection, shared-budget exhaustion and deadline exhaustion: active coverage is unknown, no active finding is manufactured, and existing passive compatibility remains deterministic.
12. Assert the Standard 150 assessed-page cap is unchanged with active probes enabled.
13. Run the exact-head full CI gate and independent review. Resolve findings with reproducing regressions before marking B07 source-complete.

## Acceptance boundary

B07 becomes source-complete only when the real scanner producer emits the evidence, authority/persistence authenticate it, all verified customer surfaces reconstruct it, unknown states remain unknown, and exact-head CI/review are green. Engine unit tests alone are insufficient.

After B07, continue B09 sitemap integrity and B16 URL variants on the same scheduler; then B08 redirect-meaning evidence using retained redirect observations. Continue B10–B15/B17–B18, then Stage 3 B19–B24 and Stage 4 B25–B28 in the approved dependency order.

Do not merge PR #303 while the Stage-1 exact SHA remains in its guarded production cutover. Nothing in this plan authorizes describing branch, staged or 0%-traffic artifacts as live.