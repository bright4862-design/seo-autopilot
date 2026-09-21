# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec's exact B01–B28 semantics control over older handoff paraphrases. Detailed RED/GREEN history is retained in executable plans under `docs/superpowers/plans/`; this file is the concise current state ledger.

## Release sequencing / freeze

- `main` refreshed during the 2026-09-21 serialized slice and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing the six V7 runtime/public-build changes and durable ownership-before-admission fix #308.
- Current-main `docs/stage-one-evidence-acceptance.md` still records Stage-1 exact-source production publication and fresh non-owner acceptance as pending.
- Worker candidate `fixlist-standard150-worker-00091-bdr` and cutover-pause run `35462502364` are historical checkpoints only. They are not permission to promote, mutate admission/queues/scheduler, launch a production scan, or rebuild.
- Serialized later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Keep all later-stage work off `main` until the separate Stage-1 release operator records exact-source publication and fresh non-owner acceptance. Then reconcile onto the accepted `main` without reverting V7/#308 and require exact integrated-head FixList CI before durable customer-path work.
- No Premium/Grok enablement, schema/RLS broadening, secret rotation, fabricated provider connection, production deployment, worker promotion, or competing live scan is authorized from this branch.

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

### B19 — partial; source numeric evidence fail-closed GREEN

Canonical signed Review carries the exact versioned factor model **impact × reach × page value × confidence**, truthful unknown denominators, and versioned explanations. Repair leverage is not a substitute fourth factor. Durable V7 FixItem/card/export consumption remains release-gated.

Fresh inspection found two remaining source-evidence coercion paths in `stage3_priority_factors.py`: fallback confidence used `float(confidence)`, so a numeric string such as `"95"` could manufacture `verified` trust; connected GSC normalized page value used `float(...)`, so string `"0.9"` or boolean `True` could become trusted provider evidence and boost page value.

- **RED `f94eeeac974be8afe317437c31d04adc5237ba76`, FixList CI `35553020191`:** three new adversarial regressions failed exactly as intended. Root regressions were `115 passed`; scanner-api was `3 failed, 2075 passed, 18 skipped`. `"95"` was incorrectly classified `verified`, `"0.9"` produced page value `0.9`, and `True` produced page value `1.0`. The separate lint/typecheck/generated-release-contract/frontend-contract/build job passed.
- **GREEN `058f46fce08c3aec66fac35a3af18a4607eb30bf`, exact-head FixList CI `35553077583`:** B19 now accepts only actual finite `int`/`float` values at these numeric source boundaries; booleans, strings, NaN and infinities fail closed. The source correction relative to RED changes only `scanner-api/app/stage3_priority_factors.py` (13 additions, 8 deletions). Root regressions: `115 passed`; scanner-api: `2078 passed, 18 skipped`; synthetic corpus: 14 cases / 55 assertions with `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd` matched; production scanner image `sha256:083616943a94b11c1c66c97db27b81c015801a6fa92494c013f1004f73adc32e`; lint, typecheck, generated release-contract verification, frontend contracts and production build passed.

Detailed checkpoint: `docs/superpowers/plans/2026-09-21-stage3-b19-numeric-source-fail-closed.md`.

The earlier 2026-09-21 numeric-evidence slice remains GREEN for B21/B22/B23 displayed evidence: malformed numeric strings, booleans, fractions where integers are required, NaN and infinities fail closed. RED `e64279094167c175141c309113ae8a58b90d7044`; GREEN `70ad5bda63b59b9e887a7b88cf26e306933a6750`; exact-head FixList CI `35543922420` passed both jobs.

### B20 — partial; explicit evidence identity/type boundary corrected GREEN

Verified shared root-cause grouping requires explicit versioned same-cause evidence and trusted enclosing `scan_id == scan_run_id`; family similarity and repair-local identity alone cannot establish trust. Scan-isolation correction is review-clean. Durable customer projection remains release-gated.

The latest B20 type hardening remains GREEN: RED `089e55a1bad819a26b30302e46b71307eea132c8`; GREEN `590dc20251952e76f265c76e40d4755299d0b6cc`; exact-head FixList CI `35549679233`. B20 accepts only actual strings for `root_cause_id`, `repair_surface_id`, and individual `evidence_refs`; mappings/lists/numbers/booleans fail closed into missing/invalid evidence. Valid string evidence, exact-scan isolation, grouping semantics and score-cap behavior are unchanged.

Detailed checkpoint: `docs/superpowers/plans/2026-09-21-stage3-b20-root-cause-evidence-type-fail-closed.md`.

### B21 — partial

Signed Review carries exact unique affected-page, observation, known-population and displayed-sample counts, with exact unions before sampling and all eligible B19 candidates ranked before presentation truncation. Known numeric zero stays known; unknown composite priority cannot borrow impact. Durable persistence/card/export proof remains open.

### B22 — partial

The signed evidence-led preview source requires verified evidence and trusted exact identity, prefers verified impact-4/5 findings with a two-item cap, otherwise exactly one best verified fallback, and emits controller-owned sufficient-coverage wording only when coverage is explicitly sufficient. Completion-HMAC coverage privacy, authority fail-closed behavior, malformed coverage shape, structured preview-text rejection and malformed numeric evidence are GREEN. A genuinely fresh independent review and durable exact-owner/exact-scan V7 preview proof remain open.

### B23 — partial

Only explicit versioned verified B20 root-cause evidence may contribute a documented score cap. Conflicts, unverified/cross-scan evidence fail closed, and existing stricter access/sample/incomplete ceilings remain authoritative. Malformed numeric caps now fail closed without coercion. Durable customer-visible adjusted-score persistence/card/export consumption remains open.

### B24 — partial; customer-safe handoff projection correction GREEN

Signed handoff-v2 source requires trusted exact scan identity and accepts root-cause identity only from exact-scan verified B20 groups. It carries family IDs, B19 factors, B21 counts, evidenced indexable counts, evidence refs, verification/dependency/vendor metadata and scanner UA; historical v1 reader compatibility remains preserved. `suppressed_findings` is included only when `operator_authorized is True` literally.

The latest B24 projection hardening remains GREEN: RED `083e3a0c1a649be8162c40ee0d85f6ed0c66773c`, GREEN `ef0204b9a7851a53c040b334f99e1e541097d4b3`, exact-head FixList CI `35546802039`. B24 positive-allowlists scan identity and the exact public B19 factor schema, type-projects customer text fields, uses strict finite numeric/integer evidence rules, filters explanation items to strings, and drops unknown operator/debug keys.

B20's typed-provenance correction and B19's source-numeric correction are upstream of this handoff, preventing malformed root-cause identifiers or malformed B19 confidence/GSC numeric source evidence from entering trusted downstream state.

B24 is **not complete**. Durable V7 persistence/read/customer/operator/export proof and a genuinely fresh independent review of the corrected shared B22/B24 privacy boundary remain open.

## Stage 3 current gate

Stage 3 is **not complete**. Latest executable GREEN is `058f46fce08c3aec66fac35a3af18a4607eb30bf`, exact-head FixList CI `35553077583`. The final persisted documentation/checkpoint branch head from this run must itself receive exact-head FixList CI before the run is closed.

Open gates:

1. one genuinely fresh independent review of the latest corrected B22/B24 shared authority/privacy boundary, including upstream B19/B20 evidence feeding handoff-v2; CodeRabbit automatic-review skip is not approval;
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
2. Refresh PR #303 review state. Require a genuinely fresh independent review of the corrected B22/B24 boundary; do not count an automatic-review skip as approval and do not repeatedly dispatch broken/skipped launchers.
3. Keep V7 durable/customer mutation and shared Stage-4 integration held while Stage-1 publication/non-owner acceptance remains open.
4. When that separate gate closes, reconcile onto accepted `main`, preserve V7/#308, run fresh exact integrated-head CI, and complete real B19–B24 persistence/customer seams before integrating the existing Stage-4 lane.
5. Only then execute genuine B25 baseline/candidate and B28 live acceptance gates.
