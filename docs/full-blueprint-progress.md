# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current requirement ledger. Historical checkpoints remain in Git history and executable plans under `docs/superpowers/plans/`. The approved spec controls over older handoff paraphrases.

## Release sequencing and Stage-1 freeze

Stage 1 and the later blueprint remain distinct release states.

- `main` was freshly verified at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing the V7 runtime/public-build changes and durable ownership-before-admission fix #308.
- Stage-1 exact-source publication/promotion and fresh non-owner production acceptance remain owned by the existing single release operator.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do **not** merge later-stage work to `main`, publish Base44, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets, or otherwise move production while the Stage-1 release operator owns that cutover.
- After Stage-1 live acceptance is recorded, reconcile this integration branch onto the then-current accepted `main` without reverting V7 or #308, then require fresh exact-head integrated CI.

The labelled Stage-1 corpus remains explicitly synthetic and cannot satisfy the genuine B25 30-site gate. Frozen scanner revision: `01ebe8e90df1e6bd`.

## Stage 2 — B06–B18 source integrated; final corrected-head re-review remains open

Integration surface: PR #303 / `agent/full-blueprint-stage2-coverage-b06-20260919`.

The isolated Stage-2 lane PRs were review/CI inputs only and must not be merged directly to `main`.

### Requirement status

- **B06:** one finite shared follow-up scheduler / unsampled internal-link verification is integrated. Probe-only URLs cannot inflate Standard-150 assessed pages or denominators.
- **B07:** active soft-404 orchestration is integrated through that same scheduler. Challenge/429/robots/budget/deadline/incomplete remains unknown.
- **B08:** redirect meaning distinguishes normalization, usable destination, wrong/catch-all destination, unusable destination and unverified access.
- **B09:** sitemap integrity/probes reuse the same finite scheduler. Customer promotion still requires exact root/child provenance and authenticated downstream proof.
- **B10:** accepted main-content evidence is integrated for internal deterministic analysis. Raw substantive copy is not retained; bounded fingerprints remain internal-only and are denied at external authority/customer boundaries.
- **B11:** exact retained-set sample-scoped depth/inlink/navigation is integrated. Sitemap is not an inlink, challenged/unusable sources cannot contribute, unsampled links cannot expand Standard 150, and no sitewide orphan claim is made.
- **B12:** paired raw/rendered hub-link evidence is integrated under the existing browser-followup ceiling with explicit completed/failed/unassessed states.
- **B13:** contextual local entity/status completeness is integrated as evidence-only; raw identity/contact observations remain internal and the external aggregate is positive-allowlisted.
- **B14:** cross-page identity requires the same explicit absolute HTTP(S) JSON-LD `@id` on distinct pages. Matching NAP/family never proves identity. External NAP proof is reduced and fail-closed.
- **B15:** contextual freshness is integrated as evidence-only. Old dates alone cannot fail; current-content intent plus contradictory current-scoped temporal evidence is required.
- **B16:** exact URL variant identity is integrated; no sibling-host expansion or duplicate claim without verified equivalence.
- **B17:** direct transfer bytes remain distinct from decoded/inline bytes. CrUX defaults disconnected; controlled connected evidence requires owner authorization, exact scan identity and valid non-future observation time.
- **B18:** GSC defaults disconnected; controlled evidence requires owner authorization, exact scan identity, exact retained-URL membership, conflict rejection, Standard-150 ceiling and valid non-future observation time.

### Latest independent-review finding: future private page fields were fail-open

A fresh CodeRabbit re-review of stable head `464d3a84726887a32bf19ad3b372d6a5ac5498cd` found one remaining material P1 boundary defect: `project_page_for_external_boundary` used a deny-list, so a future producer/debug field not already named in that list could cross `pages`/`crawled_pages`, direct authority review, signed completion/limited envelopes, persistence, preview or export.

#### RED

Commit `e51b62220c926c671c0906b441de62dcaf9c7b53` — `test(stage2): reproduce future private page leak` — injected an intentionally unknown `future_private_detail` sentinel into the existing direct-helper privacy fixture and required it to be absent from every external authority/signing path.

FixList CI `35499676118` failed as intended. The fixture change did not add a new test function; it caused the existing three direct-helper privacy regressions to expose the leak. The previous fully green suite size was 1,993 scanner-api tests / 18 intentional skips, so the RED behavior is the existing three privacy checks failing against the same suite rather than a new standalone test count.

#### Correction

Commit `fda2ab346fa102fe2a7d02f116b1cd6e1fa92eaf` — `fix(stage2): fail closed page output projection` — replaces page-output deny-list copying with an explicit positive external page-field allowlist.

Consequences:

- unknown future page fields are denied by default;
- currently approved route, metadata, robots, canonical, redirect, indexability, bounded access-block, Stage-1 content, B11 reachability, B17 scalar page-weight and authenticated GEO diagnostics remain explicitly classified;
- B10 fingerprints, B13/B14 raw entity/contact evidence, B15 per-page freshness evidence and B11 private retained-link cache remain excluded;
- future producer fields now require deliberate review/classification before they can become a signed/customer/persisted contract.

Exact executable FixList CI `35500366163` on `fda2ab346fa102fe2a7d02f116b1cd6e1fa92eaf` — **SUCCESS** on both jobs:

- immutable checkout: passed;
- root scanner regressions: passed (same 115-test root gate as the preceding certified checkpoint);
- full `scanner-api`: passed, including the three strengthened unknown-field direct-helper privacy regressions; suite remains **1,993 passed / 18 intentional skips** because the RED commit only strengthened an existing shared fixture;
- labelled Stage-1 synthetic corpus: passed and remains `full_30_site_gate=not_assessed`;
- frozen scanner revision: passed;
- production scanner image build: passed;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

GitHub Actions continues to request Node 20 and resolve Node 20.20.2 in the current CI environment; do not describe these runs as Node 20.19.5 runtime evidence.

Detailed review-hardening history: `docs/superpowers/plans/2026-09-20-stage2-followup-review-hardening.md`.

### Stage 2 completion gate

Stage 2 is **not yet recorded complete**. B06–B18 source integration and the latest material review correction now have RED reproduction and exact executable green CI. Remaining gate:

1. stabilize the persisted documentation head and require its exact-head FixList CI;
2. request one fresh independent re-review of that corrected stable PR #303 head;
3. reproduce/fix any material finding before recording completion;
4. only after a clean re-review record B06–B18 complete and begin serialized Stage-3 integration.

Keep internal B09/B10–B18 evidence internal unless a deliberate producer → Review → signed authority → persisted rows → customer/card/handoff/export chain is added. Preserve Standard 150, one finite request budget, robots/DNS/SSRF/redirect/body/deadline protections, exact scan isolation, one active scan/account, cancellation/terminalization, historical signatures/readers, preview privacy and Python Review authority.

## Stage 3 — isolated lanes built; shared integration held behind Stage 2

Do not duplicate these implementations. Reuse only after Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919` @ `e74d87acd0cec2955402b96f635f13bc275f3a91`, CI `35463839728`: B19 exact **impact × reach × page value × confidence** with truthful unknown denominators; B20 explicit evidenced shared SEO/GEO root causes. Family similarity is not root-cause proof and repair leverage is not a substitute fourth factor.
- `agent/stage3-b21-b24-delivery-20260919` @ `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`, CI `35463511347`: B21 exact unique unions/count distinctions/rank-before-truncate; B22 authenticated evidence-led private previews; B23 documented root-cause score caps preserving incomplete/access ceilings; B24 authenticated backward-compatible handoff v2 with v1 compatibility and no suppressed/operator-only exposure.

Python Review remains canonical ranking authority. Shared ranking/authority/persistence/customer integration remains serialized work after Stage 2 closes.

## Stage 4 — isolated compatibility/release lane built; live acceptance not run

`agent/stage4-b25-b28-compat-release-20260919` @ `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, remains isolated implementation input, not release authorization.

Spec numbering controls:

- **B25:** named synthetic corpus plus genuine provenance-labelled 30-site baseline/candidate gate;
- **B26:** reproduced own-site serving defects/fixes with source evidence;
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility;
- **B28:** exact-source review/CI/deployment/live acceptance, including runtime identities, rollback and one bounded real customer Standard-150 submit → persistence → exact `scan_id` reload/history → linked rescan verification.

The genuine 30-site baseline/candidate gate remains **not assessed**. Historical summaries and synthetic fixtures cannot satisfy it. No Stage-4 deployment, live customer scan or production acceptance is claimed.

## Hard invariants

- Standard-150 assessed-page cap and truthful denominators remain authoritative.
- Stage-2 follow-up checks share one finite request pool; no second scheduler/budget.
- Robots ownership, DNS/SSRF, redirect, body and deadline protections remain authoritative.
- One active scan/account, cancellation/terminalization and exact scan isolation remain intact.
- Missing, blocked, stale, disconnected, future-dated or otherwise invalid evidence remains unknown/unavailable rather than an invented pass/fail/current state.
- Historical signatures/readers stay compatible; unknown evidence versions fail closed.
- Preview privacy and entitlement boundaries remain intact.
- Python Review remains canonical priority/ranking authority.
- Premium/Grok remain outside this integration.
- Synthetic/historical data never substitutes for the genuine 30-site gate or real customer live acceptance.

## Exact next engineering action

Require exact-head CI on the final persisted documentation head, then request one fresh independent re-review of that stable PR #303 head. If clean, record Stage 2 complete and begin serialized integration of the existing B19/B20 and B21–B24 lanes. Do not move production.
