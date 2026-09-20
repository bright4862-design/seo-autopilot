# Stage 3 B21 signed delivery checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

This checkpoint records the first real shared B21 integration on PR #303. The approved spec controls. It does not authorize production movement and does not complete B21's durable customer-delivery requirement by itself.

## Scope

Connect the already reviewed B21 lane helper to the real canonical Review → signed completion boundary while preserving B19's exact four-factor model and the Stage-1/Stage-2 release invariants.

Required behavior for this slice:

- compute truthful unique affected URL / observation / population / sample counts on every canonical repair;
- rank every eligible candidate with a comparable known B19 score before applying the existing 36-item presentation limit;
- do not let legacy calibration `priority_rank` override B19 four-factor ordering in the Stage-3 presentation view;
- preserve truthful unknown B19 factors rather than inventing reach/page value merely to rank a candidate;
- keep the signed delivery summary bounded and avoid copying raw candidate evidence into a second envelope;
- authenticate the new evidence inside the existing signed Review object;
- preserve historical canonical repair metadata, Standard-150 limits, privacy, scan isolation and all existing release protections.

## RED evidence

The first fixture commit `bd8ac740320a3d239f053ba690dfb5e6b67cb41f` failed the existing canonical persistence validator and is not counted as semantic RED proof.

Valid RED: `513a4438d5622d393bf3031cb2db17f29caa7ee5`.

FixList CI `35506946578` failed in the scanner regression job exactly because the integrated Review had no `stage3_delivery` (`KeyError: 'stage3_delivery'`). The separate lint/typecheck/contracts/frontend job passed. This proves the real shared Review → authority seam was absent before the implementation.

## Implementation sequence

`86cea88d8a90c62a686015fb9fc464fc0dddfd0d`

- imports the reviewed B21 counting/ranking helper into `repair_contract_v2.py`;
- attaches `stage3_counts` to canonical repairs after B19 factor annotation;
- builds bounded `stage3_delivery` metadata with version, eligible/displayed counts, truncation/omission counts and displayed fix IDs;
- returns that evidence in Review before the existing completion HMAC is created.

CI `35507077795` then exposed a real shared-integration bug: the temporary B21 ranking view still contained legacy `priority_rank`, and the reviewed helper correctly preferred that field over `priority_score`. Older calibration order could therefore mask authenticated B19 factor order.

`d74240b751d9ac1fefe070036397d016a6d074aa`

- removes `priority_rank` only from the temporary B21 delivery candidate view;
- leaves canonical repair historical/calibration metadata unchanged;
- maps B19 `priority_factor_score` and `impact` into the reviewed B21 helper.

The remaining failed expectation then showed that the test's chosen `broken_page` candidate was cross-cutting. B19 intentionally leaves family reach/composite score unknown for that class. Treating it as a definitely highest scored item would have required fabricating evidence and would violate B19.

`e9aa3789b9b143a7b3b8dbdd0e52ad2edf953a0f`

- replaces that invalid ordering fixture with family-scoped `duplicate_content`;
- explicitly asserts its B19 `score_state == known` and non-zero `priority_factor_score` before asserting presentation order;
- retains the rank-before-truncate, count, bounded-summary and signed-proof assertions.

This is a semantic correction to the regression, not a weakening: unknown B19 scores remain unknown and only comparable known B19 scores are ordered by the B21 test.

## Independent-review correction: unknown is not sortable zero

A fresh CodeRabbit review then identified a material B19/B21 presentation defect in the earlier B21 ranking helper: an explicit unknown B19 composite score could be normalized to a sortable `0.0` and then use `impact` as a tie-breaker. With more than 36 eligible repairs, a high-impact unknown-score repair could therefore displace a repair whose authenticated B19 score was genuinely known to be `0.0`.

The behavioral correction landed at `2b952e14ac72f03c42be794540574bc06a2c55b7` after regression commit `467fc4aaf184c2cf8ad99e41dc8baa8fd13ac0d2`. `stage3_delivery._candidate_priority()` now separates known-score rows from explicit unknown-score rows. Every numeric B19 score, including exact zero, sorts ahead of the unknown segment; impact is never used to compare an unknown B19 composite against a known composite.

The reviewer additionally required proof at the real signed Review boundary, not only in the pure ranking helper. Commit `881430f0ccd1900535fe2d4483e7d217b382954e` strengthens `test_stage3_b21_signed_delivery_integration.py` with 37 contract-valid repairs: 35 positive known-score repairs, one authenticated known score of exactly `0.0`, and one higher-impact cross-cutting repair whose B19 score is truthfully unknown. The test proves the known zero remains inside the 36-item presentation set, the unknown repair is omitted, the exact `stage3_delivery` decision is present in the completion Review, and the existing completion HMAC authenticates that same Review.

FixList CI `35512886836` passed both jobs on `881430f0ccd1900535fe2d4483e7d217b382954e`:

- root scanner regressions: 115 passed;
- scanner-api: 2030 passed, 18 skipped;
- integrated signed B21 tests: 2 passed, including the >36 unknown-vs-known-zero authority regression;
- labelled Stage-1 corpus: provenance `synthetic`, 14 cases, 55 assertions, `full_30_site_gate=not_assessed`;
- frozen beta revision: `01ebe8e90df1e6bd` matched;
- production scanner image: `sha256:6d49c53baa876bf38bdf4229399e13ab2164ccbbc40a99e5723589b786aa5022`;
- lint, typecheck, generated release contracts, frontend contracts and production frontend build passed.

CI requested Node 20 and `setup-node` resolved Node `20.20.2`; GitHub-hosted JavaScript actions separately warned that their runtime is forced to Node 24. This is not represented as exact Node 20.19.5 evidence.

## Exact verification

The prior executable checkpoint `e9aa3789b9b143a7b3b8dbdd0e52ad2edf953a0f` / CI `35507339178` proved the first signed B21 delivery seam. The corrected executable checkpoint is now `881430f0ccd1900535fe2d4483e7d217b382954e` / CI `35512886836`.

## Proven boundary

The signed Review now carries:

- B19 exact factors/explanations;
- B20 explicit verified root-cause grouping state;
- B21 truthful per-repair count metadata;
- a bounded rank-before-truncate presentation summary;
- an explicit known-before-unknown score ordering at the 36-item cap, including the known-zero edge case.

The existing completion proof authenticates this Review. `stage3_delivery` does not duplicate raw `displayed_candidates`; it publishes bounded displayed fix IDs and aggregate counts only.

## Still open before B21 completion

B21 is **not complete overall**. The following still require real integration and proof:

1. map authenticated B19/B21 evidence into the existing durable persistence/read model without schema/RLS broadening;
2. prove persisted FixItem → customer card/export output uses the intended rank/count provenance;
3. prove suppressed/operator-only/private evidence remains absent from customer surfaces;
4. obtain focused independent follow-up review of the corrected signed B21 boundary and correct any material findings;
5. run fresh exact-head CI after any correction.

The durable V7 persistence/customer route is intentionally not copied into this later-stage branch while Stage-1 exact-source publication/non-owner acceptance remains incomplete. After that release gate closes, the branch must be reconciled onto the then-current accepted `main` before B19/B21 persistence/card/export wiring is finalized, so V7 and #308 are preserved rather than reimplemented or reverted.

No production deployment, worker/admission mutation, live scan, provider connection, schema/RLS mutation, secret rotation, Premium enablement or Grok enablement is authorized by this checkpoint.