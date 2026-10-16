# Stage 2 review-hardening checkpoint — 2026-09-19

This checkpoint continues the approved Stage 2 coverage work on PR #303 without moving or rewriting the Stage-1 release history.

## Exact verified source before this documentation commit

- Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`
- Verified code/test head: `1ce6ddfff69abdb850bc6a531767d95a908b1371`
- FixList CI: https://github.com/bright4862-design/seo-autopilot/actions/runs/35459245485
- Root scanner tests: **115 passed**
- Scanner API: **1,820 passed / 18 intentional skips**
- Lint, typecheck, generated contracts, frontend contracts/build, frozen-revision verification and production scanner-image build: passed
- Stage-1 corpus remains labelled `synthetic`; the genuine provenance-labelled 30-site full-blueprint gate remains `not_assessed`.

## Review findings corrected in this slice

### Probe diagnostic truncation

`SharedCoverageProbeScheduler` now tracks the exact number of observation records offered to the bounded diagnostic sample. `record_skipped`, `record_exhausted` and completed results therefore all participate in `observation_samples_truncated` truthfully. The retained observation list remains capped; no request budget, body limit, deadline or assessed-page behavior changed.

Regression coverage proves more than 40 robots-skipped synthetic candidates reports truncation while exactly 40 does not.

### Mixed evidence provenance at canonical persistence grouping

The canonical repair merge no longer inherits `observed_evidence_version` or `verified_observed_pages` from whichever member happens to be the strictest lead. Group-level provenance is restored only when **every** member has the same non-empty evidence version. Mixed active/passive evidence therefore fails closed instead of authenticating a passive URL with an active soft-404 proof.

Regression coverage proves the mixed versioned/unversioned case drops group-level authority and that a uniform active-evidence group preserves the exact verified URL union.

## Independent review status

- The CodeRabbit truncation finding is fixed, replied to and resolved.
- The mixed-provenance review finding remains open because the equivalent `scanner.py::group_findings` grouping path still needs the same all-members-same-version rule. The persistence merge half is fixed and regression-covered; do not resolve the review thread until the scanner grouping path is corrected and exact-head CI is green.

## Requirement status

- **B06:** source-complete and CI-verified on PR #303; not merged/deployed/live.
- **B07:** active evidence engine and authenticated downstream projection are implemented. Real `run_scan` producer orchestration remains open, so B07 is not source-complete.
- **B08–B18:** open after the B07 producer dependency, with B09/B16 required to reuse the same finite scheduler.
- **B19–B24 and B25–B28:** open.

## Exact next actions

1. Correct `scanner.py::group_findings` so inherited provenance is removed before grouping and restored only if every member carries the same non-empty `observed_evidence_version`; add a direct grouping regression and resolve the remaining review thread only after green exact-head CI.
2. Wire B07 producer orchestration into `run_scan`: derive deterministic root/path-family synthetic candidates from canonical origin/effective scope and observed page families; robots-check them; fetch only through the existing `SharedCoverageProbeScheduler` and hardened request provider; classify challenge/429/robots/budget/deadline states as unknown/not-verified; populate `coverage_probe_evidence.soft_404_baselines` with bounded evidence; never append synthetic URLs to assessed pages.
3. Add producer regressions proving positive active-baseline discovery and unknown-state handling, and proving Standard 150 `pages`/`pages_crawled` and eligible assessed denominator are unchanged by synthetic probes.
4. Require independent review and exact-head CI before changing B07 to source-complete.
5. Continue B09/B16 on the shared pool, then B08 and B10–B18, followed by Stages 3 and 4.

## Release boundary

Nothing in this checkpoint is merged to `main`, staged, deployed or live-accepted. Do not repurpose historical scan summaries as the 30-site acceptance gate. Preserve all existing scanner safety, robots ownership, DNS/SSRF/redirect/body/deadline limits, durable admission/cancellation, authority integrity, historical signatures and preview privacy.
