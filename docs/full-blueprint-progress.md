# Full blueprint progress

## Current checkpoint — 2026-09-23

The original B01–B28 scanner blueprint is complete through Stages 1–4 and landed in `main`, per the release owner's 2026-09-23 handoff. Stage 4 landed through PR #319 (`dad5722fe787d608289ecb358acd65e87258a0e8`); subsequent production recovery moved the product to V8. Do not rebuild these stages or apply the obsolete Stage-1 freeze below.

Freshly read repository main: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`. Current AI integration checkpoint inspected: `8faf869a66316bd7cbe3d749028853748a392944`. Integration-branch implementation is not a production release claim.

The active roadmap and next integration gates are recorded in [AI-layer current checkpoint](ai-layer/2026-09-23-current-checkpoint.md). The approved AI design is [the 2026-09-22 blueprint](superpowers/specs/2026-09-22-ai-layer-architecture-blueprint.md). The single AI Integrator owns shared seams, merges and deployment. Preserve Standard 150, V8, sealed authority and historical results; keep runtime AI/chat disabled.

Production acceptance in the owner's handoff: worker `fixlist-standard150-worker-00095-sn2`; Funbooker scan `6ab2abb3763febb79a7470e4` and rerun `6ab314008da962a9f8c58929` completed and rendered; rerun links to `6ab272fc6dfa7f9faf97a90f`. These live observations were supplied by the release owner, not independently repeated in this documentation run.

## Archived checkpoint — 2026-09-21, superseded

Everything below preserves the historical implementation/test record. Its descriptions of current main, incomplete stages, freezes, resume instructions and release gates are historical, not current instructions. Dated test results apply only to the SHAs originally recorded.

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec's exact B01–B28 semantics control over older handoff paraphrases. Detailed RED/GREEN history is retained in executable plans under `docs/superpowers/plans/`; this file is the concise current-state ledger.

## Release sequencing / freeze

- Direct `main` was refreshed during the 2026-09-21 serialized work and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing V7 runtime/public-build changes and durable ownership-before-admission fix #308.
- Current-main `docs/stage-one-evidence-acceptance.md` still records exact-source production publication and fresh non-owner acceptance as pending; no accepted Stage-1 production deployment is recorded.
- Worker candidate `fixlist-standard150-worker-00091-bdr` and cutover-pause run `35462502364` are historical checkpoints only, not permission to promote, mutate admission/queues/scheduler, launch a production scan, or rebuild.
- Serialized later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303. Keep it off `main` until the single Stage-1 release operator records exact-source publication and fresh non-owner acceptance.
- After that separate gate closes, reconcile onto the then-current accepted `main` without reverting V7/#308 and require fresh exact integrated-head FixList CI before durable customer-path activation.
- No Premium/Grok enablement, schema/RLS broadening, secret rotation, fabricated provider connection, production deployment, worker promotion, or competing live scan is authorized from this branch.

The labelled Stage-1 corpus remains explicitly synthetic: 14 cases / 55 assertions at frozen scanner revision `01ebe8e90df1e6bd`. Synthetic fixtures or historical summaries never satisfy B25's genuine provenance-labelled 30-site gate.

## Stage 2 — B06–B18 complete for implementation / independent review / exact-head CI

Stable corrected Stage-2 checkpoint: `10f51529bf5bf64b7b24ab8424f3ae821de46b39`; exact-head FixList CI `35500580582` passed and CodeRabbit follow-up `5748778814` returned no actionable finding. This is not a production-release claim.

- **B06 complete:** one finite shared follow-up scheduler; probe-only requests cannot inflate Standard-150 assessed pages or denominators.
- **B07 complete:** active soft-404 producer/orchestration reuses the scheduler; robots/challenge/429/budget/deadline/incomplete remains unknown.
- **B08 complete:** redirect meaning distinguishes normalization, usable, wrong/catch-all, unusable and unverified destinations with customer-safe wording.
- **B09 complete:** robots-declared sitemap integrity and bounded variant probes reuse the same finite scheduler rather than creating a second budget.
- **B10 complete:** accepted-main-content fingerprints/shingles/raw copy remain internal. Direct authenticated `/scan` privacy regression `d9061f23edd0a0541b017f42297bf60a9c401560`, CI `35524582769`, proves B10/B11/B13/B15 private sentinels do not survive the serialized response.
- **B11 complete:** retained-set depth/inlink/navigation evidence uses exact retained identity and truthful sample scope; sitemap membership is not an inlink.
- **B12 complete:** bounded raw/rendered hub-link evidence uses the existing browser-followup ceiling and preserves completed/failed/unassessed states.
- **B13 complete:** contextual local-entity/status completeness keeps raw identity/contact evidence internal and exposes only positive-allowlisted aggregates.
- **B14 complete:** cross-page entity identity requires the same explicit absolute HTTP(S) JSON-LD `@id` on distinct pages; matching NAP/family alone is insufficient.
- **B15 complete:** freshness requires current-content intent plus contradictory temporal evidence; old dates alone do not fail.
- **B16 complete:** bounded URL-variant probes preserve exact identity and do not expand sibling-host scope or invent duplicate claims.
- **B17 complete:** raw transfer bytes remain separate from decoded/inline bytes; CrUX remains disconnected by default and controlled evidence requires owner authorization, exact scan identity and valid observation time.
- **B18 complete:** GSC remains disconnected by default; controlled evidence requires owner authorization, exact scan identity, exact retained-URL membership, conflict rejection, Standard-150 ceiling and valid observation time.

## Stage 3 — B19–B24 in progress

Existing isolated lanes were integrated serially, never merged directly to `main`: B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> shared `c3f9d685e17b26c372a5a47403b478caec36ed2a`; B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> shared `3aebc7375e854ce063ac0bcec0a46210473e061c7`; combined lane FixList CI `35501672504` passed.

### Latest executable slice — B21/B24 malformed observation-count evidence stays unknown

Fresh B21/B24 inspection found `summarize_candidate_counts()` strictly rejected malformed explicit `observation_count` values but then always normalized `observations` through `_list()` and took its length. Missing or malformed observations therefore became an empty list, allowing invalid explicit evidence to silently turn into a signed zero rather than remain unknown.

- **RED `913dfd011aced1cd6a348468dcfd357bd316c40a`, FixList CI `35581103845`:** three new regressions cover malformed explicit count without observations, structured private/debug count through B24 handoff, and the legitimate real-observation-list fallback. Immutable checkout matched; the lint/typecheck/generated-contract/frontend/build job passed; root scanner regressions passed; Python scanner-api failed on the new negative cases and corpus/frozen/image steps were skipped after the intentional RED.
- **Source correction `f2afc1cfa87a9fbcecbd33e4b378d2edc737f658`:** B21 now uses a real list/tuple length only when actual observation evidence exists; explicitly present malformed count/observation evidence remains `None`; only the historical case where both fields are entirely absent retains the zero fallback. B24 inherits the same truthful unknown through the shared serializer. RED-to-source compare changes only `scanner-api/app/stage3_delivery.py`, 8 additions / 3 deletions.
- **GREEN `f2afc1cfa87a9fbcecbd33e4b378d2edc737f658`, FixList CI `35581439449`:** both jobs passed. Immutable checkout, root scanner regressions, full Python scanner-api suite including the new regressions, labelled Stage-1 synthetic corpus, frozen revision verification, production scanner image build, lint, typecheck, generated release contracts, frontend contract tests and production build all passed. The available GitHub job metadata did not expose trustworthy pytest totals or image digest for this run, so none are invented here.
- Detailed checkpoint: `docs/superpowers/plans/2026-09-21-stage3-b21-observation-count-unknown-fail-closed.md`.

Prior B22/B24 upstream signed-projection coercion hardening remains certified at final persisted checkpoint `fc7d9359870efdfa437b2c9c7e38c115c198de00`, exact-head CI `35577485322`; its source GREEN was `dfb9043d3cbf510ec867c68a5cde02c7cea29323`, CI `35577052441`. Prior B19/B20/B21/B22/B23/B24 fail-closed slices remain part of the same serialized branch history and retain their exact regressions.

### Requirement state

- **B19 partial:** canonical signed Review carries exact versioned **impact × reach × page value × confidence**, truthful unknown denominators and explanations. Repair leverage is not a fourth factor. Numeric source evidence and downstream factor ranges fail closed. Durable V7 FixItem/card/export consumption remains release-gated.
- **B20 partial:** verified shared-root-cause grouping requires explicit versioned same-cause evidence, actual string root-cause/surface/reference identifiers, and trusted enclosing exact producer identity. Stage-3 customer-bound group/member/family/reference identifiers also reject structured upstream coercion. Durable customer projection remains open.
- **B21 partial:** signed Review carries exact unique affected-page, observation, known-population and displayed-sample counts; exact unions precede samples and all eligible B19 candidates rank before truncation. Malformed numeric counts fail closed, malformed explicit observation evidence no longer becomes a fabricated zero, a real observation list remains a truthful fallback, a known population smaller than the exact affected union remains unknown, and customer-bound displayed IDs reject structured coercion. Durable persistence/card/export proof remains open.
- **B22 partial:** signed evidence-led preview source requires verified evidence and trusted exact producer identity; exact-owner/exact-scan customer access requires literal non-empty string identity. Producer rule/title fields retain only literal string evidence with safe fallback instead of stringifying structured/debug values. Fresh independent review and durable exact-owner/exact-scan V7 preview proof remain open.
- **B23 partial:** only explicit verified B20 root-cause evidence may contribute a documented score cap; conflicts, unverified/cross-scan evidence and malformed caps fail closed while stricter access/sample/incomplete ceilings remain authoritative. Customer-bound root-cause-cap identifiers reject structured coercion. Durable customer-visible adjusted-score persistence/card/export consumption remains open.
- **B24 partial:** signed handoff-v2 requires literal trusted exact scan identity and exact-scan verified B20 root causes; historical v1 reader compatibility remains preserved and suppressed findings require literal `operator_authorized is True`. Scan metadata, fix title/ID, family/evidence references and vendor-owner projection fail closed before signing; malformed B21 observation counts now remain unknown rather than becoming signed zero. Durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.

## Stage 3 current gate

Stage 3 is **not complete**. Latest executable source GREEN is `f2afc1cfa87a9fbcecbd33e4b378d2edc737f658`, FixList CI `35581439449`. The executable plan and ledgers are being persisted after source certification, so the resulting final branch head must itself receive exact-head FixList CI before it is called the stable checkpoint.

Open gates:

1. one genuinely fresh independent review of the latest corrected B22/B24 shared authority/privacy boundary, including upstream B19/B20/B21/B23 evidence feeding signed delivery; an automatic-review skip or old September 19 review is not approval;
2. separate Stage-1 operator records exact-source publication and fresh non-owner acceptance;
3. reconcile this branch onto then-current accepted `main` without reverting V7/#308 and run exact integrated-head CI;
4. prove real V7 B19/B21/B22/B23/B24 producer -> signed authority -> persisted rows -> exact-owner/exact-scan read/reload/history -> customer card/export/preview seams, including suppressed/operator privacy and historical-v1 compatibility.

Runtime note: GitHub setup requests Node 20; prior runs resolved Node `20.20.2`, so exact Node 20.19.5 evidence is not claimed unless separately proven.

## Stage 4 — held

Canonical isolated lane remains `agent/stage4-b25-b28-compat-release-20260919` at checkpoint `d2ce905ff67410586f86e38bafd93ce4e998e4d1`; prior lane CI `35464436789` passed. It must not be duplicated or shared-integrated before Stage 3 applicable acceptance.

- **B25 incomplete:** named synthetic corpus exists, but the genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`. Synthetic mini-fixtures and historical summaries do not satisfy it.
- **B26 partial:** isolated own-site serving-defect reproduction exists; shared integration/acceptance remains open.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared integration/acceptance remains open.
- **B28 incomplete:** no full-blueprint exact-source deployment/live acceptance has been performed. Required live site/six-V7/worker identity reconciliation, rollback proof, and real customer submit -> persistence -> reload/history -> rescan acceptance remain open.

## Next serialized action

1. Certify this slice's final persisted plan/ledger checkpoint head with exact-head FixList CI and record it in PR #303 without mutating that certified source afterward.
2. Refresh PR #303 review state. Require a genuinely fresh independent review; do not count an automatic-review skip as approval and do not repeatedly dispatch broken/skipped launchers.
3. Keep V7 durable/customer mutation and shared Stage-4 integration held while Stage-1 publication/non-owner acceptance remains open.
4. When that separate gate closes, reconcile onto accepted `main`, preserve V7/#308, run fresh exact integrated-head CI, and complete real B19–B24 persistence/customer seams before integrating the existing Stage-4 lane.
5. Only then execute the genuine B25 baseline/candidate and B28 live acceptance gates.
