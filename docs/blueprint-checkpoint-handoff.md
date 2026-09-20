# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec controls over older paraphrases.

## Release boundary

- `main` remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad` with V7 runtime/public-build changes and #308.
- Current-main `docs/stage-one-evidence-acceptance.md` still records exact-source production publication and fresh non-owner production acceptance as pending.
- Stage-1 publication/promotion/live acceptance remains owned by the existing single release operator.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- Do not merge this branch to `main`, deploy/publish, promote worker traffic, mutate admission, submit a competing production scan, change schema/secrets or copy/recreate V7 persistence routes while Stage-1 acceptance is pending.
- After Stage-1 acceptance is recorded, reconcile onto the then-current accepted `main`, preserve V7/#308 and require fresh integrated-head CI before durable customer-path work.

## Stage 2

B06–B18 are complete for source integration, independent review and exact-head CI at stable corrected head `10f51529bf5bf64b7b24ab8424f3ae821de46b39`; FixList CI `35500580582` passed and CodeRabbit follow-up `5748778814` returned no actionable finding. This is not a production-release claim.

The proven Stage-2 invariants remain authoritative: one finite shared follow-up budget; Standard-150 assessed cap; truthful denominators; robots/DNS/SSRF/redirect/body/deadline protections; exact URL identity; blocked/challenged/429/incomplete as unknown; optional providers disconnected by default; historical compatibility; fail-closed page/aggregate projection.

## Stage 3 — current checkpoint

Reviewed sources integrated serially:

- B19/B20 lane `e74d87acd0cec2955402b96f635f13bc275f3a91` -> `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 lane `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7` -> `3aebc7375e854ce063ac8853c3e49e9f10a58cb7`.
- Combined lane CI `35501672504` passed.

### B19/B20 signed authority

B19/B20 canonical Review integration: RED `ac6ce27b3c492649537d80788f7b02b86ec39e5e` / CI `35501924104`; GREEN `7ba2df83d848fd643bb510374b7da5a18ac749f1` / CI `35501983203`.

B19 signs only the versioned four factors `impact x reach x page value x confidence` with truthful unknowns. B20 requires explicit evidenced same-root-cause evidence and trusted enclosing scan identity.

B20 P1 scan-isolation correction: RED `6f1e2cc3ae519bbb494cab599579758f9efe427a` / CI `35503985665`; fix `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c`; strengthened lane expectation `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481`; exact CI `35504200573`. Fresh CodeRabbit follow-up `5749166024` on stable head `fb9a22f1284e1381db04186733ebeb32bb4a7e93` reported no unresolved material issue. B20 review is closed at the signed Review boundary; durable customer projection remains open.

### B21 signed authority — review gate closed

B21 real Review integration: semantic RED `513a4438d5622d393bf3031cb2db17f29caa7ee5` / CI `35506946578`; implementation `86cea88d8a90c62a686015fb9fc464fc0dddfd0d`; legacy-rank correction `d74240b751d9ac1fefe070036397d016a6d074aa`; B19-known fixture correction `e9aa3789b9b143a7b3b8dbdd0e52ad2edf953a0f` / CI `35507339178`.

Fresh CodeRabbit then found a P1 where explicit unknown B19 composite score could be sorted as zero plus impact and displace a genuinely known score `0.0` at the 36-item cap.

- Regression `467fc4aaf184c2cf8ad99e41dc8baa8fd13ac0d2` covers unknown-vs-known-zero.
- Fix `2b952e14ac72f03c42be794540574bc06a2c55b7` separates every numeric known B19 score, including exact zero, from explicit unknown composites. Known scores sort before unknowns; impact cannot substitute across that boundary.
- Signed-authority regression `881430f0ccd1900535fe2d4483e7d217b382954e` uses 37 valid repairs (35 positive known + known zero + high-impact unknown) and proves the known-zero repair remains in the 36 displayed IDs, the unknown repair is omitted and the completion HMAC authenticates that exact Review.
- Exact-code CI `35512886836` passed: root 115; scanner-api 2030 passed / 18 skipped; signed B21 integration 2 passed; synthetic corpus 14 cases / 55 assertions / `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd`; image `sha256:6d49c53baa876bf38bdf4229399e13ab2164ccbbc40a99e5723589b786aa5022`; lint/typecheck/contracts/frontend build green.
- Stable checkpoint head `7236c36cd65fe441a9a90c6a52db9a6c2342125a` passed exact-head FixList CI `35513093636` on both jobs.
- Focused CodeRabbit follow-up `5750062094` on exact stable head `7236c36...` reported **no unresolved material issue**. It explicitly verified exact B19 factors/no repair-leverage factor, unknown preservation, known-zero-before-unknown sorting, rank-before-truncate, signed HMAC proof, B20 trusted producer identity, bounded delivery output, external scan projection, no new request activity and unchanged Standard-150 assessed boundary. CodeRabbit did not run tests; the CI above provides execution proof.

The **B21 independent-review gate is closed for the signed authority boundary**. B21 remains incomplete overall because durable FixItem -> customer card/export persistence/consumption is still unproven.

Node note: CI requested Node 20 but setup-node resolved `20.20.2`; hosted JavaScript actions separately warn their runtime is forced to Node 24. Do not cite these runs as exact Node 20.19.5 evidence.

Detailed B21 checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b21-signed-delivery.md`.

### B19–B24 requirement state

- **B19 partial:** signed Review factors/explanations green; durable FixItem/card/export consumption open.
- **B20 partial:** signed Review P1-corrected and independently review-clean; durable customer projection open.
- **B21 partial:** signed rank/count/truncation authority seam P1-corrected, independently review-clean and CI green; durable persisted customer/card/export proof open.
- **B22 partial:** authenticated private-preview/whitelist helper exists; actual entitlement/customer seam and no-leak proof unwired.
- **B23 partial:** verified root-cause score-cap helper exists; actual health-score boundary must preserve access/sample/incomplete ceilings.
- **B24 partial:** handoff-v2 + historical-v1 reader exist; authenticated customer/operator route, persisted source fields and suppressed/operator-only exclusion unwired.

Stage 3 remains **in progress**.

## Stage 4

Reuse only existing isolated source `agent/stage4-b25-b28-compat-release-20260919` @ `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, after shared Stage-3 acceptance.

- **B25 incomplete:** real provenance-labelled 30-site baseline/candidate gate remains `not_assessed`; synthetic/historical evidence is not a pass.
- **B26 partial:** isolated own-site serving-defect work exists; shared acceptance not run.
- **B27 partial:** isolated GEO/historical HMAC/reader/tamper/privacy compatibility exists; shared acceptance not run.
- **B28 incomplete:** exact-source deployment/live acceptance, live identities, rollback proof and real customer submit -> persistence -> exact reload/history -> linked rescan remain outstanding.

## Exact next action

The B21 signed-boundary review gate is now closed. Durable B19/B21 persistence/card/export is release-gated until Stage-1 acceptance permits reconciliation onto V7 main.

Until that gate closes, the next eligible serialized source slice is B23 health-score boundary integration, provided it does not touch the frozen release path and proves the documented verified root-cause cap while preserving every existing access/sample/incomplete ceiling. Require RED -> GREEN behavior, signed-authority proof, exact-head FixList CI and focused independent review. Do not move production.