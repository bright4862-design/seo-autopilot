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

### B19/B20 real signed-review wiring — RED → GREEN

RED: `ac6ce27b3c492649537d80788f7b02b86ec39e5e` added three regressions at the canonical Review → signed completion seam. FixList CI `35501924104` failed as intended in the scanner regression job while the independent lint/typecheck/contracts/frontend job remained green.

GREEN: `7ba2df83d848fd643bb510374b7da5a18ac749f1` modifies `repair_contract_v2.py` so reviewed B19/B20 evidence is derived after the final canonical repair merge/validation and before the durable completion envelope signs Review.

Exact-head FixList CI `35501983203` passed both jobs:

- immutable checkout passed;
- root scanner regressions passed;
- full scanner-api tests passed, including the three new signed-review regressions plus both reviewed Stage-3 lane suites;
- labelled Stage-1 synthetic corpus passed and remains explicitly not the genuine 30-site gate;
- frozen scanner revision passed;
- production scanner image build passed;
- lint, typecheck, generated release contracts, frontend contracts and production build passed.

No new aggregate pytest count is asserted because the Actions summary does not expose the exact total after importing both reviewed Stage-3 lane suites.

B19 behavior now authenticated in signed Review:

- versioned exact `impact × reach × page value × confidence` factors;
- truthful unknown reach remains `None`/`unknown` rather than zero;
- final factors are recomputed over the merged canonical affected-page union;
- repair leverage is not consumed as a substitute/fifth factor;
- the same authenticated factor envelope is mirrored as `priority_factors` for later B24 derivation.

B20 behavior now authenticated in signed Review:

- explicit verified root-cause evidence only; family similarity/generic text is insufficient;
- source pre-fingerprint rows are used so SEO/GEO and family provenance is not erased before grouping;
- affected URL sets are unioned and suppressed-member reason/provenance is retained;
- grouping accepts producer identity only when non-empty `scan_id` and `scan_run_id` exactly match;
- missing/mismatched identity fails closed to singleton `not_verified` groups.

Detailed plan/checkpoint: `docs/superpowers/plans/2026-09-20-stage3-signed-b19-b20-integration.md`.

### Requirement state

- **B19:** partial shared integration. Signed Review carries exact factors/explanations. Durable FixItem/card/export consumption is not yet proven, so B19 is not complete.
- **B20:** partial shared integration. Signed Review carries explicit evidenced grouping and fail-closed identity behavior. Durable persistence/customer projection is not yet proven, so B20 is not complete.
- **B21:** helper is present and tested for unique unions/count distinctions/rank-before-truncate, but not yet wired into the signed persisted customer presentation seam.
- **B22:** helper is present and tested for exact owner/scan authority plus strict field whitelist, but not yet wired to the actual private-preview entitlement path.
- **B23:** helper is present and tested for explicit verified root-cause caps while preserving an existing ceiling, but not yet wired to live health-score production.
- **B24:** helper is present and tested for authenticated handoff-v2 shape and historical v1 compatibility, but actual customer/operator handoff routes and persisted source fields remain unwired.

Stage 3 is **in progress**. Do not mark B19–B24 complete merely because helper and signed-review tests pass.

## Stage 4 — isolated lane only

Reuse `agent/stage4-b25-b28-compat-release-20260919` / `d2ce905ff67410586f86e38bafd93ce4e998e4d1`, CI `35464436789`, only after complete shared Stage-3 acceptance.

- **B25:** named synthetic corpus + genuine provenance-labelled 30-site baseline/candidate gate.
- **B26:** reproduced own-site serving defects/fixes.
- **B27:** GEO/historical HMAC/reader/tamper/privacy compatibility.
- **B28:** exact-source review/CI/deployment/live customer acceptance.

The genuine 30-site gate remains **not assessed**. Historical summaries and synthetic fixtures are not a pass. No Stage-4 deployment or live customer acceptance has been run by this integration branch.

## Exact next action

Continue serially on PR #303 with B21–B24 real delivery integration. First add RED tests proving all eligible B19-scored candidates are ranked before presentation limits and that exact B21 counts survive into the signed authority projection without leaking private evidence. Then minimally wire B21 and the B23 cap decision inside Review while preserving existing access/sample/incomplete ceilings. Only after those are green should B22 private preview and B24 customer/operator handoff v2 be connected to their authenticated downstream paths.

Do not move production.