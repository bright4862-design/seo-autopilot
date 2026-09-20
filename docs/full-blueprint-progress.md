# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current requirement ledger. Older checkpoints remain in Git history and the executable plans under `docs/superpowers/plans/`. The approved spec controls over stale handoff wording.

## Release sequencing

Stage 1 and the later blueprint remain separate release states.

- Stage-1 source is merged on `main`; exact-source production publication/promotion/non-owner acceptance remains a separate guarded operation.
- `main` was reverified on 2026-09-20 at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing the V7 runtime/public-build changes and durable ownership-before-admission fix #308.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do not merge later-stage work to `main`, publish Base44, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets or otherwise move production while the Stage-1 release operator owns that cutover.
- After Stage-1 live acceptance is recorded, reconcile this integration line onto the then-current accepted `main` without reverting V7 or #308, then require fresh exact-head combined CI.

## Stage 1 — source complete; live release acceptance separate

Stage-1 established published-route evidence identity, authenticated authority/persistence/readers, image/template/search-evidence correctness, historical signature compatibility, preview privacy and the named synthetic acceptance runner.

Historical detail: `docs/stage-one-evidence-acceptance.md`.

The labelled corpus is explicitly synthetic and cannot satisfy the genuine 30-site full-blueprint gate. The frozen scanner revision checked by later-stage CI remains `01ebe8e90df1e6bd`.

## Stage 2 — B06–B18 integration in progress

Integration surface: PR #303 / `agent/full-blueprint-stage2-coverage-b06-20260919`.

The isolated lane PRs were review/CI inputs only; do not merge them directly to `main`.

### Integrated and materially wired

- **B06 — shared bounded coverage scheduler/internal-link verification.** One finite follow-up scheduler reuses hardened robots/DNS/SSRF/redirect/body/deadline controls. Probe-only URLs never enter the Standard-150 assessed set or denominator. Verified unsampled broken-link evidence has authenticated producer → Review → authority → persistence → customer-output coverage.
- **B07 — active soft-404 evidence/orchestration.** Deterministic same-origin/effective-scope missing-page candidates use the shared finite scheduler. Challenge/429/robots/budget/deadline/incomplete states remain unknown. Synthetic probes stay outside assessed pages. Active evidence is versioned separately from passive/historical heuristics and has signed/persisted/customer coverage.
- **B08 — redirect meaning.** Harmless normalization, usable destination, wrong/catch-all destination, unusable destination and unverified access are distinct. Challenge/block/rate-limit responses stay unknown; ordinary verified 404 is unusable. Zero-hop diagnostic loops stay unverified unless hop evidence exists.
- **B09 — sitemap integrity helper/probe integration.** Same-origin/in-scope unsampled targets reuse the shared scheduler. Candidate-universe truncation and access/budget uncertainty remain explicit. Exact root/child provenance and failure reasons must remain attached if promoted to customer-visible findings.
- **B10 — accepted main-content evidence seam.** Accepted usable HTML prefers `main`, `role=main`, then `article`; body fallback strips common chrome on a clone. Empty landmarks remain landmarks. Raw substantive page copy is not retained; bounded deterministic SHA-256 five-token shingle fingerprints plus aggregate metadata support conservative near-duplicate analysis.
- **B11 — truthful sample-scoped reachability.** Retained-set evidence is produced only after the final Standard-150 cap. Exact retained request URLs form edges; sitemap discovery never becomes an inlink; challenged/unusable sources are re-gated out; unsampled targets never expand `pages`; `sitewide_orphan_claim` remains false. Private `_reachability_links` is removed before persistence/customer projection.
- **B12 — paired raw/rendered hub evidence.** Up to five verified structural hubs may be selected for disclosure while browser execution remains under the existing three-page follow-up ceiling. Rendered evidence is accepted only from successful 2xx accepted `usable_html` observations with no challenge/block/rate-limit/fetch-error/truncation state. Missing/rejected render stays failed/unassessed. Unsampled rendered links cannot expand the assessed set.
- **B13 — local entity completeness evidence.** Accepted usable HTML produces bounded versioned JSON-LD LocalBusiness/Store-family observations for explicitly present name/address/phone/regular-hours/schema/entity-id plus optional fields. Malformed/oversized/unusable evidence fails closed. Missing optional fields are not universal defects. The bounded scan aggregate is attached to the shared result and authenticated technical summary without creating a customer repair or score change.
- **B14 — conservative cross-page NAP evidence.** Cross-page identity requires explicit absolute HTTP(S) JSON-LD `@id`; relative/fragment IDs remain unverified without a trusted document base. Matching names/addresses/phones or page-family similarity never prove identity. The same verified ID must occur on at least two distinct page URLs before a consistency pass/fail. The scan aggregate is attached to the authenticated technical summary with `sitewide_consistency_claim=false`.
- **B15 — contextual freshness evidence.** A fail requires explicit current-content intent plus contradictory current-scoped temporal evidence. Old articles/years/dated paths alone cannot fail freshness; historical/archive wording remains historical; year-only dates use 31 December conservatively. Evidence-only: no repair/card/score change or new fetch.
- **B16 — URL variants.** Exact path/query/case/reserved-escape/empty-query identity is retained. No implicit sibling-host expansion. Live alternate routes are not declared duplicates without independent equivalence evidence. Redirect meaning delegates to B08.
- **B17 — distinct page-weight evidence + optional CrUX state.** Decoded HTML and inline script/style bytes remain separate. Transfer-body payload bytes are now measured directly from the hardened `httpx` `aiter_raw()` boundary before content decoding; they are never inferred from `Content-Length` or decoded bytes and a remote site cannot spoof FixList's internal measurement. Access-limited pages keep transfer evidence unknown. The ordinary scan path now authenticates CrUX as explicitly disconnected with no metrics or fabricated scan identity; controlled authorized/current/stale/unavailable response shapes remain covered by the exact-scan adapter tests. No live provider connection is claimed.
- **B18 — optional connected GSC state.** The ordinary scan path now authenticates GSC as explicitly disconnected, with `provider_data_admitted=false`, no page metrics and an assessed retained-URL count only. Controlled connected/stale/unavailable GSC response tests require owner authorization, exact scan identity, exact retained URL membership, conflict rejection and the Standard-150 ceiling. No live GSC connection or traffic/indexing claim is made.

### Current exact executable checkpoint

Exact executable head: `910206d34a298ab840cf610542a55809a76b0115`.

FixList CI `35490060294` — **SUCCESS** on both jobs:

- immutable checkout verified `910206d34a298ab840cf610542a55809a76b0115`;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,978 passed / 18 intentional skips**;
- new shared disconnected-provider result/authority regressions: **3 passed**;
- existing connected-provider contract regressions: **7 passed**;
- direct B17 transfer-body regressions: **4 passed**;
- labelled Stage-1 corpus: `synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:afc5d05e3a0c36639b02c40de8545d87d3d897711969c17e13029f01c6ee9ba1`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow resolved Node `20.20.2`; this checkpoint is not Node `20.19.5` runtime evidence.

Direct-transfer executable checkpoint before provider-result integration: `b915e3846aa2a94da7acbe0b59be7e22c4b3051d`, FixList CI `35489000795` — SUCCESS. Detailed records:

- `docs/superpowers/plans/2026-09-19-stage2-serialized-review-hardening.md`
- `docs/superpowers/plans/2026-09-20-stage2-b11-reachability-provenance.md`
- `docs/superpowers/plans/2026-09-20-stage2-b12-hub-render-evidence.md`
- `docs/superpowers/plans/2026-09-20-stage2-b13-b14-local-entity.md`
- `docs/superpowers/plans/2026-09-20-stage2-b15-contextual-freshness.md`
- `docs/superpowers/plans/2026-09-20-stage2-connected-provider-evidence.md`
- `docs/superpowers/plans/2026-09-20-stage2-transfer-body-evidence.md`
- `docs/superpowers/plans/2026-09-20-stage2-provider-result-integration.md`

### Stage 2 still open

Stage 2 is **not complete**.

- **B09:** if sitemap evidence is promoted downstream, exact sitemap root/child provenance and child failure reasons must survive the authenticated customer chain.
- **B10:** if near-duplicate evidence becomes customer-visible, add authenticated Review → authority → persistence → customer/card/handoff/export proof. Fingerprint evidence must remain bounded and must not become a hidden preview/export channel.
- **B11/B12:** source wiring is green; downstream authenticated/privacy proof is required if raw/rendered samples are exposed to customers.
- **B13/B14:** current producer is deliberately conservative and does not yet claim generic visible-text/store-form identity, complete Coming Soon status inference, or complete store-finder/form/sitemap entity parity. Those portions remain open until explicit provenance is implemented; do not infer them from matching NAP strings.
- **B15:** source evidence is green and evidence-only. Any customer-visible freshness finding requires authenticated downstream proof.
- **B17/B18:** ordinary no-provider behavior is now explicit and authenticated; controlled connected-response adapters are tested. No account-specific live connection is claimed. A future live/provider connection is not required for an otherwise valid scan and remains an owner-authorized optional integration.
- A fresh independent review of the final combined B06–B18 source shape is mandatory. Material findings must receive regressions and another exact-head CI before Stage 3 shared integration.
- Any new displayed B09/B10–B18 evidence/count/finding requires real producer → Review → signed authority → persisted rows → verified customer/card/handoff/export coverage before that displayed behavior can close.

## Stage 3 — isolated lanes built; shared integration held behind Stage 2

Existing lane work is implementation input only until Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919`: B19 exact **impact × reach × page value × confidence** evidence/explanations and B20 explicit evidenced shared root causes across SEO/GEO. Family similarity is never root-cause proof. Exact lane head `e74d87acd0cec2955402b96f635f13bc275f3a91` passed lane CI `35463839728`.
- `agent/stage3-b21-b24-delivery-20260919`: B21 exact unions/count distinctions/rank-before-truncate; B22 authenticated evidence-led private previews; B23 explicit evidenced root-cause score caps preserving existing ceilings; B24 backward-compatible handoff v2. Lane head `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` passed lane CI `35463511347`.

Do not integrate B19–B24 into shared ranking/authority/customer interfaces until Stage 2 is source-complete, independently reviewed and exact-head green. Python Review remains canonical ranking authority.

## Stage 4 — isolated compatibility/release lane built; live acceptance not run

`agent/stage4-b25-b28-compat-release-20260919` contains isolated compatibility/acceptance/release-preparation work. Lane head `d2ce905ff67410586f86e38bafd93ce4e998e4d1` passed lane CI `35464436789`. This is not release authorization or live acceptance.

Spec numbering controls:

- **B25:** named synthetic corpus plus genuine provenance-labelled 30-site baseline/candidate gate. Historical summaries and synthetic fixtures cannot satisfy the real gate.
- **B26:** reproduced own-site serving defects/fixes with source evidence; deployed HTTP behavior is verified only on the exact eventual release.
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

Stay on Stage 2. Close the remaining B13/B14 explicit-provenance gap for contextual Coming Soon/open/closed and store-finder/form/sitemap entity evidence without inferring identity from matching NAP strings. Then obtain a fresh independent review of the complete B06–B18 source shape, fix any material findings with behavioral regressions, and require fresh exact-head FixList CI. Only after B06–B18 are genuinely complete, independently reviewed and exact-head green should shared Stage-3 integration begin.
