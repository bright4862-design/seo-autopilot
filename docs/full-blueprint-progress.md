# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current requirement ledger. Historical checkpoints remain in Git history and the executable plans under `docs/superpowers/plans/`. The approved spec controls over stale handoff wording.

## Release sequencing

Stage 1 and the later blueprint remain separate release states.

- Stage-1 source is merged on `main`; exact-source production publication/promotion/non-owner acceptance remains a separate guarded operation.
- `main` was last accepted for this later-stage work at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing V7 runtime/public-build changes and durable ownership-before-admission fix #308. Treat newer repository metadata as non-authorizing until the Stage-1 release operator records exact-source publication and fresh non-owner acceptance.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do not merge later-stage work to `main`, publish Base44, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets or otherwise move production while the Stage-1 release operator owns that cutover.
- After Stage-1 live acceptance is recorded, reconcile this integration line onto the then-current accepted `main` without reverting V7 or #308, then require fresh exact-head combined CI.

## Stage 1 — source complete; live release acceptance separate

Stage-1 established published-route evidence identity, authenticated authority/persistence/readers, image/template/search-evidence correctness, historical signature compatibility, preview privacy and the named synthetic acceptance runner.

Historical detail: `docs/stage-one-evidence-acceptance.md`.

The labelled corpus is explicitly synthetic and cannot satisfy the genuine 30-site full-blueprint gate. The frozen scanner revision checked by later-stage CI remains `01ebe8e90df1e6bd`.

## Stage 2 — B06–B18 source integrated; follow-up independent review still open

Integration surface: PR #303 / `agent/full-blueprint-stage2-coverage-b06-20260919`.

The isolated lane PRs were review/CI inputs only and must not be merged directly to `main`.

### Requirement status

- **B06 — shared bounded coverage scheduler/internal-link verification:** integrated. One finite follow-up scheduler reuses hardened robots/DNS/SSRF/redirect/body/deadline controls. Probe-only URLs never enter the Standard-150 assessed set or denominator. Verified unsampled broken-link evidence has authenticated downstream coverage.
- **B07 — active soft-404:** integrated. Deterministic same-origin/effective-scope missing-page candidates use the shared finite scheduler; challenge/429/robots/budget/deadline/incomplete states remain unknown; synthetic probes stay outside assessed pages; authenticated downstream proof exists.
- **B08 — redirect meaning:** integrated. Normalization, usable, wrong/catch-all, unusable and unverified access are distinct; challenged/rate-limited destinations remain unknown and verified ordinary 404 remains unusable.
- **B09 — sitemap integrity:** source/helper/probe integration is present through the shared scheduler. Exact root/child provenance and failure reasons must survive if this evidence is later promoted into customer-visible findings; no customer finding is invented by Stage 2 merely to expose internal evidence.
- **B10 — near-duplicate main content:** accepted main-content seam is integrated. Common chrome is excluded; raw substantive page copy is not retained; bounded deterministic SHA-256 shingle fingerprints/signature metadata support conservative internal analysis. Fresh whole-stage review proved those deterministic intermediates must not cross HTTP/authority boundaries; the current projection strips them before those boundaries. Any future customer-visible duplicate finding requires authenticated downstream/privacy proof.
- **B11 — money-page reachability:** integrated on the final retained Standard-150 set. Exact retained internal edges only; sitemap discovery cannot become an inlink; challenged/unusable sources are re-gated out; unsampled links do not expand the assessed set; `sitewide_orphan_claim=false`; transient private link cache is removed before publication and is also denied by the common output projection.
- **B12 — raw/rendered hub links:** integrated. Up to five eligible hubs may be disclosed while actual browser execution remains inside the existing three-page follow-up ceiling. Only successful accepted render evidence completes a pair; failed/unassessed states remain explicit; rendered links cannot expand the assessed set.
- **B13 — local entity completeness/status:** integrated as evidence-only. Accepted usable HTML produces bounded JSON-LD local-entity observations. Explicit structured status fields or conservative accepted title/H1 phrases can establish open/closed/Coming Soon context; arbitrary body wording cannot. Missing regular hours are contextual for verified Coming Soon/closed states, required for verified open, and unknown when applicability is unknown. Raw observations/contact evidence are stripped before output/authority; the scan aggregate is reduced to non-content state/count proof.
- **B14 — cross-page NAP/source provenance:** integrated conservatively as evidence-only. Cross-page identity still requires an explicit absolute HTTP(S) JSON-LD `@id` observed on at least two distinct page URLs. Matching NAP/family never proves identity. Explicit form/store-finder references are recorded only when they carry the exact already-verified entity ID; sitemap provenance comes only from retained page discovery evidence. None of those sources can promote a missing/unverified entity identity. `sitewide_consistency_claim=false`. Exact entity keys/page URLs/status-heading provenance are removed from the external aggregate projection.
- **B15 — contextual freshness:** integrated as evidence-only. A fail requires current-content intent plus contradictory current-scoped temporal evidence. Old articles/years/dated paths alone do not fail; historical/archive wording remains historical; year-only dates use 31 December conservatively. Per-page producer evidence is stripped before external authority/customer boundaries until an explicit downstream contract exists.
- **B16 — URL variants:** integrated. Exact path/query/case/reserved-escape/empty-query identity is retained; no sibling-host expansion; no duplicate claim without independent equivalence evidence; redirect meaning delegates to B08.
- **B17 — page weight + optional CrUX:** integrated. Decoded HTML, inline script/style and transfer-body bytes remain distinct; transfer bytes are directly measured from raw response chunks before decoding, never inferred from `Content-Length`, and remain unknown on access-limited pages. Ordinary scans authenticate CrUX as disconnected; controlled authorized/current/stale/unavailable adapter cases are tested. No live provider connection is claimed.
- **B18 — optional GSC:** integrated at source/contract level. Ordinary scans authenticate GSC as disconnected with `provider_data_admitted=false`; controlled connected/stale/unavailable cases require owner authorization, exact scan identity, exact retained URL membership, conflict rejection and Standard-150 ceiling. No live GSC connection or traffic/indexing claim is made.

### Fresh whole-stage independent review correction

The fresh combined B06–B18 CodeRabbit review found one material P1 defect in prior executable checkpoint `e906ef69c7b7deab3a1014c702b4f3af1453c54c`: B10 deterministic main-content fingerprint intermediates and B13 normalized local-entity observations were still present on page dictionaries forwarded into the synchronous result and durable authority path.

The correction is now implemented and regression-covered:

- `scanner-api/app/page_output_privacy.py` fail-closes the external page projection for B10/B13/B14/B15 producer-only fields and the defensive B11 private cache;
- `scanner-api/app/render_evidence_quality.py` applies that projection at the common post-crawl boundary after B13/B14 scan aggregation but before synchronous output and durable authority handling;
- the B13/B14 aggregate itself is reduced to non-content state/count diagnostics, removing exact page URLs, entity IDs and accepted-heading status provenance before the external boundary;
- four behavioral regressions inject distinctive B10/B13/B15/private-link sentinels and prove absence from the post-crawl result, response-budget projection, authority review payload, and signed completion/limited-result envelopes.

Detailed correction record: `docs/superpowers/plans/2026-09-20-stage2-output-privacy-hardening.md`.

### Latest exact executable checkpoint

Exact executable head: `e42151d4f10007f4f1660de4a2bbda927a4696eb`.

FixList CI `35493637000` — **SUCCESS** on both jobs:

- immutable checkout verified the exact SHA;
- Ubuntu 24.04.5 / Python 3.12.14;
- the Node 20 setup resolved Node **20.20.2**; this run is not evidence for Node 20.19.5 specifically;
- root scanner regressions: **115 passed**;
- full `scanner-api`: **1,988 passed / 18 intentional skips** (2,006 collected), including **4 new Stage-2 output-privacy regressions**;
- labelled Stage-1 corpus: synthetic, **14 cases / 55 assertions**, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: `sha256:ace9b08b88ea3c29faecc00cc0c9567deb9687cc90f1c503723bcd73f80a86dc`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build passed.

Documentation-only commits may sit above that executable checkpoint. Do not attribute executable certification to a docs-only head unless its own CI is separately green.

Detailed current records include:

- `docs/superpowers/plans/2026-09-19-stage2-serialized-review-hardening.md`
- `docs/superpowers/plans/2026-09-20-stage2-b11-reachability-provenance.md`
- `docs/superpowers/plans/2026-09-20-stage2-b12-hub-render-evidence.md`
- `docs/superpowers/plans/2026-09-20-stage2-b13-b14-local-entity.md`
- `docs/superpowers/plans/2026-09-20-stage2-b15-contextual-freshness.md`
- `docs/superpowers/plans/2026-09-20-stage2-connected-provider-evidence.md`
- `docs/superpowers/plans/2026-09-20-stage2-transfer-body-evidence.md`
- `docs/superpowers/plans/2026-09-20-stage2-provider-result-integration.md`
- `docs/superpowers/plans/2026-09-20-stage2-output-privacy-hardening.md`

### Stage 2 completion gate

Stage 2 is **not yet recorded complete**. The one material fresh whole-stage review finding has been reproduced, fixed and exact-head CI green. Before shared Stage-3 integration, a fresh independent follow-up review must verify the corrected current B06–B18 source shape and confirm that no material finding remains. Any new material finding must receive a reproducing behavioral regression, the smallest safe fix and fresh exact-head CI.

Keep any internal evidence-only B09/B10–B18 field internal unless a real producer → Review → signed authority → persisted rows → customer/card/handoff/export chain is intentionally added. Preserve all Standard-150/security/privacy/historical-reader invariants during remaining review hardening.

No account-specific CrUX/GSC connection is required for an otherwise valid scan; disconnected and controlled-response behavior is the source acceptance requirement unless a live connection is actually authorized and verified.

## Stage 3 — isolated lanes built; shared integration held behind Stage 2

Existing lane work is implementation input only until Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919` @ `e74d87acd0cec2955402b96f635f13bc275f3a91`, CI `35463839728`: B19 exact **impact × reach × page value × confidence** evidence/explanations and B20 explicit evidenced shared root causes across SEO/GEO. Family similarity is never root-cause proof.
- `agent/stage3-b21-b24-delivery-20260919` @ `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`, CI `35463511347`: B21 exact unions/count distinctions/rank-before-truncate; B22 authenticated evidence-led private previews; B23 evidenced root-cause score caps preserving existing ceilings; B24 backward-compatible handoff v2.

Do not integrate B19–B24 into shared ranking/authority/customer interfaces until Stage 2 receives clean follow-up independent review and exact-head certification. Python Review remains canonical ranking authority.

## Stage 4 — isolated compatibility/release lane built; live acceptance not run

`agent/stage4-b25-b28-compat-release-20260919` @ `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, contains isolated compatibility/acceptance/release-preparation work. This is not release authorization or live acceptance.

Spec numbering controls:

- **B25:** named synthetic corpus plus genuine provenance-labelled 30-site baseline/candidate gate;
- **B26:** reproduced own-site serving defects/fixes with source evidence;
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility;
- **B28:** exact-source review/CI/deployment/live acceptance, including runtime identities, rollback, one bounded real customer Standard-150 submit → persistence → exact `scan_id` reload/history → linked rescan verification.

The genuine 30-site baseline/candidate gate remains **not assessed**. Historical summaries and synthetic fixtures cannot satisfy it. No Stage-4 deployment, live customer scan or production acceptance is claimed.

## Hard invariants

- Standard-150 assessed-page cap and truthful denominators remain authoritative.
- Stage-2 follow-up checks share one finite request pool; no second scheduler/budget.
- Existing robots ownership, DNS/SSRF, redirect, body and deadline protections remain authoritative.
- One active scan/account, cancellation/terminalization and exact scan isolation remain intact.
- Missing, blocked, stale, disconnected or invalid evidence remains unknown rather than invented pass/fail evidence.
- Historical signatures/readers remain compatible; unknown evidence versions fail closed.
- Preview privacy and entitlement boundaries remain intact.
- Python Review remains canonical priority/ranking authority.
- Premium/Grok remain outside this integration.
- Synthetic/historical data never substitutes for the genuine 30-site gate or real customer live acceptance.

## Exact next engineering action

Stay on Stage 2 for a fresh independent follow-up review of executable head `e42151d4f10007f4f1660de4a2bbda927a4696eb` plus the privacy correction. Correct any new material issue with a reproducing regression and fresh exact-head CI. Only when that gate is genuinely green should the serialized owner begin integrating Stage 3 B19–B24 into the shared ranking/authority/persistence/customer path.
