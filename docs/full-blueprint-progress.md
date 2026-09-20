# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current requirement ledger. Older implementation checkpoints remain in Git history and the executable plans linked below. The approved spec controls over stale handoff wording.

## Release sequencing

Stage 1 and the later blueprint remain separate release states.

- Stage-1 source was completed and merged before this later-stage integration line.
- Its exact-source production publication/promotion/non-owner live acceptance is a separate guarded operation and is **not** implied by later-stage CI.
- The later-stage integration branch is `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do not merge later-stage work to `main`, publish Base44, promote worker traffic, mutate admission, run a competing production scan, change schema/secrets, or otherwise move production while the Stage-1 release operator owns that cutover.
- `main` was reverified on 2026-09-20 at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`; the Stage-1 freeze is intact.
- After Stage-1 live acceptance is recorded, reconcile this integration line onto the then-current accepted `main` without reverting V7 runtime/public-build changes or the durable ownership-before-admission fix, followed by fresh exact-head combined CI.

## Stage 1 — source complete; live release acceptance separate

Stage-1 implementation established published-route evidence identity, authenticated authority/persistence/readers, image/template/search-evidence correctness, historical signature compatibility, preview privacy, and the named synthetic acceptance runner.

The labelled corpus remains explicitly synthetic and cannot satisfy the genuine 30-site full-blueprint gate.

Historical detail: `docs/stage-one-evidence-acceptance.md`.

Frozen scanner revision checked by later-stage CI: `01ebe8e90df1e6bd`.

## Stage 2 — B06–B18 integration in progress

Integration surface: PR #303 / `agent/full-blueprint-stage2-coverage-b06-20260919`.

The isolated lane PRs were review/CI inputs only and are not to be merged directly to `main`.

### Integrated and materially wired

- **B06 — shared bounded coverage scheduler/internal-link verification.** One finite follow-up scheduler reuses the hardened robots/DNS/SSRF/redirect/body/deadline path. Probe-only URLs do not enter the Standard-150 assessed-page set or denominator. Verified unsampled broken-link evidence has authenticated producer → Review → authority → persistence → customer-output coverage.
- **B07 — active soft-404 evidence/orchestration.** Deterministic same-origin/effective-scope missing-page candidates use the shared finite scheduler. Challenge/429/robots/budget/deadline/incomplete outcomes remain unknown. Synthetic probes stay outside assessed pages. Versioned active evidence is separate from historical/passive heuristic evidence and has signed/persisted/customer coverage.
- **B08 — redirect meaning.** Harmless normalization, usable destination, wrong/catch-all destination, unusable destination and unverified access are distinct. Challenge/block/rate-limit destinations remain unknown; ordinary verified 404 remains unusable. Zero-hop diagnostic loop state remains unverified while an observed loop with hop provenance is unusable.
- **B09 — sitemap integrity helper/probe integration.** Same-origin/in-scope unsampled targets reuse the shared scheduler. Candidate-universe truncation and access/budget uncertainty remain explicit. Exact root/child provenance and child failure reasons must remain attached if this evidence is promoted to displayed findings.
- **B10 — accepted main-content producer seam.** Accepted usable HTML prefers `main`, `role=main`, then `article`; body fallback strips common chrome on a clone. Empty landmarks remain landmarks. Raw page copy is not retained in compatibility evidence; bounded SHA-256 five-token shingle fingerprints plus aggregate signature/token/character-count metadata are used instead.
- **B11 — truthful sample-scoped reachability producer wiring.** Versioned B11 evidence reaches the retained assessed set after the final Standard-150 cap. Edges exist only where both exact request URLs are retained assessed pages; sitemap discovery never becomes an inlink; challenged/unusable sources are re-gated out; unsampled targets never expand `pages`; `sitewide_orphan_claim` remains false. The private `_reachability_links` cache is removed before result persistence/customer projection. No second request budget exists.
- **B12 — paired raw/rendered hub evidence producer/source wiring.** Up to five verified structural hubs can be selected for evidence disclosure while browser execution still uses the existing three-page follow-up ceiling. B11 retained links provide bounded raw evidence; rendered evidence is accepted only from successful 2xx, accepted `usable_html` renderer observations with no challenge/block/rate-limit/fetch-error/truncation state. Missing or rejected rendered evidence stays failed/unassessed, and unsampled rendered links never expand the assessed set. `run_render_followup` separates browser authorization from the exact retained-set evidence disclosure channel, so policy-declined rendering remains selected-but-unassessed without enabling a renderer callback or second budget.
- **B13 partial — local entity completeness producer.** Accepted usable HTML can produce bounded versioned JSON-LD LocalBusiness/Store-family observations for name, address, phone, regular hours when explicitly present, schema type, entity ID and optional holiday-hours/photos/sameAs/parent presence. Missing hours with unknown applicability remains `not_verified`; optional fields are not universal defects. Malformed/oversized structured data and unusable HTTP evidence fail closed. Page observations are bounded while exact unique candidate counts and truncation state are retained.
- **B14 partial — conservative cross-page NAP evidence.** Cross-page entity identity currently requires an explicit absolute HTTP(S) JSON-LD `@id`. Fragment/relative IDs such as `#store` remain observed but unverified until trusted base resolution exists. Shared names/addresses/phones/page-family similarity never establish identity. NAP comparison requires the same verified entity ID on at least two distinct page URLs; one observation and same-page duplicate/conflicting JSON-LD cannot produce a cross-page pass/fail. Distinct explicit IDs remain separate even when a phone is shared. `sitewide_consistency_claim` is false.
- **B15 — contextual freshness producer/source evidence seam.** Accepted retained pages receive bounded versioned freshness evidence from already-extracted title/H1/meta description plus path as historical-only provenance. A fail requires explicit current-content language and contradictory current-scoped temporal evidence. Old years/articles/paths alone are not stale defects; `apply now` is not current-content intent; mixed current/latest plus explicit archive/history wording preserves dates as historical and therefore unknown rather than manufacturing a stale finding. Year-only dates use 31 December conservatively. This is evidence-only: no repair/card/score change is emitted and no new fetch or request budget exists.
- **B16 — URL variants.** Exact path/query/case/reserved-escape/empty-query identity is retained. No implicit sibling-host expansion occurs. Live alternate routes are not declared duplicates without independent equivalence evidence. Redirect meaning delegates to B08.
- **B17 partial — truthful decoded/inline page weight.** Decoded HTML bytes and inline script/style bytes are separately measured from accepted content. Transfer/wire bytes remain unknown; decoded bytes or zero are never substituted for network transfer bytes.

### Current exact executable checkpoint

Exact executable head: `e286c3c4f0db6b90c60300f804232c5894936c40`.

FixList CI `35484767939` — **SUCCESS** on both jobs:

- immutable checkout verified `e286c3c4f0db6b90c60300f804232c5894936c40`;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,961 passed / 18 intentional skips**;
- B15 focused suite: **9 passed** as part of the scanner suite;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:afc21e8f12c5d00cfaa9cdbef78514576141422bc9ee08605e8f2f6affabd74d`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow resolved Node `20.20.2`; this is not Node `20.19.5` runtime evidence.

Detailed current plans:

- `docs/superpowers/plans/2026-09-19-stage2-serialized-review-hardening.md`
- `docs/superpowers/plans/2026-09-20-stage2-b11-reachability-provenance.md`
- `docs/superpowers/plans/2026-09-20-stage2-b12-hub-render-evidence.md`
- `docs/superpowers/plans/2026-09-20-stage2-b13-b14-local-entity.md`
- `docs/superpowers/plans/2026-09-20-stage2-b15-contextual-freshness.md`

### B13/B14 hardening carried forward

The B14 seam was tightened after source review:

1. A single explicit entity observation can support B13 completeness but cannot prove that NAP is consistent across pages.
2. The same explicit entity ID must occur on at least two distinct page URLs before B14 can pass or fail.
3. Duplicate/conflicting JSON-LD on one page remains unverified for cross-page consistency rather than becoming a false cross-page inconsistency.
4. Distinct explicit entity IDs remain separate even if they share a phone number.
5. Matching name/address/phone without explicit verified identity never joins entities.
6. Relative/fragment JSON-LD IDs remain unverified because the current producer seam does not carry a trusted document base for correct cross-page resolution; absolute HTTP(S) IDs remain eligible verified identity.

Focused regressions are in `scanner-api/tests/test_stage2_local_entity_producer.py` and `scanner-api/tests/test_stage2_local_entity_identity.py`.

Intermediate cross-page head `b513c6c7a47e39d792b342f15d6ff31025f5d099` passed FixList CI `35484212032` with **115 root passed**, **1,950 scanner-api passed / 18 skips**, labelled synthetic corpus, frozen revision, production image build and frontend/contract gates. B13/B14 hardening head `fe3d18cc63f7b0acdf0e97679db5b14e47966e10` passed CI `35484333097` with **115 root passed**, **1,952 scanner-api passed / 18 skips**.

### Relevant prior Stage-2 checkpoints

- Shared B07/B09/B16 integration: `ca70b7380011e93437fc993185e511a5847618e6`, Stage2IntegrationRun `35469815094`.
- B10/review hardening exact head `f904649c9193877181471e1daa01097da0f3062b`, CI `35472567286`: 115 root, 1,911 scanner-api / 18 skips.
- B11 retained-set producer hook exact head `f51869adf8eac44de4fa7c9387590ab3c330c5a9`, CI `35478073142`: 115 root, 1,924 scanner-api / 18 skips.
- B12 final shared caller checkpoint `d612ceade6fc31ecd3e01d5b195dbd4d646524ef`, CI `35483256047`: 115 root, 1,932 scanner-api / 18 skips. CodeRabbit subsequently identified a valid renderer-acceptance P1; the current branch fixes it by requiring accepted complete usable HTML before rendered links can count as completed evidence.
- B15 exact head `e286c3c4f0db6b90c60300f804232c5894936c40`, CI `35484767939`: 115 root, 1,961 scanner-api / 18 skips; production scanner image `sha256:afc21e8f12c5d00cfaa9cdbef78514576141422bc9ee08605e8f2f6affabd74d`.

### Stage 2 still open

Stage 2 is **not source-complete**.

- **B09:** if sitemap evidence becomes customer-visible, preserve exact sitemap root/child provenance and child failure reasons through the authenticated downstream chain.
- **B10:** if near-duplicate evidence becomes customer-visible, add authenticated Review → authority → persistence → customer/card/handoff/export coverage.
- **B11/B12:** source integration is green. A current independent review of the combined retained-link/render shape remains a stage gate. Add downstream authenticated/privacy proof if these samples are exposed to customers.
- **B13/B14:** page-level structured observations and the bounded scan aggregation adapter are implemented and green, but the scan-level summary is not yet attached to the shared `run_scan`/authority result. The producer does not claim generic visible-text/store-form identity, complete Coming Soon status inference, or complete store-finder/form parity. Add those only from explicit provenance. No customer repair/card/score adjustment exists for this slice.
- **B15:** producer/source evidence is implemented and exact-head green, but remains evidence-only. Any future customer-visible freshness finding requires authenticated downstream proof before exposure.
- **B17:** add directly measured transfer bytes without confusing them with decoded bytes. CrUX remains optional and must expose disconnected/stale/unavailable states unless a current authorized response exists.
- **B18:** GSC remains optional with explicit disconnected/stale/unavailable behavior unless a current owner-authorized response exists.
- Any new displayed B09/B10–B18 evidence/count/finding requires real producer → Review → signed authority → persisted rows → verified customer/card/handoff/export coverage before requirement closure.
- Final combined independent review and fresh exact-head CI after remaining shared wiring are mandatory before Stage 3 integration.

A fresh CodeRabbit review was requested for the current B11–B14 combined shape, but the bot's repository configuration currently exposes a manual trigger rather than recording a new review pass. Do not count that request as an independent-review success. A fresh review of B15 is also still required before Stage 2 can close.

## Stage 3 — isolated lanes built; shared integration held behind Stage 2

The existing lane work is implementation input only until Stage 2 closes.

- `agent/stage3-b19-b20-decisions-20260919`: B19 exact **impact × reach × page value × confidence** factor evidence/explanations and B20 explicit evidenced shared root causes across SEO/GEO. Family similarity alone is not root-cause proof. Exact lane head `e74d87acd0cec2955402b96f635f13bc275f3a91` passed its lane CI.
- `agent/stage3-b21-b24-delivery-20260919`: B21 exact unions/count distinctions/rank-before-truncate; B22 authenticated evidence-led private previews; B23 explicit evidenced root-cause score caps preserving existing ceilings; B24 backward-compatible handoff v2. Lane head `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` passed its lane CI.

Do not integrate B19–B24 into shared ranking/authority/customer interfaces until Stage 2 is source-complete, independently reviewed and exact-head green. Python Review remains canonical ranking authority.

## Stage 4 — isolated compatibility/release lane built; live acceptance not run

`agent/stage4-b25-b28-compat-release-20260919` contains isolated B25–B28 compatibility/acceptance/release-preparation work. Lane head `d2ce905ff67410586f86e38bafd93ce4e998e4d1` passed its lane CI. This does not constitute release authorization or live acceptance.

Spec numbering controls:

- **B25:** named synthetic corpus plus genuine provenance-labelled 30-site baseline/candidate gate. Historical summaries and synthetic fixtures cannot satisfy the real gate.
- **B26:** reproduced own-site serving defects/fixes with source evidence; deployed HTTP behavior must be verified only on the exact eventual release.
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility for new evidence while original historical signatures remain readable and unknown versions fail closed.
- **B28:** exact-source review/CI/deployment/live acceptance, including runtime identities, rollback, one bounded real customer Standard-150 submit → persistence → exact `scan_id` reload/history → linked rescan verification.

The genuine 30-site baseline/candidate gate remains **not assessed**. No Stage-4 deployment, live scan or production claim is authorized by isolated lane CI.

## Hard invariants

- Standard-150 assessed-page cap and truthful denominators remain authoritative.
- Stage-2 follow-up checks share one finite request pool; no second scheduler/budget.
- Existing robots ownership, DNS/SSRF, redirect, body and deadline protections remain authoritative.
- One active scan/account, cancellation/terminalization and exact scan isolation remain intact.
- Missing, blocked, stale, disconnected or invalid evidence remains unknown rather than invented pass/fail evidence.
- Historical signatures/readers remain compatible; unknown evidence versions fail closed.
- Preview privacy and entitlement boundaries remain intact.
- Python Review remains the canonical priority/ranking authority.
- Premium/Grok remain outside this blueprint integration.
- Synthetic/historical data never substitutes for the genuine 30-site gate or real customer live acceptance.

## Exact next engineering action

Stay on Stage 2. Attach the bounded B13/B14 scan-level summary to the shared scanner result/authority path without changing the assessed set or request budget and without exposing unauthenticated customer claims. Then implement direct B17 transfer-byte evidence plus conservative optional CrUX state and B18 optional GSC state. Obtain fresh independent review of the combined B11–B18 source shape and require another exact-head CI after the remaining shared wiring. Only after B06–B18 are genuinely source-complete, independently reviewed and exact-head green should shared Stage-3 integration begin.
