# Blueprint implementation checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This is the current serialized handoff for the FixList full-scanner blueprint. Historical checkpoints remain in Git history and linked executable plans. The approved spec controls over older paraphrases.

## Release boundary

- Stage-1 publication/promotion/live non-owner acceptance remains owned by the existing exact-source release operator.
- `main` was last verified at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`; later-stage work has no authority to move production.
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

### B21 real signed delivery wiring — RED → GREEN

B21 is no longer helper-only. It is now connected to the canonical Review before the existing completion HMAC signs authority.

- `bd8ac740320a3d239f053ba690dfb5e6b67cb41f`: first fixture attempt failed the pre-existing canonical persistence validator and is not semantic RED evidence.
- `513a4438d5622d393bf3031cb2db17f29caa7ee5`: valid RED fixture. FixList CI `35506946578` failed exactly with missing `stage3_delivery` at the integrated Review boundary; build/contracts remained green.
- `86cea88d8a90c62a686015fb9fc464fc0dddfd0d`: implementation attaches truthful `stage3_counts` per canonical repair and bounded `stage3_delivery` summary before signing.
- CI `35507077795` exposed that the temporary delivery view still inherited legacy `priority_rank`, allowing earlier calibration order to mask B19 factor scores.
- `d74240b751d9ac1fefe070036397d016a6d074aa`: removes legacy `priority_rank` only from the temporary B21 ranking view; canonical historical metadata remains untouched.
- That test then revealed its high-priority fixture used cross-cutting `broken_page`, where B19 correctly leaves reach/composite score unknown. The fixture was corrected rather than fabricating reach or weakening B19.
- `e9aa3789b9b143a7b3b8dbdd0e52ad2edf953a0f`: uses a family-scoped `duplicate_content` candidate with known B19 score and asserts that known state before rank-order expectations.
- Exact-head FixList CI `35507339178`: **green on both jobs**. Root regressions 115 passed; scanner-api `2029 passed, 18 skipped`; Stage-1 corpus stayed explicitly synthetic at 14 cases / 55 assertions / `full_30_site_gate=not_assessed`; frozen revision `01ebe8e90df1e6bd` passed; production scanner image `sha256:e7378326b2f8030b7cbe23f0fb5a01a0f7f50a18e80d75b5c28fe8ee8b38ccc1` built; lint/typecheck/generated contracts/frontend contracts/build passed.
- CI's requested Node 20 resolved to Node `20.20.2`; hosted JavaScript action runtime separately warns it is forced to Node 24. Do not cite this as Node 20.19.5 evidence.

B21 signed authority behavior now proves:

- unique affected URL union, observation count, known population count, displayed sample count, displayed samples, partiality and truncated-sample count are attached to every canonical repair;
- all eligible candidates with comparable B19 scores are ranked before the 36-item presentation limit;
- legacy `priority_rank` cannot mask B19 factor order in the B21 temporary ranking view;
- unknown B19 scores remain unknown;
- signed delivery output is bounded to version/counts/omitted count/displayed fix IDs and does not duplicate raw candidate evidence;
- the existing completion proof authenticates the Review carrying B19/B20/B21.

Detailed plan/checkpoint: `docs/superpowers/plans/2026-09-20-stage3-b21-signed-delivery.md`.

### Requirement state

- **B19:** signed Review integration green. Durable FixItem/card/export consumption remains open.
- **B20:** signed Review integration P1-corrected, exact-head CI green, fresh independent follow-up review clean. Durable FixItem/customer projection remains open.
- **B21:** signed Review rank-before-truncate/count integration green on `e9aa3789...`; durable persisted customer/card/export consumption and focused independent review of the new B21 seam remain open.
- **B22:** helper is present and tested for exact owner/scan authority plus strict field whitelist, but not yet wired to the actual private-preview entitlement path.
- **B23:** helper is present and tested for explicit verified root-cause caps while preserving an existing ceiling, but not yet wired to the actual health-score production boundary.
- **B24:** helper is present and tested for authenticated handoff-v2 shape and historical v1 compatibility, but actual customer/operator handoff routes and persisted source fields remain unwired.

Stage 3 is **in progress**. Do not mark B19–B24 complete merely because helper/signed-review tests pass; any customer-visible counts/priorities/scores still require persistence/card/export proof.

## Stage 4 — isolated lane only

Reuse `agent/stage4-b25-b28-compat-release-20260919` / `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, only after complete shared Stage-3 acceptance.

- **B25:** named synthetic corpus + genuine provenance-labelled 30-site baseline/candidate gate.
- **B26:** reproduced own-site serving defects/fixes.
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility.
- **B28:** exact-source review/CI/deployment/live customer acceptance.

The genuine 30-site gate remains **not assessed**. Historical summaries and synthetic fixtures are not a pass. No Stage-4 deployment or live customer acceptance has been run by this integration branch.

## Exact next action

Continue serially on PR #303. First wire authenticated B19/B21 evidence through the existing durable persistence/read model and prove persisted FixItem → customer card/export behavior without schema/RLS expansion or leakage of suppressed/operator-only/private evidence. Then connect B23 at the current health-score boundary while preserving all existing access/sample/incomplete ceilings. After those visible score/count seams are proven, wire B22 private preview and B24 handoff-v2 through authenticated allowlists with historical v1 compatibility. Each shared slice requires RED → GREEN behavior, exact-head FixList CI and focused independent review.

Do not move production.