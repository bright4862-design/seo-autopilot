# Full blueprint progress

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec's exact requirement IDs and semantics control over older handoff paraphrases. Detailed historical RED/GREEN evidence remains in the executable plans under `docs/superpowers/plans/`; this file is the concise current state ledger.

## Release sequencing / freeze

- `main` refreshed on 2026-09-20 and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing the V7 runtime/public-build changes and durable ownership-before-admission fix #308.
- Current-main `docs/stage-one-evidence-acceptance.md` still records Stage-1 exact-source production publication and fresh non-owner production acceptance as pending. No accepted Stage-1 production report is recorded.
- Worker candidate `fixlist-standard150-worker-00091-bdr` and cutover-pause run `35462502364` remain historical checkpoints only; this branch does not promote traffic or mutate admission.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do not merge later-stage work to `main`, deploy/publish Base44, promote workers, mutate admission/queues/scheduler, submit a competing production scan, change schema/RLS/secrets, or enable Premium/Grok while the Stage-1 release gate remains open.
- After the single Stage-1 release operator records exact-source publication and fresh non-owner acceptance, reconcile this branch onto the then-current accepted `main` without reverting V7 routes or #308 and require fresh integrated-head FixList CI before durable customer-path work.

The labelled Stage-1 corpus remains explicitly synthetic: 14 cases / 55 assertions; frozen scanner revision `01ebe8e90df1e6bd`. Synthetic or historical evidence cannot satisfy B25's genuine provenance-labelled 30-site gate.

## Stage 2 — B06–B18 complete for source/review/CI

Stable corrected Stage-2 checkpoint: `10f51529bf5bf64b7b24ab8424f3ae821de46b39`; exact-head FixList CI `35500580582` passed. Fresh CodeRabbit follow-up `5748778814` returned no actionable finding. This closes Stage 2 for implementation, independent review and exact-head CI only; it is not a production-release claim.

- **B06 complete:** one finite shared follow-up scheduler; probe-only requests cannot inflate Standard-150 assessed pages or denominators.
- **B07 complete:** active soft-404 producer/orchestration reuses that scheduler; robots/challenge/429/budget/deadline/incomplete remains unknown.
- **B08 complete:** redirect meaning distinguishes normalization, usable, wrong/catch-all, unusable and unverified destinations with customer-safe wording.
- **B09 complete:** robots-declared sitemap integrity and variant probes reuse the shared finite scheduler.
- **B10 complete:** deterministic accepted-main-content analysis remains internal; fingerprints/shingles/raw copy are excluded from HTTP/authority/customer boundaries. A direct authenticated `/scan` regression at `d9061f23edd0a0541b017f42297bf60a9c401560` proved the serialized response does not leak B10/B11/B13/B15 private sentinels; CI `35524582769` passed.
- **B11 complete:** retained-set depth/inlink/navigation evidence uses exact retained identity and truthful sample scope; sitemap membership is not an inlink.
- **B12 complete:** bounded raw/rendered hub-link evidence uses the existing browser-followup ceiling with completed/failed/unassessed states.
- **B13 complete:** contextual local-entity/status completeness retains raw identity/contact evidence internally and exposes only positive-allowlisted aggregates.
- **B14 complete:** cross-page entity identity requires the same explicit absolute HTTP(S) JSON-LD `@id` on distinct pages; matching NAP/family alone is insufficient.
- **B15 complete:** freshness requires current-content intent plus contradictory temporal evidence; old dates alone do not fail.
- **B16 complete:** bounded URL-variant probes preserve exact identity and do not expand sibling-host scope or invent duplicate claims.
- **B17 complete:** raw transfer bytes remain separate from decoded/inline bytes; CrUX is disconnected by default and controlled evidence requires owner authorization, exact scan identity and valid observation time.
- **B18 complete:** GSC is disconnected by default; controlled evidence requires owner authorization, exact scan identity, exact retained-URL membership, conflict rejection, Standard-150 ceiling and valid observation time.

## Stage 3 — B19–B24 in progress

Reviewed isolated lanes were integrated serially, never merged directly to `main`:

- B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> shared integration `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> shared integration `3aebc7375e854ce063ac0bcec0a46210473e061c7`.
- Combined lane CI `35501672504` passed.

### B19 — partial; signed authority proven, durable customer consumption open

RED `ac6ce27b3c492649537d80788f7b02b86ec39e5e` / CI `35501924104`; GREEN `7ba2df83d848fd643bb510374b7da5a18ac749f1` / CI `35501983203`.

Canonical Review carries the exact versioned model `impact × reach × page value × confidence`, with truthful unknown denominators and explanations. Repair leverage is not a fifth/substitute factor. Durable FixItem/card/export consumption remains release-gated.

### B20 — partial; signed authority independently review-clean, durable customer consumption open

A P1 scan-isolation defect was reproduced at `6f1e2cc3ae519bbb494cab599579758f9efe427a` / CI `35503985665`, fixed at `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c`, with stale lane expectation corrected at `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481`; exact CI `35504200573` passed. Fresh follow-up `5749166024` reported no unresolved material issue.

Verified grouping requires trusted non-empty enclosing `scan_id == scan_run_id`; repair-local identity can only confirm that trust. Explicit versioned same-root-cause evidence is required; family similarity alone is insufficient.

### B21 — partial; signed authority independently review-clean, durable customer consumption open

Semantic RED `513a4438d5622d393bf3031cb2db17f29caa7ee5` / CI `35506946578`; known-zero/unknown ordering regression `467fc4aaf184c2cf8ad99e41dc8baa8fd13ac0d2`; fix `2b952e14ac72f03c42be794540574bc06a2c55b7`; signed-authority regression `881430f0ccd1900535fe2d4483e7d217b382954e`; exact-code CI `35512886836`; stable head `7236c36cd65fe441a9a90c6a52db9a6c2342125a` / CI `35513093636`; CodeRabbit follow-up `5750062094` no unresolved material issue.

Signed Review carries unique affected-page, observation, known-population and displayed-sample counts, with exact unions before sample truncation. Every eligible B19 candidate is ranked before presentation truncation. Known numeric scores including `0.0` sort ahead of explicit unknown composites; impact cannot substitute for unknown B19 priority.

### B22 — partial; signed preview source and authority/privacy boundaries GREEN, fresh independent review still open

Core signed-preview integration is GREEN and preserves exact trusted producer identity, verified-only evidence, impact-4/5 preference with two-finding cap, exactly one best verified fallback when no high-impact finding exists, and fixed controller-owned sufficient-coverage wording only when normalized coverage is explicitly sufficient. Arbitrary producer coverage text is excluded from the nested preview source and enclosing completion-HMAC Review.

Material privacy corrections already proven:

- fallback/privacy RED `ac2e1f0e3f1326073a6a37593071c00244338b11` / CI `35519832761`;
- corrected executable `e7719996e5454f19d373dc04557792992590d834` / CI `35520663236`;
- enclosing completion-Review leak RED `db6432fcf7258e64736d7a3eabeadd28e4cb907f` / CI `35521744377`;
- completion positive-allowlist GREEN `4d1575d92c6a3092661bcd290b7d8ef4ae883066` / CI `35522106799`.

Latest authority hardening on 2026-09-20:

- RED regression commit `28f58efbd773637bfada09da5b0a99b7fcc03fbc`, FixList CI `35528067336`: scanner-api failed exactly `4 failed, 2042 passed, 18 skipped` while the independent lint/typecheck/contracts/frontend job passed. The failures proved an unverified authority could still receive the fixed sufficient-coverage qualification and B24 accepted truthy non-boolean operator flags.
- GREEN implementation `4a9e0d4dec048291be7956bb225ab1635af30bbc`, FixList CI `35528215150`: both jobs passed; root `115 passed`; scanner-api `2046 passed, 18 skipped`; Stage-1 synthetic corpus 14/55 with `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd`; scanner image `sha256:124ee33c14e185e89adbb49906941192d7a2f55ffe8356e8ad7d43c121a7d932`; lint/typecheck/generated contracts/frontend contracts/build passed.
- `select_private_preview()` now returns no coverage qualification at all unless `authority_verified is True` before qualification evaluation.

Detailed latest checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b22-b24-authority-fail-closed.md`.

B22 remains partial until a fresh independent review passes on the corrected shared head and, after Stage-1 accepted-main reconciliation, the real V7 exact-owner/exact-scan entitlement plus persistence/read/reload/history/preview/card/export path is proven.

### B23 — partial; signed authority independently review-clean, durable score consumption open

RED `c713baca3f65da28bd52616960fdcb30e8f52d49` / CI `35514082243`; executable GREEN `23d28ddee804e9c20db4136f06aab879685d1942` / CI `35514416069`; stable head `4ee24691f46721ffe8112bb435f278e5dd810721` / CI `35514613656`; fresh focused review `5750230877` found no unresolved material defect.

Only versioned, explicit, verified B20 root-cause evidence can contribute a documented score cap. Conflicts/cross-scan/unverified evidence fail closed. Existing stricter access/sample/incomplete ceilings remain authoritative. Customer-visible adjusted-score persistence/card/export remains open.

### B24 — partial; signed handoff-v2 source GREEN, operator suppression hardened, fresh independent review + durable route open

Source RED `37b73a98e6b54db9c86f0de9eb921ff178a0201a` / CI `35515644839`; implementation `5eb4b6751019e98f87afc3b329880fbd33e0fdd6`; corrected GREEN `790ebdc7ddec86a5a4bbfe4dfa0cb3ee23e0a353` / CI `35516240329`.

The signed source requires exact trusted producer scan identity; accepts root-cause identity only from exact-scan verified B20 groups; carries family IDs, B19 factors, B21 counts, explicitly evidenced indexable count, evidence refs, verification/dependency/vendor metadata and scanner UA; fails closed on ambiguous root-cause mapping; historical v1 reader compatibility remains preserved.

Latest operator-only hardening shares the RED/GREEN evidence above: at `28f58ef...` truthy non-boolean values leaked `suppressed_findings`; `4a9e0d4...` changed the projection gate to literal `operator_authorized is True`, and CI `35528215150` passed all four adversarial authority tests plus the full suite.

B24 remains partial until a fresh independent review passes and the accepted-main durable V7 persistence/read/customer/operator/export path is proven. No suppressed/operator-only finding may appear in customer output.

## Stage 3 current gate

Stage 3 is **not complete**. Latest executable GREEN is `4a9e0d4dec048291be7956bb225ab1635af30bbc` with CI `35528215150`. The latest checkpoint is persisted in `docs/superpowers/plans/2026-09-20-stage3-b22-b24-authority-fail-closed.md`; the documentation head will be certified separately by exact-head FixList CI.

Open gates before Stage 3 can close:

1. fresh independent review of the corrected current B22/B24 shared authority/privacy boundary; skipped/failed automated reviews are not approval;
2. Stage-1 release operator must first record exact-source production publication and fresh non-owner acceptance;
3. reconcile onto the then-current accepted `main` without reverting V7/#308 and run fresh integrated-head CI;
4. implement/prove the real V7 B19/B21/B22/B23/B24 producer → signed authority → persisted rows → exact-owner/exact-scan read/reload/history → customer card/export/preview seams, including suppressed/operator privacy and historical v1 compatibility.

## Stage 4 — held

Existing isolated lane remains `agent/stage4-b25-b28-compat-release-20260919` at `d2ce905ff67410586f86e38bafd93ce4e998e4d1`; prior lane CI `35464436789` passed. It must not be reimplemented in duplicate and is not shared-accepted yet.

- **B25 incomplete:** named synthetic corpus exists, but the genuine provenance-labelled 30-site baseline/candidate gate remains `not_assessed`. Synthetic mini-fixtures and historical summaries never satisfy the real gate.
- **B26 partial:** isolated own-site serving-defect reproduction exists; shared integration/acceptance remains open.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared integration/acceptance remains open.
- **B28 incomplete:** no full-blueprint exact-source deployment/live acceptance has been performed. Required live-site/six-V7/worker identities, rollback proof and real customer submit → persistence → reload/history → rescan acceptance remain open.

## Next serialized action

1. Certify the persisted documentation head with exact-head FixList CI.
2. Obtain one fresh independent review of the latest B22/B24 authority/privacy corrections; do not count a skipped review as approval.
3. Keep all V7 durable/customer mutation and Stage-4 integration held until the Stage-1 release operator records exact-source publication and fresh non-owner acceptance.
4. After that release gate closes, reconcile onto accepted `main`, run fresh integrated-head CI, then complete the real V7 B19–B24 persistence/customer seams before integrating the existing Stage-4 lane and executing the real B25/B28 acceptance gates.

No production deployment, `main` merge, worker/admission mutation, production scan, provider connection, schema/RLS change, secret rotation, Premium enablement or Grok enablement occurred in the latest slice.
