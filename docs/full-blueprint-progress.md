# Full blueprint progress

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

### Latest executable slice — B22 private-preview identity type fail-closed

Fresh inspection found `scanner-api/app/stage3_delivery.py::_preview_eligible()` compared candidate and requested `scan_id` / `owner_id` with raw Python equality. Matching structured values could therefore pass the exact-owner/exact-scan customer preview boundary even though structured producer/debug identity is not a valid authority identity.

- **RED `1b3f5ae219a733f8b9642761c0ef75d89f4ef65e`, FixList CI `35571403257`:** added `scanner-api/tests/test_stage3_b22_preview_identity_type_fail_closed.py`. Root tests `115 passed`; scanner-api `2 failed, 2090 passed, 18 skipped`. Exactly the two malformed structured-identity regressions failed by returning `findings` instead of `not_available`; the literal exact-string control passed. Lint/typecheck/generated-contract/frontend/build passed; corpus/frozen/image steps were skipped after the intentional RED scanner failure.
- **GREEN `4ef7fb44a1bdb614d7bea764aa121dfac355f61c`, FixList CI `35571774891`:** requested scan/owner IDs must now be actual non-empty strings and candidate scan/owner IDs actual strings before literal exact equality. No coercion or normalization was added; dict/list/bool/numeric identity fails closed. RED→GREEN implementation compare changes exactly `scanner-api/app/stage3_delivery.py`, 10 additions / 2 deletions.
- Exact GREEN evidence: both jobs passed; root tests `115 passed`; scanner-api `2092 passed, 18 skipped`; all three new B22 regressions passed; labelled synthetic corpus `14/55` with `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd`; scanner image `sha256:a52ecebf7b90fdd6793ecf106444052d5d65737ca21a443c28e51f4a109d28a0`; lint/typecheck/generated contracts/frontend/build all passed.
- Detailed checkpoint: `docs/superpowers/plans/2026-09-21-stage3-b22-preview-identity-type-fail-closed.md`.

Prior B21 denominator hardening remains certified at `ebd83739b49da4a7aabd3fef3c171da23cdd8dd8`, CI `35567449548`; its plan is `docs/superpowers/plans/2026-09-21-stage3-b21-population-denominator-fail-closed.md`. Prior B19/B20/B23/B24 fail-closed slices remain part of the same serialized branch history and retain their exact regressions.

### Requirement state

- **B19 partial:** canonical signed Review carries exact versioned **impact × reach × page value × confidence**, truthful unknown denominators and explanations. Repair leverage is not a fourth factor. Numeric source evidence and downstream factor ranges fail closed. Durable V7 FixItem/card/export consumption remains release-gated.
- **B20 partial:** verified shared-root-cause grouping requires explicit versioned same-cause evidence, actual string root-cause/surface/reference identifiers, and trusted enclosing exact producer identity. Family similarity or coercible structured/debug identity cannot establish trust. Durable customer projection remains open.
- **B21 partial:** signed Review carries exact unique affected-page, observation, known-population and displayed-sample counts; exact unions precede samples and all eligible B19 candidates rank before truncation. Malformed numeric counts fail closed, and a known population smaller than the exact affected union remains unknown. Durable persistence/card/export proof remains open.
- **B22 partial:** signed evidence-led preview source requires verified evidence and trusted exact producer identity; customer private preview now also requires literal non-empty string requested scan/owner identity and string candidate identity before exact equality. It prefers verified impact-4/5 findings with a two-item cap, otherwise one best verified fallback, and emits fixed sufficient-coverage wording only for explicit sufficient coverage. Fresh independent review and durable exact-owner/exact-scan V7 preview proof remain open.
- **B23 partial:** only explicit verified B20 root-cause evidence may contribute a documented score cap; conflicts, unverified/cross-scan evidence and malformed caps fail closed while stricter access/sample/incomplete ceilings remain authoritative. Coverage state is bounded to documented vocabulary. Durable customer-visible adjusted-score persistence/card/export consumption remains open.
- **B24 partial:** signed handoff-v2 requires literal trusted exact scan identity and exact-scan verified B20 root causes; historical v1 reader compatibility remains preserved and suppressed findings require literal `operator_authorized is True`. Customer scan/fix/B19-factor projection is positive-allowlisted, type-checked and range-checked; impossible B21 population denominators remain unknown. Durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.

## Stage 3 current gate

Stage 3 is **not complete**. Latest executable source GREEN is `4ef7fb44a1bdb614d7bea764aa121dfac355f61c`, FixList CI `35571774891`. This documentation update occurs after source certification, so the resulting final persisted checkpoint branch head must itself receive exact-head FixList CI before it is called stable.

Open gates:

1. one genuinely fresh independent review of the latest corrected B22/B24 shared authority/privacy boundary, including upstream B19/B20/B21/B23 evidence feeding signed delivery; an automatic-review skip is not approval;
2. separate Stage-1 operator records exact-source publication and fresh non-owner acceptance;
3. reconcile this branch onto then-current accepted `main` without reverting V7/#308 and run exact integrated-head CI;
4. prove real V7 B19/B21/B22/B23/B24 producer -> signed authority -> persisted rows -> exact-owner/exact-scan read/reload/history -> customer card/export/preview seams, including suppressed/operator privacy and historical-v1 compatibility.

Runtime note: GitHub setup requested Node 20 but resolved Node `20.20.2`; exact Node 20.19.5 evidence is not claimed. GitHub Actions also emitted its Node-20 action-runtime deprecation warning.

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
