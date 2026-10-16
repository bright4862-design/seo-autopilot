# Stage 3 B23 signed health-score cap checkpoint

Authoritative requirement: B23 in `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

Status: **source/signed-authority slice implemented and exact-code CI green; independent review and durable customer score consumption still open**.

## Release boundary

- `main` remains frozen at `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad` pending Stage-1 exact-source publication plus fresh non-owner production acceptance.
- This slice stays on PR #303 / `agent/full-blueprint-stage2-coverage-b06-20260919`.
- No production deploy, worker/admission mutation, live scan, schema/RLS change, secret change, Premium/Grok enablement, or recreation of V7 persistence routes occurred.
- The legacy customer-visible `health_score` is deliberately **not rewritten** by this source-only slice. Any displayed-score change remains gated on accepted Stage-1 main reconciliation plus real persistence/card/export proof.

## RED proof

Test-only commit `c713baca3f65da28bd52616960fdcb30e8f52d49` added a signed-boundary expectation for `stage3_health_score_decision` before implementation existed.

FixList CI `35514082243` failed in `Run Python scanner-api tests` while the separate lint/typecheck/contracts/frontend-build job remained green. This is the intentional RED proof that the real canonical Review -> completion-HMAC path did not yet contain B23 authority evidence.

## Implementation

- `5d967faa32e6a0790cf5cae013717a35455ba9b4` binds optional `score_cap` only to the same versioned, explicit, verified B20 `root_cause_evidence` that establishes the root cause.
  - accepted caps are explicit whole-number numeric values from 0..100;
  - unverified/conflicted/cross-scan evidence cannot contribute a cap;
  - conflicting explicit caps for one verified B20 group fail closed to `score_cap_state=conflicted` instead of selecting the harsher value.
- `addc071e2fcc2d4f2392eb1fa5586cb73dde352e` attaches a bounded `stage3_health_score_decision` to canonical Review before completion signing.
  - the already-final legacy `review.health_score` is used as B23's base, so this layer cannot raise a score that has already been constrained by access/sample/incomplete handling;
  - an existing explicit legacy ceiling is carried from `health_score_explanation.applied_ceiling` when available; it is not recomputed;
  - authenticated B20 groups are collapsed to one cap decision per `root_cause_id`, preventing duplicate SEO/GEO/cross-rule penalties;
  - conflicting caps across verified groups for the same root cause fail closed;
  - coverage state is preserved, with missing coverage represented as `unknown` rather than invented success/failure;
  - the current customer-visible legacy `health_score` remains unchanged.
- `bdd7fc4e2794227997b181693b203b157304ba02` adds adversarial conflict and foreign-scan regressions.
- `23d28ddee804e9c20db4136f06aab879685d1942` separates two behaviors in the signed integration fixture: a verified cap can produce a lower authenticated candidate score, while a stricter pre-existing incomplete ceiling still wins and cannot be raised.

## Behavioral proof

`scanner-api/tests/test_stage3_b23_signed_score_caps_integration.py` now proves:

1. a documented verified root-cause cap (72) yields a signed B23 adjusted candidate score of 72 from a legacy score of 88, while the legacy customer-visible score remains 88 in this release-gated slice;
2. an existing incomplete ceiling of 55 remains effective when the root-cause cap is 72;
3. conflicting documented caps (72 vs 48) for the same verified root cause fail closed and apply no B23 penalty;
4. repair-local foreign `scan_id`/`scan_run_id` values cannot use a documented cap after B20 scan isolation rejects the group;
5. the completion HMAC authenticates the exact B23 decision in the canonical Review.

Existing `stage3_delivery.py` helper regressions continue to prove unverified/heuristic/missing caps are ignored and unknown coverage does not invent a penalty.

## Verification

Exact executable head `23d28ddee804e9c20db4136f06aab879685d1942` passed FixList CI `35514416069` on both jobs:

- root scanner regressions: passed;
- full Python scanner-api suite: passed;
- labelled Stage-1 synthetic corpus: passed (still synthetic; not B25's real 30-site gate);
- frozen beta revision check: passed;
- production scanner image build: passed;
- lint/typecheck/generated release contracts/frontend contracts/production frontend build: passed.

This run does **not** claim exact Node 20.19.5 evidence; hosted CI setup details remain separate from the requirement.

## Requirement status / open gates

B23 is now **partial at the real signed-authority seam**, not complete overall.

Still required before B23/full Stage 3 completion:

- focused independent review of the exact integrated B23 head and any resulting RED -> GREEN correction;
- after Stage-1 acceptance/reconciliation onto current V7 main, authenticated persistence/read/card/export proof before any B23-adjusted score is customer-visible;
- preserve historical readers/signatures and all current access/sample/incomplete ceilings on the reconciled source;
- exact-head CI again after any review or reconciliation change.

Next source-only slice while the Stage-1 release gate remains closed should be B22 or B24 only if it can be integrated without copying/recreating the frozen V7 persistence/customer route. Otherwise hold for release reconciliation.