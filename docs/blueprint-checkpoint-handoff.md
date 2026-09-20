# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current serialized handoff for the FixList full-scanner blueprint. Historical checkpoints remain in Git history and the linked executable plans. The approved spec controls over older handoff paraphrases.

## Release boundary

- Stage-1 publication/promotion/live non-owner acceptance remains owned by the existing exact-source release operator.
- `main` remains frozen for later-stage integration at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`; newer repository metadata is not authorization to move the Stage-1 cutover.
- Do not use the later-stage integration branch to publish, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets, or otherwise move production.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- After Stage-1 live acceptance, reconcile this branch onto the then-current accepted `main` without reverting V7 route/public-build changes or #308, then run fresh exact-head combined CI.

## Current Stage-2 executable checkpoint

Exact executable head: `fda78e9aa4fe823e2067837041f3cba538712f3b`.

FixList CI `35495894222` — **SUCCESS** on both jobs:

- immutable checkout: passed;
- root scanner regressions: passed;
- full Python `scanner-api` suite: passed, including two new future-shape fail-closed privacy regressions;
- labelled Stage-1 synthetic corpus: passed and remains synthetic rather than the genuine B25 30-site gate;
- frozen scanner revision verification: passed;
- production scanner-image build: passed;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The immediately preceding checkpoint `e42151d4f10007f4f1660de4a2bbda927a4696eb` had 115 root regressions and 1,988 scanner-api passes / 18 intentional skips. The current GitHub job proves the expanded full suite green; do not invent an exact new pass count unless it is taken from runner output.

## New RED → GREEN privacy hardening

The earlier whole-stage CodeRabbit review found the material P1 boundary leak where B10 deterministic content fingerprints and B13 raw local-entity observations could cross synchronous/durable authority output. The common post-crawl projection fixed that known shape and was already regression-covered.

A fresh serialized source inspection found one remaining fail-open property in that projection: `project_local_entity_scan_evidence()` forwarded unknown future B13/B14 aggregate fields and unknown future `nap_consistency` fields by default. That meant a later producer/debug addition containing exact entity IDs, page URLs, raw observations or headings could silently become customer/persisted output without an explicit privacy decision.

RED commit: `661b9e2121c6f49bd50dedc64bdce1c73cf54b6b`.

- New file: `scanner-api/tests/test_stage2_output_privacy_fail_closed.py`.
- It injects future-shaped sensitive entity/page/text sentinels at aggregate, NAP and inconsistency levels.
- FixList CI `35495870104` failed specifically in the full Python `scanner-api` test step, while the separate lint/typecheck/contracts/frontend-build job passed. This is the expected regression proof against the old projection.

GREEN commit: `fda78e9aa4fe823e2067837041f3cba538712f3b`.

- `scanner-api/app/page_output_privacy.py` now positively allowlists the B13/B14 aggregate top-level version/count/truncation fields.
- B13 completeness rows remain allowlisted.
- B14 NAP summary fields are now positively allowlisted instead of copying every unknown field except `inconsistencies`.
- B14 inconsistency rows remain allowlisted to field names/source count/provenance only.
- Unknown future producer/debug keys therefore fail closed automatically.
- Existing page-level projection and the common post-crawl placement remain unchanged; current approved non-content state/count diagnostics still survive.

Detailed checkpoint: `docs/superpowers/plans/2026-09-20-stage2-output-privacy-fail-closed.md`.

## Stage-2 material state

- **B06:** shared finite coverage scheduler / unsampled internal-link verification integrated with authenticated downstream proof.
- **B07:** active soft-404 orchestration integrated through the same finite scheduler; blocked/challenged/robots/budget/deadline/incomplete evidence remains unknown.
- **B08:** redirect meaning distinguishes harmless normalization, usable, wrong/catch-all, unusable and unverified access; challenge/block/rate-limit evidence remains unknown.
- **B09:** sitemap integrity shares the same scheduler; any future customer promotion must retain exact root/child provenance and failure reasons.
- **B10:** accepted main-content evidence integrated. Raw copy is not retained; deterministic fingerprints remain internal-only and are stripped before HTTP/authority/persistence boundaries.
- **B11:** sample-scoped retained-set depth/inlink/navigation evidence integrated; sitemap discovery cannot become an inlink; unsampled targets cannot expand the assessed set; `sitewide_orphan_claim=false`.
- **B12:** raw/rendered hub evidence integrated under the existing bounded browser-followup ceiling; failed/unassessed states remain explicit; rendered links cannot expand Standard 150.
- **B13:** contextual local entity/status completeness integrated as evidence-only; raw contact/identity observations are internal; external aggregate is now fail-closed by positive allowlist.
- **B14:** cross-page identity requires the same explicit absolute HTTP(S) JSON-LD `@id` on at least two distinct URLs; matching NAP/family never proves identity; `sitewide_consistency_claim=false`; external NAP summary is now fail-closed by positive allowlist.
- **B15:** contextual freshness integrated as evidence-only; old dates alone cannot fail; producer evidence remains internal until an authenticated downstream contract exists.
- **B16:** exact URL variant identity integrated; no sibling-host expansion or duplicate claim without verified equivalence.
- **B17:** direct raw transfer-body bytes are distinct from decoded HTML/inline bytes; CrUX defaults to authenticated disconnected state unless an authorized exact-scan response exists.
- **B18:** GSC defaults to authenticated disconnected state; connected/stale/unavailable contracts require authorization, exact scan identity, exact retained URL membership, conflict rejection and Standard-150 ceiling.

## Stage 2 remains open at the final independent-review gate

Do not start shared Stage-3 integration yet. Source integration is materially complete, and the latest privacy hardening has RED → GREEN evidence plus exact executable CI. Remaining serialized gate:

1. stabilize the documentation head and require its exact-head FixList CI;
2. obtain one fresh independent follow-up review of the corrected current PR #303 head;
3. if a new material issue is reported, reproduce it with a behavioral regression and apply the smallest safe correction;
4. require fresh exact-head FixList CI after any executable correction;
5. keep internal B09/B10–B18 evidence internal unless a deliberate producer → Review → signed authority → persisted rows → customer/card/handoff/export chain is added;
6. preserve Standard-150 cap, one finite probe budget, robots/DNS/SSRF/redirect/body/deadline controls, one active scan/account, exact scan isolation, historical signatures/readers, preview privacy and Python Review authority.

A live account-specific CrUX/GSC connection is neither claimed nor required for an otherwise valid scan; disconnected behavior plus controlled authorized-response behavior is the current source acceptance contract.

## Stage 3 — isolated lanes built, not shared-integrated

Reuse only after Stage 2 closes:

- `agent/stage3-b19-b20-decisions-20260919` / `e74d87acd0cec2955402b96f635f13bc275f3a91`, CI `35463839728`: B19 **impact × reach × page value × confidence** and B20 explicit evidenced SEO/GEO root causes. Family similarity is not root-cause proof.
- `agent/stage3-b21-b24-delivery-20260919` / `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`, CI `35463511347`: B21 exact unions/rank-before-truncate, B22 authenticated private preview selection, B23 evidenced root-cause score caps preserving existing ceilings, B24 backward-compatible handoff v2.

These are integration-ready inputs, not product completion. Python Review remains canonical ranking authority. Shared ranking/authority/persistence/customer interfaces remain serialized integration work.

## Stage 4 — isolated lane built, not released

Reuse `agent/stage4-b25-b28-compat-release-20260919` / `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, only after Stage 3 shared integration.

Spec numbering controls:

- **B25:** named synthetic corpus + genuine provenance-labelled 30-site baseline/candidate gate;
- **B26:** reproduced own-site serving defects/fixes;
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility;
- **B28:** exact-source review/CI/deployment/live customer acceptance.

The genuine 30-site gate remains **not assessed**. Historical summaries and synthetic fixtures cannot become a pass. No Stage-4 deployment, live customer scan or acceptance has been run by this integration branch.

## Exact next action

Wait only for the documentation-head CI caused by these persisted records, then request one fresh independent review on that stable PR #303 head. If it is clean, record Stage 2 complete and begin serialized integration of the existing B19/B20 and B21–B24 lane deltas. Do not move production.
