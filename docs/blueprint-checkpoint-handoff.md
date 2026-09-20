# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current serialized handoff for the FixList full-scanner blueprint. Historical checkpoints remain in Git history and linked executable plans. The approved spec controls over older paraphrases.

## Release boundary

- Stage-1 publication/promotion/live non-owner acceptance remains owned by the existing exact-source release operator.
- `main` was freshly verified at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`; later-stage work has no authority to move production.
- Do not publish, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets, or merge the later-stage branch to `main`.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- After Stage-1 live acceptance, reconcile onto the then-current accepted `main` without reverting V7 route/public-build changes or #308, then require fresh exact-head integrated CI.

## Current Stage-2 executable checkpoint

Exact executable head: `fda2ab346fa102fe2a7d02f116b1cd6e1fa92eaf`.

FixList CI `35500366163` — **SUCCESS** on both jobs:

- immutable checkout: passed;
- root scanner regression gate: passed (same 115-test gate as the preceding certified checkpoint);
- full `scanner-api`: passed, including the three strengthened direct-helper privacy regressions; suite remains **1,993 passed / 18 intentional skips** because the latest RED commit strengthened an existing fixture rather than adding test functions;
- labelled Stage-1 synthetic corpus: passed, with `full_30_site_gate=not_assessed` unchanged;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image build: passed;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

GitHub Actions requested Node 20 but resolved Node 20.20.2. Do not represent this as Node 20.19.5 runtime evidence.

## Latest independent re-review finding and RED → GREEN correction

A fresh CodeRabbit re-review of stable head `464d3a84726887a32bf19ad3b372d6a5ac5498cd` found one remaining material P1 defect: the per-page external projection used a deny-list. An unknown future producer/debug field could therefore cross `pages`/`crawled_pages`, direct authority review and signed completion/limited envelopes merely because the projector did not know its name yet.

### RED

`e51b62220c926c671c0906b441de62dcaf9c7b53` — `test(stage2): reproduce future private page leak` — injects an intentionally unknown `future_private_detail` sentinel into the existing Stage-2 direct-helper privacy fixture and requires it to be absent from every external authority/signing path.

FixList CI `35499676118` failed as intended. The change added no new test function; it made the existing three direct-helper privacy regressions expose the fail-open behavior.

### GREEN

`fda2ab346fa102fe2a7d02f116b1cd6e1fa92eaf` — `fix(stage2): fail closed page output projection` — replaces deny-list copying with a positive external page-field allowlist.

- current approved route/search metadata/robots/canonical/redirect/indexability/access-block/Stage-1 content/B11 reachability/B17 scalar-weight/GEO diagnostics are explicitly classified;
- unknown future page fields are denied by default;
- B10 fingerprints, raw B13/B14 identity/contact observations, B15 per-page freshness evidence and B11 private link cache remain excluded;
- direct authority/signing helpers already defensively project before sampling/signing, so the new fail-closed rule applies to those paths too.

Exact executable CI `35500366163` is fully green as recorded above.

Detailed history: `docs/superpowers/plans/2026-09-20-stage2-followup-review-hardening.md`.

## Stage-2 requirement state

- **B06:** shared finite coverage scheduler / unsampled internal-link verification integrated; probe-only URLs cannot inflate Standard-150 denominators.
- **B07:** active soft-404 integrated through that same scheduler; blocked/challenged/robots/budget/deadline/incomplete remains unknown.
- **B08:** redirect meaning distinguishes normalization, usable, wrong/catch-all, unusable and unverified access.
- **B09:** sitemap integrity uses the same finite scheduler; any customer promotion still requires exact root/child provenance and authenticated downstream proof.
- **B10:** bounded main-content fingerprints are internal-only; raw copy is not retained; page output and direct authority/signing boundaries now fail closed for unknown future fields.
- **B11:** retained-set reachability is exact-URL/sample-scoped; sitemap cannot masquerade as inlink; no sitewide orphan claim; private link cache denied externally.
- **B12:** paired raw/rendered hub evidence integrated under existing browser-followup ceiling with explicit completed/failed/unassessed states.
- **B13:** contextual local entity/status completeness integrated as evidence-only; raw identity/contact observations remain internal; external aggregate is positive-allowlisted.
- **B14:** explicit absolute HTTP(S) entity identity required across distinct URLs; matching NAP/family never proves identity; external NAP proof is reduced and fail-closed.
- **B15:** contextual freshness integrated as evidence-only; old date alone cannot fail; raw per-page freshness evidence stays internal.
- **B16:** exact URL variant identity integrated; no sibling-host expansion or duplicate claim without verified equivalence.
- **B17:** direct transfer bytes remain distinct from decoded/inline bytes; CrUX defaults disconnected; controlled provider data rejects stale/missing/future timing.
- **B18:** GSC defaults disconnected; controlled data requires owner authorization, exact scan identity, exact retained URL membership, conflict rejection, Standard-150 ceiling and valid observation time.

## Stage 2 remains open only at corrected stable-head independent re-review

Do not start shared Stage-3 integration yet. Source integration and the latest material review finding now have RED reproduction and exact executable green CI. Remaining gate:

1. require exact-head FixList CI on the final persisted documentation head;
2. request one fresh independent re-review of that stable PR #303 head;
3. if a material issue appears, reproduce it before correction and require new exact-head CI;
4. if the re-review is clean, record B06–B18 complete and begin serialized Stage-3 integration.

Keep B09/B10–B18 evidence internal unless a deliberate producer → Review → signed authority → persisted rows → customer/card/handoff/export chain is added. Preserve Standard 150, one finite request budget, robots/DNS/SSRF/redirect/body/deadline protections, one active scan/account, cancellation/terminalization, exact scan isolation, historical signatures/readers, preview privacy and Python Review authority.

## Stage 3 — isolated lanes built, not shared-integrated

Reuse only after Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919` / `e74d87acd0cec2955402b96f635f13bc275f3a91`, CI `35463839728`: B19 exact **impact × reach × page value × confidence** with truthful unknown denominators; B20 explicit evidenced root causes across SEO/GEO. Family similarity is not root-cause proof; repair leverage is not the fourth factor.
- `agent/stage3-b21-b24-delivery-20260919` / `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`, CI `35463511347`: B21 exact unique unions/counts/rank-before-truncate; B22 authenticated private previews; B23 evidenced root-cause score caps preserving incomplete/access ceilings; B24 backward-compatible authenticated handoff v2 with v1 compatibility and no suppressed/operator-only exposure.

Python Review remains canonical ranking authority. Shared ranking/authority/persistence/customer interfaces remain serialized integration work.

## Stage 4 — isolated lane built, not released

Reuse `agent/stage4-b25-b28-compat-release-20260919` / `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, only after Stage 3 shared integration.

Spec numbering controls:

- **B25:** named synthetic corpus + genuine provenance-labelled 30-site baseline/candidate gate;
- **B26:** reproduced own-site serving defects/fixes;
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility;
- **B28:** exact-source review/CI/deployment/live customer acceptance.

The genuine 30-site gate remains **not assessed**. Historical summaries and synthetic fixtures cannot become a pass. No Stage-4 deployment, live customer scan or acceptance has been run by this integration branch.

## Exact next action

Require exact-head CI on the final persisted documentation head, then request one fresh independent re-review of stable PR #303. If clean, record Stage 2 complete and begin serialized integration of the existing B19/B20 and B21–B24 deltas. Do not move production.
