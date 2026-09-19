# Stage 4 B25–B28 isolated lane handoff — 2026-09-19

Branch: `agent/stage4-b25-b28-compat-release-20260919`

Lane base: Stage-2 PR #303 checkpoint `b05fe3993422357959c7755a2eda47a2e635943f`.

CI/review-only draft PR: #317. **Do not merge it directly.** The branch intentionally remains isolated from Stage-2/Stage-3 shared integration; the serialized integrator should transplant only this lane delta after B06–B24 settle.

## Authoritative requirement mapping

The approved blueprint's final register names the requirements as:

- **B25** exact named synthetic corpus plus genuine provenance-labelled 30-site baseline/candidate gate;
- **B26** own-site getfixlist finding reproduction/fixes against the intended release;
- **B27** existing GEO and historical compatibility;
- **B28** actual exact-source deployment and live acceptance.

The automation assignment described the same Stage-4 concerns in a slightly different B25/B26/B27 order. This lane covers all four concerns without changing the approved register or shared runtime contracts.

## Implemented isolated contracts

### B27 / compatibility boundary

`scripts/stage4EvidenceCompatibility.mjs` defines a read-only fail-closed compatibility policy:

- all historical authority seals remain readable under historical reconstruction semantics;
- the current identity seal requires the exact published-route identity and coverage versions;
- known Stage-2 observed evidence versions are explicitly registered but do not become authoritative merely by being registered;
- observed evidence requires a bounded non-empty `verified_observed_pages` set;
- unknown authority, identity, coverage or observed-evidence versions fail closed.

Regressions in `tests/frontend/stage4EvidenceCompatibility.test.mjs` read the frozen historical HMAC fixture and prove the compatibility helper neither rewrites the fixture objects nor changes the fixture file bytes.

`tests/frontend/stage4HistoricalReaderContract.test.mjs` also checks the real V6 customer reader and Grok reader still list every historical authority version plus `standard_review_snapshot_hmac_identity_v1`, and that both readers contain a fail-closed accepted-version boundary.

**Integration hook:** the serialized authority/customer integrator must use this version registry (or an equivalent reviewed shared implementation) when new Stage-2/3 evidence becomes signed customer evidence. This lane intentionally does not modify authority/persistence shared writers or customer reader reconstruction code.

### B25 / named synthetic and genuine 30-site gates

The existing Stage-1 named corpus remains the source of deterministic named-host acceptance. `tests/frontend/stage4NamedCorpusContract.test.mjs` pins:

- Pretto;
- Center Street Lending;
- `www.ikessandwich.com`;
- `locations.ikessandwich.com`;
- getfixlist;
- Ironwood 200/403/truncated access-limited cases;
- explicit `synthetic` provenance;
- `full_30_site_gate=not_assessed`;
- actual Python corpus production plus `scripts/assertCorpusRun.mjs` execution in FixList CI.

New `scripts/assertBlueprint30SiteGate.mjs` implements the separate full-blueprint gate. The tracked 30-row renderer-risk manifest is accepted only as the canonical **roster**. A pass requires exactly 30 paired baseline/candidate artifacts where each artifact is explicitly `captured`, Standard 150, source/fingerprint/time/scope/policy/evidence-bundle identified. Baseline and candidate must be distinct ordered captures under the same scope and policy. Every new candidate artifact requires an evidence-backed independent adjudication. Historical summaries, synthetic data, test fixtures, wrong/partial rosters and 29/30 cohorts cannot pass.

`tests/frontend/stage4Blueprint30SiteGate.test.mjs` proves those fail-closed states. It intentionally does not create a unit-test record that can be mistaken for a genuine passing corpus.

**Current genuine gate status: `not_assessed`.** No paired 30-site baseline/candidate corpus was created or inferred from historical summary counts.

### B26 / getfixlist own-site serving evidence

A source audit demonstrated three source-level gaps relevant to the own-site release contract: the home source lacked an explicit canonical and the public static tree lacked `robots.txt` and `sitemap.xml`.

This lane adds:

- exact home canonical `https://getfixlist.com/` in `index.html`;
- `public/robots.txt` allowing normal crawling and declaring `https://getfixlist.com/sitemap.xml`;
- a conservative `public/sitemap.xml` containing only `/` and `/blog`, excluding authentication/account/app routes;
- `scripts/stage4OwnSiteSourceAudit.mjs` and `tests/frontend/stage4OwnSiteSourceAudit.test.mjs` to verify title, description, canonical, robots declaration and sitemap/public-route alignment.

The source audit deliberately returns `soft_404.status=not_assessed`: source files cannot prove the HTTP status/fallback behavior of the deployed Base44 host. The exact release still needs a fresh deployed observation before getfixlist soft-404 behavior can be called fixed or clean.

### B28 / exact-source release and live customer acceptance

`tests/frontend/stage4ReleaseWorkflowContract.test.mjs` pins existing guarded release behavior:

- Base44 publish is owner-only and main-only;
- checkout and `origin/main` must equal the dispatched SHA;
- owner confirmation must equal the exact SHA;
- ephemeral Base44 device authorization remains required;
- the canonical release manifest contains exactly six V6 scanner runtime functions;
- Cloud Operator exposes guarded build/promote/rollback/barrier/cutover/acceptance-only operations with bounded acceptance budgets.

`scripts/stage4ReleaseAcceptance.mjs` defines the evidence record required to call live Stage 4 accepted. It requires traceable receipts/references for every material live claim, including:

- exact merged SHA, independently approved review and exact-SHA CI success;
- named-schema parity;
- verified getfixlist and Base44 site source identities;
- verified identities for all six V6 scanner functions;
- worker source, digest, revision, 100% traffic, rollback target/readiness and private unauthenticated `/scan-job` 403;
- an acceptance-only bounded cohort while public claims are closed;
- a real scan submitted through the published customer UI using Standard 150, within the 150-page cap, with persisted authority proof and FixList id;
- reload of the exact same `scan_id`/FixList/authority proof;
- owner-scoped history containing that scan;
- a distinct linked rescan on the same domain with verified improved/unchanged/regressed comparison evidence;
- cohort close/drain before public claims open.

Test fixtures can exercise this shape but are forcibly `not_assessed`; they cannot claim live acceptance. A claimed live state without receipts fails closed.

## Files owned by this lane

- `scripts/stage4EvidenceCompatibility.mjs`
- `scripts/assertBlueprint30SiteGate.mjs`
- `scripts/stage4ReleaseAcceptance.mjs`
- `scripts/stage4OwnSiteSourceAudit.mjs`
- `tests/frontend/stage4EvidenceCompatibility.test.mjs`
- `tests/frontend/stage4HistoricalReaderContract.test.mjs`
- `tests/frontend/stage4Blueprint30SiteGate.test.mjs`
- `tests/frontend/stage4NamedCorpusContract.test.mjs`
- `tests/frontend/stage4ReleaseAcceptance.test.mjs`
- `tests/frontend/stage4ReleaseWorkflowContract.test.mjs`
- `tests/frontend/stage4OwnSiteSourceAudit.test.mjs`
- `index.html`
- `public/robots.txt`
- `public/sitemap.xml`
- this handoff document

No `run_scan`, shared probe scheduler, Stage-2 feature module, Stage-3 ranking/delivery module, authority/persistence shared writer, deployed Base44 function, worker traffic, admission state, provider connection or customer data is changed by this lane.

## Verification status

Exact code/test checkpoint before this documentation commit: `c8999a0407136b4e9e45345ba81011584691ecf8`.

FixList CI run `35463913140`: **SUCCESS** on both jobs.

Fresh exact-checkpoint evidence:

- immutable checkout: passed;
- root scanner regression step: passed;
- full `scanner-api` regression step: passed;
- named Stage-1 corpus production/assertion: passed and remained explicitly synthetic with `full_30_site_gate=not_assessed`;
- frozen scanner revision verification: passed;
- production scanner image build: passed;
- frontend lint: passed;
- typecheck: passed;
- generated release contracts: current;
- frontend contract tests, including the Stage-4 regressions above: passed;
- frontend production build: passed.

The latest directly captured numeric suite totals from the preceding exact lane head `1e22b488036c2a00b9993a6302ddb8fbae1bd9f3`, FixList CI `35463815563`, were **115 root scanner tests** and **1,820 scanner-api tests / 18 intentional skips**. The later checkpoint changed only Stage-4 JavaScript gate/test code and the same scanner regression, corpus, frozen-revision and image-build steps passed again.

CodeRabbit independent review was manually requested on draft PR #317, but the service reported its review quota/rate limit at this checkpoint. That is recorded as **independent automated review unavailable**, not as a review pass.

**Lane status: code/test contracts are CI-verified and integration-ready, but Stage 4 is not complete or live-accepted.** The genuine paired 30-site gate, deployed getfixlist soft-404 verification, exact-source deployment and real customer scan/reload/history/rescan acceptance all remain `not_assessed` until performed against the eventual integrated release.

## Remaining serialized integration/live actions

1. Complete and exact-head verify B06–B24 before shared Stage-4 wiring.
2. Authenticate approved Stage-2/3 evidence fields through the canonical signed authority and all verified readers using the compatibility boundary; retain frozen legacy reconstruction bytes and fail closed on unknown versions.
3. Capture the genuine paired 30-site baseline/candidate corpus under a single explicit policy/scope contract; independently adjudicate every new artifact. Until that exists, B25 full gate remains `not_assessed`.
4. Merge only reviewed integrated source, require exact-main CI and named schema parity.
5. Publish Base44 site/functions and promote the worker only through guarded owner workflows, proving actual runtime/source identities and rollback readiness.
6. Recheck getfixlist canonical, robots, sitemap and soft-404 behavior against the **exact deployed source**. The source-level changes in this lane are not deployment proof.
7. With public claims still closed, activate a bounded acceptance-only cohort and run one real customer Standard 150 scan from the published UI. Verify persisted authority/FixList, exact `scan_id` reload/history, then run and verify a linked rescan comparison.
8. Close/drain acceptance before opening public claims. Record the resulting live evidence in the Stage-4 acceptance record; only a genuine `live_authorized` record may pass.
