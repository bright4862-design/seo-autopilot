# Stage 2 B09/B16 isolated lane handoff — 2026-09-19

Branch: `agent/stage2-b09-b16-coverage-20260919`

Base checkpoint: Stage-2 PR #303 head `b05fe3993422357959c7755a2eda47a2e635943f`.

This lane owns only feature-specific B09 sitemap-integrity and B16 URL-variant evidence helpers plus regressions. It intentionally does not edit `run_scan`, `SharedCoverageProbeScheduler`, authority/persistence, customer projections, other agent branches, `main`, deployment, or live data.

## Implemented seams

### B09 — sitemap integrity

`scanner-api/app/sitemap_integrity_evidence.py`

- Registers **unsampled, same-origin, in-scope** sitemap targets into the existing `SharedCoverageProbeScheduler` under purpose `sitemap_target`.
- Deduplicates one outbound request identity while retaining up to the scheduler's bounded source-page provenance when the same target is present in multiple sitemap sources.
- Never appends probe targets to assessed pages and returns explicit `assessed_page_count_unchanged=true` plus eligible/registered/truncated diagnostics.
- Classifies only verified target evidence: 404/410, 5xx, explicit noindex, explicit app-shell and observed redirect conflicts can fail; challenge/block/rate-limit, request failure and incomplete HTML remain `not_verified`.
- Projects existing sitemap source diagnostics without fabricating failure provenance. A source whose retrieval failed but whose exact failure reason is not attached remains `not_verified`, even when an aggregate failure bucket exists.
- Projects shared-scheduler budget/deadline/partial coverage as explicit unknown rather than success.

### B16 — URL variants

`scanner-api/app/url_variant_evidence.py`

- Builds bounded slash and case variants while preserving the source URL's raw query string and reserved-escape spelling.
- Does **not** generate scheme/apex-www variants unless the caller supplies a previously verified alias origin. This preserves the no-sibling-host expansion boundary.
- Meaningful-parameter variants must be explicitly supplied as observed/reviewed source→variant pairs; the helper does not invent arbitrary query mutations.
- Registers all variant probes into the existing shared scheduler under purpose `url_variant`; it does not own another request pool.
- A synthetic variant normalizing to the source can pass as normalization evidence, but `published_redirect_claim` is always false. Redirect destination meaning is explicitly deferred to B08.
- A complete independently live variant with distinct final identity can fail as `distinct_live_variant`; canonicalization to the source passes. Challenge/access/request/incomplete evidence remains unknown.
- Partial/exhausted shared-scheduler coverage remains `not_verified`.

## Regression file

`scanner-api/tests/test_stage2_coverage_integrity.py`

Coverage includes:

- unsampled same-origin/scope candidate registration;
- multi-sitemap source provenance on one request identity;
- candidate truncation without assessed-page expansion;
- 404/noindex/redirect/app-shell target conflicts;
- challenge/429/incomplete target unknown states;
- root/source diagnostic fail-closed behavior;
- exact case/slash/query/reserved-escape preservation;
- no implicit apex/www or scheme expansion;
- explicit verified alias generation;
- explicit meaningful-parameter variants;
- same shared scheduler budget;
- `/page` ↔ `/page/` normalization;
- independently live case/query variants;
- canonicalized variants;
- challenged/request-failed variants;
- B08 redirect-meaning handoff;
- scheduler exhaustion and partial coverage staying unknown.

## Shared integration steps still required

These are intentionally left to the serialized Stage-2 integration owner because they touch shared producer interfaces:

1. **Sitemap target provenance producer:** current `load_sitemap_urls` returns page URLs after discovery but does not expose a per-page sitemap-source map. Extend the shared producer to retain the root/child source URL for selected page targets, then pass those entries to `register_sitemap_target_candidates`.
2. **Sitemap source/child failures:** existing diagnostics identify root sources and aggregate failure buckets, but some child failure reasons are not attached to the exact child URL. B09 source completion requires retaining exact root/child URL + outcome/reason so `build_sitemap_source_evidence` can authenticate it instead of leaving it unknown.
3. **Shared fetch orchestration:** after B07 establishes the serialized scheduler/fetch loop, register `sitemap_target` and `url_variant` candidates in that same pool; fetch only through the hardened request provider/robots/deadline path and call the feature classifiers on extracted results.
4. **B16 verified aliases:** pass only aliases already verified by existing landing/scope evidence. Never derive sibling hosts merely from naming convention.
5. **Meaningful parameters:** supply B16 only with parameter variants already observed/reviewed as meaningful. Tracking-only scheduling normalization remains separate from evidence identity.
6. **Authenticated customer output:** this lane does not produce customer-facing repairs. If integration promotes B09/B16 failures into displayed findings, add producer→review→signed authority→persisted rows→verified customer/card/handoff/export tests before calling either requirement source-complete.

## Verification

Draft PR #310 is CI-only and must not be merged. It targets `main` solely because `.github/workflows/ci.yml` currently runs pull-request CI only for PRs whose base is `main`; the branch itself remains based on PR #303's Stage-2 head. Exact-head CI is pending at this checkpoint and must be recorded here before integration.

## Requirement status

- **B09:** feature helper + regressions implemented; shared producer/source-provenance wiring and authenticated customer-output decision remain open. Do not mark source-complete yet.
- **B16:** feature helper + regressions implemented; shared scheduler producer wiring and any customer-output promotion remain open. Do not mark source-complete yet.

No merge, deployment, `main` change, live scan, provider connection, or customer-data mutation is claimed by this lane.
