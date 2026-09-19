# Stage 2 serialized integration checkpoint — 2026-09-19

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303

Exact integrated head before this checkpoint document: `eaca32004ca06250b8442c72422a9fb349d5ccb5`.

Stage-1 production/release source remains separate. Fresh GitHub main was verified at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`; this Stage-2 branch has not been merged to main, deployed, promoted, or live-accepted.

## Integrated lane deltas

The serialized integration branch now contains the completed isolated feature-lane deltas, merged one at a time:

1. B07 orchestration adapter and focused safety regressions from `agent/stage2-b07-producer-20260919` head `0ca2eeabe89642bacea81b36b4efb98c09c7737e`, integrated through PR #318. Stage-2 merge commit: `3cdd464504c114a170222efc5fceffd200043fc4`.
2. B09 sitemap-integrity and B16 URL-variant helpers/regressions from `agent/stage2-b09-b16-coverage-20260919` head `d58a06b93da5625958eeb68691eeffae88a3ba2a`, integrated through PR #310. Stage-2 merge commit: `6d2fb78739d86fcba062c38fd6b08b433e5c715f`.
3. B08 redirect-destination meaning helpers/regressions from `agent/stage2-b08-redirect-meaning-20260919` head `bc4f53e2669d0e35f9f0bb752cce31811b334d25`, integrated through PR #309. Stage-2 merge commit: `b2eae38ae9cdd02af390d8647cebabae1279885e`.
4. B10–B15/B17–B18 evidence helpers/regressions from `agent/stage2-b10-b18-acceptance-20260919` head `7921ad254b91e850c71eee0e3aba7c3f54750cfd`, integrated through PR #311. Stage-2 merge commit/head: `eaca32004ca06250b8442c72422a9fb349d5ccb5`.

The lane PRs were integration surfaces only; they were not merged to `main`.

## Fresh combined verification

FixList CI run `35466262405` executed exact head `eaca32004ca06250b8442c72422a9fb349d5ccb5` and passed both jobs.

- root scanner suite: **115 passed**;
- `scanner-api`: **1,882 passed / 18 intentional skips** (1,900 collected);
- B07 orchestration tests: **8 passed**;
- B08 redirect-meaning tests: **6 passed**;
- B09/B16 focused tests were included and passed;
- B10–B18 focused tests were included and passed;
- labelled Stage-1 corpus remained explicitly `synthetic`: 14 cases / 55 assertions;
- genuine full 30-site gate remained `not_assessed`;
- frozen scanner revision check passed at `01ebe8e90df1e6bd`;
- production scanner image build passed;
- lint, typecheck, generated contracts, frontend contracts and production frontend build passed.

This proves the integrated helpers coexist without regression. It does **not** prove B07–B18 source-complete because the shared producer still does not invoke most new helpers.

## Shared integration work still open

### B07 — producer path

`scanner-api/app/active_soft404_orchestration.py` is present and tested, but `scanner.py::run_scan` still needs to invoke it using the already-created `SharedCoverageProbeScheduler`, effective origin/path scope, existing robots policy, and `fetch_and_extract(... request_provider=scheduler.fetch_once)` hardened request path. The resulting bounded baseline rows must be attached under `coverage_probe_evidence.soft_404_baselines` before postprocessing. Synthetic probes must never enter `pages`, `pages_crawled`, assessed/eligible denominators, or discovery counts.

Producer-path positive and challenge/429/robots/budget/deadline regressions remain required. Existing downstream active-soft404 authority/customer tests must then be exercised from the real producer path.

### B08 — shared customer wording

The current `redirect_wrong_destination` customer copy in `scanner.py` still describes only a catch-all homepage. B08 can now verify unrelated/catch-all sections too. The shared copy must become evidence-led and generic (for example, “unrelated or catch-all destination”), with a focused regression. Do not change the redirect evidence version or historical signatures.

### B09 — sitemap producer provenance and shared fetch

The helper is integrated, but `run_scan` must retain per-target sitemap-source provenance and exact source/child failure reasons, register unsampled in-scope targets under purpose `sitemap_target` on the **same** scheduler, fetch through the existing hardened request provider, and keep challenged/robots/budget/deadline/incomplete states unknown. Probe-only sitemap targets must stay outside assessed-page counts.

### B16 — URL variant producer wiring

The helper is integrated, but `run_scan` must derive/register only bounded exact-identity variants allowed by the spec. Verified alias origins must come from already-authenticated landing/scope evidence; meaningful parameter variants must be observed/reviewed rather than invented. Synthetic normalization cannot become a published-redirect claim. A distinct live route remains unknown unless separate authenticated equivalence evidence (for example B10) proves equivalence.

### B10–B15/B17–B18 — extraction and authenticated projection

Pure evidence contracts are integrated. Shared producer wiring remains for accepted substantive main text, crawl-depth/navigation provenance, bounded paired raw/rendered hub evidence, local entity/context/status envelopes, contextual temporal/current-intent evidence, truthful transfer/decoded/inline byte measurements, and optional CrUX/GSC states. Disconnected, stale and unavailable provider evidence must stay explicit and non-fabricated.

If any of these fields create or change customer-visible findings/counts, integration must add real producer → review → signed authority → persisted rows → verified customer/card/handoff/export regressions before the requirement is source-complete.

## Integration invariants

- One shared finite coverage scheduler/request pool only; no feature receives a second hidden request budget.
- Standard 150 assessed-page cap and truthful assessed denominators remain unchanged by probe-only evidence.
- Existing DNS/SSRF/redirect/body/deadline/robots protections remain authoritative.
- Unknown/unavailable evidence remains unknown and cannot be converted to pass/fail merely to improve coverage.
- Historical signatures/readers and preview privacy remain unchanged.
- Python review remains the canonical decision/ranking authority.
- Stage 3 shared integration does not begin until Stage 2 producer/customer wiring is complete, independently reviewed, and exact-head CI green.

## Next serialized slice

1. Wire B07 into the actual `run_scan` probe phase first and add producer-path regressions.
2. Update B08 shared wording with a focused regression.
3. Wire B09/B16 registrations and fetch/classification through that same scheduler.
4. Complete B10–B18 producer/extraction/authenticated customer wiring.
5. Run focused suites after each slice, then full exact-head FixList CI.
6. Obtain independent review and fix every material finding with a reproducing regression.
7. Only then update B06–B18 to source-complete and begin Stage-3 shared integration.

No production release, live scan, provider connection, schema broadening, secret change, Premium enablement or Grok enablement is authorized by this checkpoint.