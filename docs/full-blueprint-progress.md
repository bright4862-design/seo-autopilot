# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec's exact B01–B28 semantics control over older handoff paraphrases. Detailed RED/GREEN history is retained in the executable plans under `docs/superpowers/plans/`; this file is the concise current state ledger.

## Release sequencing / freeze

- `main` refreshed during the 2026-09-21 integration slice and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing the six V7 runtime/public-build changes and durable ownership-before-admission fix #308.
- Current-main `docs/stage-one-evidence-acceptance.md` still records Stage-1 exact-source production publication and fresh non-owner acceptance as pending.
- Worker candidate `fixlist-standard150-worker-00091-bdr` and cutover-pause run `35462502364` remain historical checkpoints only. No later-stage branch work authorizes promotion, admission mutation, a production scan, or a rebuild.
- Serialized later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Keep all later-stage work off `main` until the separate Stage-1 release operator records exact-source publication and fresh non-owner acceptance. After that, reconcile onto the then-current accepted `main` without reverting V7/#308 and require fresh exact integrated-head FixList CI before durable customer-path work.
- No Premium/Grok enablement, schema/RLS broadening, secret rotation, provider fabrication, production deployment, worker promotion, queue/scheduler mutation, or competing live scan is permitted from this branch.

The labelled Stage-1 corpus remains explicitly synthetic: 14 cases / 55 assertions; frozen scanner revision `01ebe8e90df1e6bd`. Synthetic fixtures or historical summaries never satisfy B25's genuine provenance-labelled 30-site gate.

## Stage 2 — B06–B18 complete for implementation / independent review / exact-head CI

Stable corrected Stage-2 checkpoint: `10f51529bf5bf64b7b24ab8424f3ae821de46b39`; exact-head FixList CI `35500580582` passed and CodeRabbit follow-up `5748778814` returned no actionable finding. This is not a production-release claim.

- **B06 complete:** one finite shared follow-up scheduler; probe-only requests cannot inflate Standard-150 assessed pages or denominators.
- **B07 complete:** active soft-404 producer/orchestration reuses the scheduler; robots/challenge/429/budget/deadline/incomplete remains unknown.
- **B08 complete:** redirect meaning distinguishes normalization, usable, wrong/catch-all, unusable and unverified destinations with customer-safe wording.
- **B09 complete:** robots-declared sitemap integrity and bounded variant probes reuse the same finite scheduler rather than creating a second budget.
- **B10 complete:** accepted-main-content fingerprints/shingles/raw copy remain internal. Direct authenticated `/scan` regression `d9061f23edd0a0541b017f42297bf60a9c401560`, CI `35524582769`, proves B10/B11/B13/B15 private sentinels do not survive the serialized response.
- **B11 complete:** retained-set depth/inlink/navigation evidence uses exact retained identity and truthful sample scope; sitemap membership is not an inlink.
- **B12 complete:** bounded raw/rendered hub-link evidence uses the existing browser-followup ceiling and preserves completed/failed/unassessed states.
- **B13 complete:** contextual local-entity/status completeness keeps raw identity/contact evidence internal and exposes only positive-allowlisted aggregates.
- **B14 complete:** cross-page entity identity requires the same explicit absolute HTTP(S) JSON-LD `@id` on distinct pages; matching NAP/family alone is insufficient.
- **B15 complete:** freshness requires current-content intent plus contradictory temporal evidence; old dates alone do not fail.
- **B16 complete:** bounded URL-variant probes preserve exact identity and do not expand sibling-host scope or invent duplicate claims.
- **B17 complete:** raw transfer bytes remain separate from decoded/inline bytes; CrUX remains disconnected by default and controlled evidence requires owner authorization, exact scan identity and valid observation time.
- **B18 complete:** GSC remains disconnected by default; controlled evidence requires owner authorization, exact scan identity, exact retained-URL membership, conflict rejection, Standard-150 ceiling and valid observation time.

## Stage 3 — B19–B24 in progress

Existing isolated lanes were integrated serially, never merged directly to `main`:

- B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> shared `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> shared `3aebc7375e854ce063ac0bcec0a46210473e061c7`.
- Combined lane FixList CI `35501672504` passed.

### B19 — partial

Canonical signed Review carries the exact versioned factor model **impact × reach × page value × confidence**, truthful unknown denominators, and versioned explanations. Repair leverage is not a substitute fourth factor or an extra fifth factor. RED `ac6ce27b3c492649537d80788f7b02b86ec39e5e` / CI `35501924104`; GREEN `7ba2df83d848fd643bb510374b7da5a18ac749f1` / CI `35501983203`. Durable V7 FixItem/card/export consumption remains release-gated.

### B20 — partial

Verified shared root-cause grouping requires explicit versioned same-cause evidence and trusted enclosing `scan_id == scan_run_id`; family similarity and repair-local identity alone cannot establish trust. Scan-isolation RED `6f1e2cc3ae519bbb494cab599579758f9efe427a` / CI `35503985665`; corrected through `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c` and `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481`; CI `35504200573`; follow-up `5749166024` found no unresolved material issue. Durable customer projection remains release-gated.

### B21 — partial

Signed Review carries exact unique affected-page, observation, known-population and displayed-sample counts, with exact unions before sampling and all eligible B19 candidates ranked before presentation truncation. Known numeric zero stays known; unknown composite priority cannot borrow impact. Stable checkpoint `7236c36cd65fe441a9a90c6a52db9a6c2342125a`, CI `35513093636`; follow-up `5750062094` clean. Durable persistence/card/export proof remains open.

### B22 — partial; latest preview projection privacy correction GREEN

The signed evidence-led preview source requires verified evidence and trusted exact identity, prefers verified impact-4/5 findings with a two-item cap, otherwise exactly one best verified fallback, and emits controller-owned sufficient-coverage wording only when coverage is explicitly sufficient. Arbitrary coverage prose and private producer evidence are excluded from signed/customer preview boundaries.

Prior hardening includes completion-Review positive allowlisting, authority fail-closed behavior, and malformed `coverage_assessment` shape rejection. The newest serialized slice found a separate type-hygiene defect in the final B22 customer projection:

- **RED `b58478e456bc67bef293d8d84223e896201891bc`, FixList CI `35540737270`:** `scanner-api/tests/test_stage3_preview_projection_privacy.py` injected a private URL/sentinel inside dict/list values for allowlisted `rule_id`, `title`, and `evidence_summary`. The scanner suite failed exactly the new behavior: `1 failed, 2049 passed, 18 skipped`; root regressions were `115 passed`. The separate lint/typecheck/generated-release-contract/frontend-contract/build job passed. The failure diff proved structured values crossed the preview projection unchanged.
- **GREEN `c5cab5b7ef437c1fa847b8cc28558fb6ca4c4af5`, exact-head FixList CI `35541044424`:** `_preview_projection()` now routes those customer text fields through `_preview_text()`; only real strings survive and structured/non-string producer values fail closed to `None`. Both CI jobs passed. Root regressions: `115 passed`; scanner-api: `2050 passed, 18 skipped`; both new privacy/type regressions passed; Stage-1 corpus remained `provenance=synthetic`, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd` matched; production scanner image `sha256:deef044ec3e1a2c025d3e741bbed5d78bda57d5ceb8bd9d7199bd32efa65e37a`; lint, typecheck, generated release-contract verification, frontend contract tests and production build all passed.

Detailed newest checkpoint: `docs/superpowers/plans/2026-09-21-stage3-b22-preview-projection-type-fail-closed.md`.

B22 is **not complete**. A genuinely fresh independent review of the corrected shared B22/B24 boundary is still required. The current CodeRabbit summary says automatic review is skipped for this repository; a skipped review is not approval. After Stage-1 release acceptance, the real V7 exact-owner/exact-scan persistence/read/reload/history/preview/card/export seam must also be proven on reconciled accepted-main source.

### B23 — partial

Only explicit versioned verified B20 root-cause evidence may contribute a documented score cap. Conflicts, unverified/cross-scan evidence fail closed, and existing stricter access/sample/incomplete ceilings remain authoritative. Executable GREEN `23d28ddee804e9c20db4136f06aab879685d1942` / CI `35514416069`; stable checkpoint `4ee24691f46721ffe8112bb435f278e5dd810721` / CI `35514613656`; focused review `5750230877` found no unresolved material defect. Durable customer-visible adjusted-score persistence/card/export consumption remains open.

### B24 — partial

Signed handoff-v2 source requires trusted exact scan identity and accepts root-cause identity only from exact-scan verified B20 groups. It carries family IDs, B19 factors, B21 counts, evidenced indexable counts, evidence refs, verification/dependency/vendor metadata and scanner UA; ambiguous mapping fails closed; historical v1 reader compatibility remains preserved. `suppressed_findings` is included only when `operator_authorized is True` literally; truthy non-booleans fail closed. Durable V7 persistence/read/customer/operator/export proof and the same fresh independent review remain open.

## Stage 3 current gate

Stage 3 is **not complete**. Latest executable GREEN is `c5cab5b7ef437c1fa847b8cc28558fb6ca4c4af5`, exact-head FixList CI `35541044424`. The current documentation/checkpoint commits must themselves be certified by exact-head FixList CI before this run ends.

Open gates:

1. one genuinely fresh independent review of the latest corrected B22/B24 shared authority/privacy boundary; a skipped/requested/failed automated review is not approval;
2. separate Stage-1 operator records exact-source publication and fresh non-owner acceptance;
3. reconcile this branch onto then-current accepted `main` without reverting V7/#308 and run exact integrated-head CI;
4. prove real V7 B19/B21/B22/B23/B24 producer → signed authority → persisted rows → exact-owner/exact-scan read/reload/history → customer card/export/preview seams, including suppressed/operator privacy and historical-v1 compatibility.

Runtime note for the latest executable GREEN: Ubuntu 24.04.5, Python 3.12.14; `setup-node` requested major Node 20 but resolved `20.20.2`, so this is not exact Node 20.19.5 evidence. GitHub emitted the Node-24 action-runtime migration warning.

## Stage 4 — held

Canonical isolated lane remains `agent/stage4-b25-b28-compat-release-20260919` at `d2ce905ff67410586f86e38bafd93ce4e998e4d1`; prior lane CI `35464436789` passed. It must not be duplicated or shared-integrated before Stage 3 applicable acceptance.

- **B25 incomplete:** named synthetic corpus exists, but the genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`. Synthetic mini-fixtures and historical summaries do not satisfy it.
- **B26 partial:** isolated own-site serving-defect reproduction exists; shared integration/acceptance remains open.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared integration/acceptance remains open.
- **B28 incomplete:** no full-blueprint exact-source deployment/live acceptance has been performed. Required live site/six-V7/worker identity reconciliation, rollback proof, and real customer submit → persistence → reload/history → rescan acceptance remain open.

## Next serialized action

1. Certify the final persisted documentation/checkpoint head with exact-head FixList CI and record its result in PR #303 without mutating that certified source afterward.
2. Refresh PR #303 review state. Require a genuinely fresh independent review of the corrected B22/B24 boundary; do not count CodeRabbit's automatic-review skip as approval.
3. Keep V7 durable/customer mutation and shared Stage-4 integration held while Stage-1 publication/non-owner acceptance remains open.
4. When that separate gate closes, reconcile onto accepted `main`, preserve V7/#308, run fresh exact integrated-head CI, and complete real B19–B24 persistence/customer seams before integrating the existing Stage-4 lane.
5. Only then execute genuine B25 baseline/candidate and B28 live acceptance gates.
