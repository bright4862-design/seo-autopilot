# Stage 2 serialized integration checkpoint — 2026-09-19

Branch: `agent/full-blueprint-stage2-coverage-b06-20260919`

PR: #303

Stage-1 production/release source remains separate. Fresh GitHub main remains outside this later-stage branch; nothing in this checkpoint authorizes or performs production publication, promotion, admission mutation, live scanning, schema broadening, Premium enablement, or Grok enablement.

## Integrated lane deltas

The serialized integration branch contains the isolated Stage-2 feature-lane deltas, integrated one at a time rather than merged directly to `main`:

1. B07 orchestration adapter/safety regressions from `agent/stage2-b07-producer-20260919` head `0ca2eeabe89642bacea81b36b4efb98c09c7737e`.
2. B09 sitemap-integrity and B16 URL-variant helpers/regressions from `agent/stage2-b09-b16-coverage-20260919` head `d58a06b93da5625958eeb68691eeffae88a3ba2a`.
3. B08 redirect-destination meaning helpers/regressions from `agent/stage2-b08-redirect-meaning-20260919` head `bc4f53e2669d0e35f9f0bb752cce31811b334d25`.
4. B10–B15/B17–B18 evidence helpers/regressions from `agent/stage2-b10-b18-acceptance-20260919` head `7921ad254b91e850c71eee0e3aba7c3f54750cfd`.

B06 remains the existing source-complete shared scheduler/internal-link foundation on this line.

## Shared finite-pool orchestration added in the serialized integration

The integration branch now contains `scanner-api/app/stage2_shared_probe_orchestration.py`, a producer adapter that composes B07, B09 and B16 through the **one already-owned `SharedCoverageProbeScheduler`**.

The adapter:

- reads the scheduler's existing remaining request capacity through `stage2_probe_budget.py`; it never creates or enlarges a feature-local allowance;
- derives deterministic B07 synthetic missing-page candidates;
- consumes exact B09 target→sitemap provenance retained by current sitemap discovery, while leaving missing provenance explicitly incomplete rather than inventing a source URL;
- derives only bounded B16 exact-identity variants, taking sibling/alias origins only when supplied as already verified and meaningful parameters only when supplied as explicitly observed/reviewed;
- allocates candidate starts across `soft_404_baseline`, `sitemap_target`, and `url_variant` before follow-up I/O, so an earlier purpose cannot silently hide later eligible work;
- registers all selected B07/B09/B16 candidates on the same scheduler before the first follow-up request;
- fetches exclusively through the existing hardened page path with `probe_scheduler.fetch_once` as request provider, so redirect hops spend the same finite request pool;
- applies the existing robots policy before B09/B16 requests; B07 continues to apply the same policy inside its existing helper;
- records challenge, 429, robots denial, request failure, shared-budget exhaustion and deadline exhaustion as unknown/not-verified;
- never appends synthetic/probe-only URLs to assessed `pages` and returns an explicit before/after assessed-page invariant;
- attaches bounded `soft_404_baselines`, sitemap evidence/coverage/provenance, URL-variant evidence/coverage and the allocation contract to one scheduler-summary-compatible evidence envelope.

A follow-up hardening found that the scheduler records an intentional robots skip in its `skipped` counter rather than `not_verified`. The feature coverage layer now explicitly checks its classified evidence rows so a robots-denied/unverified target cannot be mislabeled as a coverage pass.

## New behavioral regressions

`scanner-api/tests/test_stage2_shared_probe_orchestration.py` adds five network-free producer-adapter regressions:

1. B07/B09/B16 candidates are registered before first follow-up I/O; one scheduler is used; verified soft-404, sitemap-404 and harmless slash-normalization evidence are produced without changing assessed pages.
2. A one-request shared remainder allocates only one candidate start and keeps unselected B09/B16 candidate universes explicit/truncated/not-verified rather than claiming coverage.
3. Robots-denied sitemap evidence is explicit unknown and does not become a coverage pass.
4. Sitemap 429 and URL-variant challenge evidence remain unknown.
5. Deadline exhaustion causes no fetch and leaves B07/B09/B16 coverage unknown.

## Exact verification

Exact code/test head: `4d53c33edb5a2f028af26c732172123c11cb20ce`.

FixList CI run: `35468420878` — **SUCCESS on both jobs**.

Fresh evidence from that exact checkout:

- immutable checkout confirmed `4d53c33edb5a2f028af26c732172123c11cb20ce`;
- root scanner suite: **115 passed**;
- `scanner-api`: **1,896 passed / 18 intentional skips** (1,914 collected);
- new shared Stage-2 orchestration suite: **5 passed**;
- existing B07/B08/B09/B16/B10–B18 suites remained green;
- labelled Stage-1 corpus remained explicitly `synthetic`: **14 cases / 55 assertions**;
- genuine full 30-site gate remained **`not_assessed`**;
- frozen scanner revision `01ebe8e90df1e6bd` passed;
- production scanner-image build passed;
- lint, typecheck, generated release contracts, frontend contract tests and frontend production build passed.

This is meaningful integrated producer-adapter evidence, but it does **not** make Stage 2 source-complete because the real `scanner.py::run_scan` call site and later producer/customer surfaces are still open.

## Remaining serialized Stage-2 work

### 1. Wire the adapter into real `run_scan`

Invoke `run_stage2_shared_probe_orchestration(...)` after the existing B06 unsampled-internal-link slice using the already-created scheduler, canonical/effective origin and scope, current robots policy, current discovered sitemap URLs/diagnostics, and existing hardened `fetch_and_extract` path. The returned envelope can replace the later scheduler snapshot because it preserves the scheduler-summary keys and adds Stage-2 evidence.

Add a direct real-`run_scan` regression proving positive + robots/challenge/429/budget/deadline behavior and that synthetic/probe-only URLs never change Standard 150 assessed-page counts/denominators.

### 2. Fix grouped observed provenance in `scanner.group_findings`

The current implementation still filters blank evidence versions before checking agreement. A versioned member can therefore lend group-level `observed_evidence_version` / `verified_observed_pages` to an unversioned member. Strip sample-inherited observed provenance and restore it only through `uniform_observed_group_provenance(...)`, which already requires the same non-empty version on **every** grouped member. Add a direct `group_findings` regression.

### 3. Generalize B08 customer wording

The shared `redirect_wrong_destination` copy still describes only homepage catch-all behavior. B08 can prove unrelated sections too. Change the title/explanation/recommendation/group text to evidence-led “unrelated or catch-all destination” language without changing historical evidence versions/signatures, and add a focused regression.

### 4. Complete B10–B15/B17–B18 real producer/authenticated delivery

The pure evidence contracts are integrated, but real production evidence still needs to supply accepted substantive main text, navigation/depth, bounded raw/rendered hub pairs, local entity/context/status, scoped freshness/current intent, truthful transfer/decoded/inline byte measurements, and explicit optional CrUX/GSC disconnected/stale/unavailable states.

Any newly displayed evidence/count/finding must be proven through real producer → review → signed authority → persisted rows → verified customer/card/handoff/export readers before the corresponding requirement is source-complete.

### 5. Independent review + exact-head combined CI

After the remaining shared wiring, run focused regressions, the full exact-head FixList CI, and independent review. Fix every material finding with a reproducing regression. Only then mark B06–B18 source-complete and begin shared Stage-3 integration.

## Invariants retained

- exactly one finite Stage-2 follow-up scheduler/request pool;
- Standard 150 assessed-page cap and truthful denominators unchanged by probe-only evidence;
- DNS/SSRF/redirect/body/deadline/robots rules remain authoritative;
- unknown/unavailable evidence remains unknown;
- exact published evidence identity, historical signatures/readers and preview privacy remain compatible;
- Python Review remains canonical decision/ranking authority;
- no production release/live acceptance is claimed here.
