# Stage 2 B09/B16 isolated lane handoff — 2026-09-19

Branch: `agent/stage2-b09-b16-coverage-20260919`

Base checkpoint: Stage-2 PR #303 head `b05fe3993422357959c7755a2eda47a2e635943f`.

This lane owns only feature-specific B09 sitemap-integrity and B16 URL-variant evidence helpers plus regressions. It intentionally does not edit `run_scan`, `SharedCoverageProbeScheduler`, authority/persistence, customer projections, other agent branches, `main`, deployment, or live data.

## Implemented seams

### B09 — sitemap integrity

`scanner-api/app/sitemap_integrity_evidence.py`

- Registers **unsampled, same-origin, in-scope** sitemap targets into the existing `SharedCoverageProbeScheduler` under purpose `sitemap_target`.
- Deduplicates one outbound request identity while retaining bounded source-page provenance when the same target is present in multiple sitemap sources.
- Never appends probe targets to assessed pages and returns explicit `assessed_page_count_unchanged=true` plus eligible/registered/truncated diagnostics.
- Classifies only verified target evidence: 404/410, 5xx, explicit noindex, explicit app-shell and observed redirect conflicts can fail; challenge/block/rate-limit, request failure and incomplete HTML remain `not_verified`.
- Projects existing sitemap source diagnostics without fabricating failure provenance. A source whose retrieval failed but whose exact failure reason is not attached remains `not_verified`, even when an aggregate failure bucket exists. If the shared producer later attaches an exact source-level reason, known missing/unusable source files may fail while access-limited states remain unknown.
- Projects shared-scheduler budget/deadline/partial coverage as explicit unknown rather than success.
- A bounded target sample can never be described as exhaustive coverage: registration exposes `eligible_unsampled`/`truncated`, and the coverage helper remains `not_verified` when the eligible target universe was truncated.

### B16 — URL variants

`scanner-api/app/url_variant_evidence.py`

- Builds bounded slash and case variants while preserving the source URL's raw query ordering, reserved-escape spelling and the otherwise-easy-to-lose empty query delimiter on path mutations.
- Does **not** generate scheme/apex-www variants unless the caller supplies a previously verified alias origin. This preserves the no-sibling-host expansion boundary.
- Meaningful-parameter variants must be explicitly supplied as observed/reviewed source→variant pairs; the helper does not invent arbitrary query mutations.
- Registers all variant probes into the existing shared scheduler under purpose `url_variant`; it does not own another request pool.
- A synthetic variant normalizing to the source can pass as normalization evidence, but `published_redirect_claim` is always false. Redirect destination meaning is explicitly deferred to B08.
- Canonicalization back to the source passes. Challenge/access/request/incomplete evidence remains unknown. An independently live case/query route is **not** automatically labelled a duplicate: without redirect/canonical or separate equivalence evidence it remains `not_verified`, and explicit noindex remains a policy/judgment state rather than a manufactured duplicate defect.
- Candidate generation records `eligible_candidate_count` and `candidate_universe_truncated`; partial/exhausted/truncated shared-scheduler coverage remains `not_verified`.

## Regression file

`scanner-api/tests/test_stage2_coverage_integrity.py`

Coverage includes:

- unsampled same-origin/scope candidate registration;
- multi-sitemap source provenance on one request identity;
- candidate truncation without assessed-page expansion and without a false full-coverage pass;
- 404/noindex/redirect/app-shell target conflicts;
- challenge/429/incomplete target unknown states;
- root/source diagnostic fail-closed behavior and exact source-level missing-vs-access-limited reasons;
- exact case/slash/query/reserved-escape preservation, including an empty query delimiter;
- no implicit apex/www or scheme expansion;
- explicit verified alias generation;
- explicit meaningful-parameter variants;
- same shared scheduler budget;
- `/page` ↔ `/page/` normalization;
- independently live case/query variants staying unknown without equivalence evidence;
- noindex and canonicalized variant behavior;
- challenged/request-failed variants;
- B08 redirect-meaning handoff;
- URL-variant candidate-universe truncation;
- scheduler exhaustion and partial coverage staying unknown.

## Review-hardening findings corrected in this lane

A fresh lane review found two evidence-truthfulness risks after the first green implementation checkpoint:

1. The scheduler can complete every **selected** probe even when the B09/B16 candidate universe was intentionally capped. The feature helpers now carry universe-size/truncation evidence and refuse to describe that bounded subset as exhaustive coverage.
2. A distinct live 200 URL is evidence that another route exists, not proof that it duplicates the assessed source. B16 now requires redirect/canonical or later independent equivalence evidence before a duplicate-like defect can be promoted; independently live routes remain unknown meanwhile.

The review also added raw empty-query-delimiter preservation to path-variant tests and exact sitemap-source failure attribution for future producer enrichment.

CodeRabbit was manually requested on draft PR #310, but its service reported that the account/repository review request was rate-limited at this checkpoint. That is not treated as an independent-review pass.

## Shared integration steps still required

These are intentionally left to the serialized Stage-2 integration owner because they touch shared producer interfaces:

1. **Sitemap target provenance producer:** current `load_sitemap_urls` returns page URLs after discovery but does not expose a per-page sitemap-source map. Extend the shared producer to retain the root/child source URL for selected page targets, then pass those entries to `register_sitemap_target_candidates`.
2. **Sitemap source/child failures:** existing diagnostics identify root sources and aggregate failure buckets, but some child failure reasons are not attached to the exact child URL. B09 source completion requires retaining exact root/child URL + outcome/reason so `build_sitemap_source_evidence` can authenticate it instead of leaving it unknown.
3. **Shared fetch orchestration:** after B07 establishes the serialized scheduler/fetch loop, register `sitemap_target` and `url_variant` candidates in that same pool; fetch only through the hardened request provider/robots/deadline path and call the feature classifiers on extracted results.
4. **B16 verified aliases:** pass only aliases already verified by existing landing/scope evidence. Never derive sibling hosts merely from naming convention.
5. **Meaningful parameters:** supply B16 only with parameter variants already observed/reviewed as meaningful. Tracking-only scheduling normalization remains separate from evidence identity.
6. **Equivalence evidence:** if a live variant is to become a duplicate/variant defect, integrate a separately authenticated equivalence signal (for example the B10 main-content comparison) rather than inferring equivalence from HTTP 200 alone.
7. **Authenticated customer output:** this lane does not produce customer-facing repairs. If integration promotes B09/B16 failures into displayed findings, add producer→review→signed authority→persisted rows→verified customer/card/handoff/export tests before calling either requirement source-complete.

## Verification

Exact code/test head before this documentation update: `6e8cecf9edb06b0385b55079c31cc8d6aa673d5c`.

FixList CI run: https://github.com/bright4862-design/seo-autopilot/actions/runs/35462510437 — **success**.

Fresh results on that exact code head:

- root scanner regressions: **115 passed**;
- scanner-api: **1,844 passed / 18 intentional skips**;
- `test_stage2_coverage_integrity.py`: **24 passed**;
- lint: passed;
- typecheck: passed;
- generated release contracts: passed;
- frontend contract tests: passed;
- frontend production build: passed;
- labelled Stage-1 corpus stayed explicitly `synthetic`, 14 cases / 55 assertions, and the full 30-site gate stayed `not_assessed`;
- frozen revision check: passed at `01ebe8e90df1e6bd`;
- production scanner image build: passed.

Draft PR #310 was temporarily based on `main` only because `.github/workflows/ci.yml` currently runs pull-request CI only for PRs whose base is `main`. It is CI/review-only and must not be merged. After exact-final-head verification it should be retargeted to the Stage-2 integration branch so the review diff contains only this lane.

## Requirement status

- **B09:** feature helper + regressions implemented and broad-CI verified; shared producer/source-provenance wiring and authenticated customer-output decision remain open. Do not mark source-complete yet.
- **B16:** feature helper + regressions implemented and broad-CI verified; shared scheduler producer wiring, optional equivalence integration, and any customer-output promotion remain open. Do not mark source-complete yet.

No merge, deployment, `main` change, live scan, provider connection, or customer-data mutation is claimed by this lane.
