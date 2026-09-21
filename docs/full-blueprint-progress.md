# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec's exact B01–B28 semantics control over older handoff paraphrases. Detailed RED/GREEN history is retained in executable plans under `docs/superpowers/plans/`; this file is the concise current state ledger.

## Release sequencing / freeze

- Direct `main` was refreshed during the 2026-09-21 serialized slice and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing the V7 runtime/public-build changes and durable ownership-before-admission fix #308.
- Current-main `docs/stage-one-evidence-acceptance.md` still records Stage-1 exact-source production publication and fresh non-owner acceptance as pending.
- Worker candidate `fixlist-standard150-worker-00091-bdr` and cutover-pause run `35462502364` are historical checkpoints only, not permission to promote, mutate admission/queues/scheduler, launch a production scan, or rebuild.
- Serialized later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Keep later-stage work off `main` until the separate Stage-1 release operator records exact-source publication and fresh non-owner acceptance. Then reconcile onto the accepted `main` without reverting V7/#308 and require exact integrated-head FixList CI before durable customer-path activation.
- No Premium/Grok enablement, schema/RLS broadening, secret rotation, fabricated provider connection, production deployment, worker promotion, or competing live scan is authorized from this branch.

The labelled Stage-1 corpus remains explicitly synthetic: 14 cases / 55 assertions at frozen scanner revision `01ebe8e90df1e6bd`. Synthetic fixtures or historical summaries never satisfy B25's genuine provenance-labelled 30-site gate.

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

Canonical signed Review carries exact versioned **impact × reach × page value × confidence**, truthful unknown denominators and explanations. Repair leverage is not a substitute fourth factor. Fallback confidence and connected-GSC page-value source evidence accept only actual finite numeric values; strings, booleans, NaN and infinities fail closed. Latest source-numeric GREEN: `058f46fce08c3aec66fac35a3af18a4607eb30bf`, CI `35553077583`. Durable V7 FixItem/card/export consumption remains release-gated.

### B20 — partial; exact-scan identity coercion corrected GREEN

Verified shared-root-cause grouping requires explicit versioned same-cause evidence, actual string root-cause/surface/reference identifiers, and trusted enclosing exact producer identity. Family similarity, repair-local identity, structured/debug objects, or stringified structured scan identities cannot establish trust.

Fresh inspection found `_trusted_stage3_scan_id()` passed `scan_id` and `scan_run_id` through `_clean_text()`. Matching dictionaries/lists could therefore stringify to the same non-empty value and be treated as an exact producer scan identity. That malformed trusted identity also fed B22/B24 signed source construction.

- **RED `f0d6f217ab338874fc13dd576f40195af06a0fac`, FixList CI `35559679611`:** added `scanner-api/tests/test_stage3_exact_scan_identity_fail_closed.py`. Exact result: root scanner tests `115 passed`; scanner-api `2 failed, 2081 passed, 18 skipped`, with exactly the two new structured-identity regressions failing. The independent lint/typecheck/generated-contract/frontend/build job passed.
- **GREEN `08c94082bd731c371bc06946df5b821521aa3861`, exact-head FixList CI `35559929454`:** `_trusted_stage3_scan_id()` now requires two actual non-empty strings and exact post-strip equality. Non-string/coercible values fail closed. RED→GREEN implementation diff is one file, 9 additions / 4 deletions. Both CI jobs passed: root tests `115 passed`; scanner-api `2083 passed, 18 skipped`; labelled corpus `14/55` with `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd`; scanner image `sha256:2f2a1f8d5a35a1ccdba861061c5ad58e42c98152b32ce0e2d44990c5ff30d5b8`; lint/typecheck/contracts/frontend/build all passed.

Detailed checkpoint: `docs/superpowers/plans/2026-09-21-stage3-exact-scan-identity-fail-closed.md`. Durable customer projection remains open.

### B21 — partial

Signed Review carries exact unique affected-page, observation, known-population and displayed-sample counts. Exact unions are computed before sampling and all eligible B19 candidates are ranked before presentation truncation. Malformed numeric evidence fails closed. Durable persistence/card/export proof remains open.

### B22 — partial

The signed evidence-led preview source requires verified evidence and literal trusted exact producer identity, prefers verified impact-4/5 findings with a two-item cap, otherwise exactly one best verified fallback, and emits controller-owned sufficient-coverage wording only when coverage is explicitly sufficient. Completion-HMAC coverage privacy, authority fail-closed behavior, malformed coverage shape, structured preview-text rejection, malformed numeric evidence, and structured scan-identity rejection are GREEN. A genuinely fresh independent review and durable exact-owner/exact-scan V7 preview proof remain open.

### B23 — partial

Only explicit verified B20 root-cause evidence may contribute a documented score cap. Conflicts, unverified/cross-scan evidence and malformed numeric caps fail closed, while existing stricter access/sample/incomplete ceilings remain authoritative. Coverage state is bounded to the documented vocabulary; malformed/structured values project to `unknown`. Latest coverage-state GREEN: `c1f7ebc04392e413a0181a791459b42fadfcf6a5`, CI `35556598093`. Durable customer-visible adjusted-score persistence/card/export consumption remains open.

### B24 — partial

Signed handoff-v2 source requires literal trusted exact scan identity and accepts root-cause identity only from exact-scan verified B20 groups. It carries family IDs, B19 factors, B21 counts, evidenced indexable counts, evidence refs, verification/dependency/vendor metadata and scanner UA; historical v1 reader compatibility remains preserved. `suppressed_findings` is included only when `operator_authorized is True` literally. Customer scan/fix/B19-factor projection is positive-allowlisted and type-checked. The exact-scan coercion correction at `08c94082bd731c371bc06946df5b821521aa3861` prevents structured producer identity from entering the signed B24 source. Durable V7 persistence/read/customer/operator/export proof and fresh independent review remain open.

## Stage 3 current gate

Stage 3 is **not complete**. Latest executable GREEN is `08c94082bd731c371bc06946df5b821521aa3861`, exact-head FixList CI `35559929454`, both jobs passed. This documentation update occurs after that source certification, so the final persisted documentation/checkpoint branch head must itself receive exact-head FixList CI before it is called the stable checkpoint.

Open gates:

1. one genuinely fresh independent review of the latest corrected B22/B24 shared authority/privacy boundary, including upstream B19/B20/B23 evidence feeding signed delivery; a skipped/absent automated review is not approval;
2. separate Stage-1 operator records exact-source publication and fresh non-owner acceptance;
3. reconcile this branch onto then-current accepted `main` without reverting V7/#308 and run exact integrated-head CI;
4. prove real V7 B19/B21/B22/B23/B24 producer -> signed authority -> persisted rows -> exact-owner/exact-scan read/reload/history -> customer card/export/preview seams, including suppressed/operator privacy and historical-v1 compatibility.

Runtime note: GitHub's Node-20 setup resolved Node `20.20.2` for `35559929454`, not exact Node 20.19.5; exact 20.19.5 evidence is therefore not claimed. GitHub Actions also emitted its Node-20 action-runtime deprecation warning.

## Stage 4 — held

Canonical isolated lane remains `agent/stage4-b25-b28-compat-release-20260919` at refreshed checkpoint `d2ce905ff67410586f86e38bafd93ce4e998e4d1`; prior lane CI `35464436789` passed. It must not be duplicated or shared-integrated before Stage 3 applicable acceptance.

- **B25 incomplete:** named synthetic corpus exists, but the genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`. Synthetic mini-fixtures and historical summaries do not satisfy it.
- **B26 partial:** isolated own-site serving-defect reproduction exists; shared integration/acceptance remains open.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared integration/acceptance remains open.
- **B28 incomplete:** no full-blueprint exact-source deployment/live acceptance has been performed. Required live site/six-V7/worker identity reconciliation, rollback proof, and real customer submit -> persistence -> reload/history -> rescan acceptance remain open.

## Next serialized action

1. Certify the final persisted documentation/checkpoint head for this exact-scan-identity slice with exact-head FixList CI and record it in PR #303 without mutating that certified source afterward.
2. Refresh PR #303 review state. Require a genuinely fresh independent review of the corrected B22/B24 boundary; do not count an automatic-review skip as approval and do not repeatedly dispatch broken/skipped launchers.
3. Keep V7 durable/customer mutation and shared Stage-4 integration held while Stage-1 publication/non-owner acceptance remains open.
4. When that separate gate closes, reconcile onto accepted `main`, preserve V7/#308, run fresh exact integrated-head CI, and complete real B19–B24 persistence/customer seams before integrating the existing Stage-4 lane.
5. Only then execute the genuine B25 baseline/candidate and B28 live acceptance gates.
