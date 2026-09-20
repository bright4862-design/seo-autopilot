# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current serialized handoff for the FixList full-scanner blueprint. Historical checkpoints remain in Git history and linked executable plans. The approved spec controls over older paraphrases.

## Release boundary

- Stage-1 publication/promotion/live non-owner acceptance remains owned by the existing exact-source release operator.
- `main` was refreshed and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`; later-stage work has no authority to move production.
- Current `main` `docs/stage-one-evidence-acceptance.md` still records exact-source production publication and fresh non-owner acceptance as pending, so the later-stage branch must not yet reconcile/copy V7 persistence routes.
- Do not publish, promote worker traffic, mutate admission, run a competing production scan, rebuild the release, change schema/secrets, or merge the later-stage branch to `main`.
- Later-stage integration remains on `agent/full-blueprint-stage2-coverage-b06-20260919`, PR #303.
- After Stage-1 live acceptance, reconcile onto the then-current accepted `main` without reverting V7 route/public-build changes or #308, then require fresh exact-head integrated CI.

## Stage 2 — complete for source/review/CI, not a production-release claim

Stable corrected Stage-2 head: `10f51529bf5bf64b7b24ab8424f3ae821de46b39`.

Exact-head FixList CI `35500580582` passed. Fresh CodeRabbit follow-up on the corrected fail-closed page-output boundary (PR #303 issue comment `5748778814`, 2026-09-20T08:48:38Z) returned `Comments: 0` and no actionable finding. This closes the final B06–B18 independent-review gate.

Stage 2 is therefore recorded complete for implementation, material-review correction and exact-head CI. It does **not** authorize Stage-1 publication, admission mutation, worker promotion or any production scan.

Key invariants proven through the Stage-2 integration remain unchanged: one finite follow-up budget, Standard-150 assessed cap, truthful denominators, robots/DNS/SSRF/redirect/body/deadline protections, exact URL identity, blocked/challenged/429/incomplete as unknown, optional providers disconnected by default, historical signature/read compatibility, and fail-closed external page/aggregate projections.

## Stage 3 — current executable integration checkpoint

### Reviewed source lanes

- B19/B20: `agent/stage3-b19-b20-decisions-20260919` @ `e74d87acd0cec2955402b96f635f13bc275f3a91`.
- B21–B24: `agent/stage3-b21-b24-delivery-20260919` @ `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`.

Exact reviewed blobs were integrated serially onto the single integration branch:

- B19/B20 integration commit `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 integration commit `3aebc7375e854ce063c0bcec0a46210473e061c7`.
- Exact-head FixList CI `35501672504` passed both jobs on the combined lane additions.

### B19/B20 real signed-review wiring and review closure

RED `ac6ce27b3c492649537d80788f7b02b86ec39e5e` / CI `35501924104` proved the canonical Review → signed completion seam was missing. GREEN `7ba2df83d848fd643bb510374b7da5a18ac749f1` / CI `35501983203` derives B19/B20 after final canonical merge/validation and before the durable completion envelope signs Review.

B19 authenticated behavior: exact versioned `impact × reach × page value × confidence`, truthful unknown reach, final factors recomputed over the canonical affected-page union, no repair-leverage substitute/fifth factor, and the same authenticated factor envelope mirrored as `priority_factors` for later B24 derivation.

B20 authenticated behavior: explicit verified root-cause evidence only, pre-fingerprint source rows preserve SEO/GEO/family provenance, affected URLs are unioned, suppression provenance is retained, and enclosing producer identity must have non-empty exact `scan_id == scan_run_id`.

Fresh CodeRabbit then found a material P1: repair-local identity could replace the trusted enclosing producer identity. RED `6f1e2cc3ae519bbb494cab599579758f9efe427a` / CI `35503985665` reproduced it. Fix `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c` makes producer identity authoritative and local identity only a consistency assertion. CI `35504067902` exposed a stale lane expectation; `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481` strengthened that test so absent producer identity cannot be resurrected locally. Exact-head CI `35504200573` passed.

Fresh CodeRabbit follow-up on exact stable head `fb9a22f1284e1381db04186733ebeb32bb4a7e93` (PR #303 issue comment `5749166024`, 2026-09-20T10:14:11Z) reported no unresolved material issue and explicitly rechecked trusted producer identity, foreign/matching local IDs, explicit verified same-root-cause evidence, B19 factors/unknown reach and signed Review. The B20 independent-review gate is therefore closed for this signed-review boundary.

B19/B20 remain **overall incomplete** only because their durable FixItem/card/export customer projection has not yet been proven.

Detailed plan/checkpoint: `docs/superpowers/plans/2026-09-20-stage3-signed-b19-b20-integration.md`.

### B21 real signed delivery wiring and P1 correction

B21 is connected to the canonical Review before the existing completion HMAC signs authority.

- `513a4438d5622d393bf3031cb2db17f29caa7ee5` / CI `35506946578`: valid RED proving `stage3_delivery` was absent at the integrated Review boundary.
- `86cea88d8a90c62a686015fb9fc464fc0dddfd0d`: first shared B21 implementation, adding per-repair truthful counts and bounded delivery metadata before signing.
- CI `35507077795` exposed legacy `priority_rank` masking authenticated B19 factor order.
- `d74240b751d9ac1fefe070036397d016a6d074aa`: removes that legacy field only from the temporary B21 view, leaving canonical historical metadata unchanged.
- `e9aa3789b9b143a7b3b8dbdd0e52ad2edf953a0f` corrected the test fixture to a family-scoped B19-known candidate instead of fabricating reach/score for cross-cutting `broken_page`; CI `35507339178` passed.

A fresh CodeRabbit review then identified a material P1: explicit unknown B19 composite score could be normalized to sortable zero and use impact as a tie-breaker. At the 36-item presentation cap, a high-impact unknown repair could displace a repair whose authenticated B19 composite was genuinely known as `0.0`.

- `467fc4aaf184c2cf8ad99e41dc8baa8fd13ac0d2`: regression for unknown-vs-known-zero ordering.
- `2b952e14ac72f03c42be794540574bc06a2c55b7`: fixes `stage3_delivery._candidate_priority()` so all numeric B19 scores, including zero, rank in a known segment before all explicit unknown composite scores. Impact no longer substitutes when comparing an unknown composite with a known one.
- Reviewer-required signed authority proof: `881430f0ccd1900535fe2d4483e7d217b382954e` extends the real B21 integration regression to 37 contract-valid repairs (35 positive known scores + one known `0.0` + one high-impact unknown). The known zero remains in the 36 displayed IDs, the unknown repair is omitted, `stage3_delivery` is exactly the completion Review's value, and the existing HMAC verifies that same Review.
- Exact executable FixList CI `35512886836` passed both jobs on `881430f0ccd1900535fe2d4483e7d217b382954e`: root 115 passed; scanner-api `2030 passed, 18 skipped`; signed B21 integration tests 2 passed; labelled synthetic corpus 14 cases / 55 assertions / `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd`; scanner image `sha256:6d49c53baa876bf38bdf4229399e13ab2164ccbbc40a99e5723589b786aa5022`; lint/typecheck/generated contracts/frontend contracts/build passed.
- CI requested Node 20 but `setup-node` resolved `20.20.2`; hosted JavaScript actions separately warned their action runtime is forced onto Node 24. Do not cite this as exact Node 20.19.5 evidence.

B21's corrected signed behavior is now proven at the real authority boundary. A fresh independent follow-up review of this corrected exact boundary is still required, and B21 remains overall incomplete until durable FixItem/card/export consumption is proven.

Detailed plan/checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b21-signed-delivery.md`.

### Requirement state

- **B19:** signed Review integration green; exact factors/explanations and truthful unknowns authenticated. Unknown composite cannot displace known zero in B21 signed presentation. Durable FixItem/card/export consumption remains open.
- **B20:** signed Review P1-corrected, exact-head CI green, fresh independent follow-up clean. Durable FixItem/customer projection remains open.
- **B21:** corrected signed Review rank-before-truncate/count integration green at executable `881430f0...` / CI `35512886836`; focused independent follow-up plus durable customer persistence/card/export consumption remain open.
- **B22:** helper present/tested for exact owner/scan authority plus strict whitelist; actual private-preview entitlement seam remains unwired.
- **B23:** helper present/tested for explicit verified root-cause caps while preserving an existing ceiling; actual health-score boundary remains unwired.
- **B24:** helper present/tested for handoff-v2 and historical v1 compatibility; actual authenticated customer/operator route and persisted source fields remain unwired.

Stage 3 is **in progress**. Do not mark B19–B24 complete merely because helper/signed-review tests pass; customer-visible counts/priorities/scores still require persistence/card/export proof.

## Stage 4 — isolated lane only

Reuse `agent/stage4-b25-b28-compat-release-20260919` / `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, only after complete shared Stage-3 acceptance.

- **B25:** named synthetic corpus + genuine provenance-labelled 30-site baseline/candidate gate.
- **B26:** reproduced own-site serving defects/fixes.
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility.
- **B28:** exact-source review/CI/deployment/live customer acceptance.

The genuine 30-site gate remains **not assessed**. Historical summaries and synthetic fixtures are not a pass. No Stage-4 deployment or live customer acceptance has been run by this integration branch.

## Exact next action

Obtain and inspect a focused independent follow-up review of executable `881430f0ccd1900535fe2d4483e7d217b382954e` and the current persisted checkpoint. Correct any material B19/B21 authority finding with a reproducing regression and fresh exact-head CI.

Do not implement B19/B21 durable customer persistence by copying or recreating V7 route files on this branch: current `main` owns V7/#308 and Stage-1 acceptance still says exact-source publication/non-owner production acceptance is pending. When that single release operator records completion, reconcile this integration branch onto the then-current accepted `main`, preserve V7/#308, run fresh integrated-head CI, then wire authenticated B19/B21 evidence through the real durable V7 persistence/read/card/export surfaces without schema/RLS expansion or suppressed/operator/private leakage. Until then, later Stage-3 source work may continue only where it does not duplicate or mutate the frozen release path.

Do not move production.