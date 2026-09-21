# Stage 3 signed B19–B20 integration checkpoint

Date: 2026-09-20

Authoritative spec: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

## Preconditions refreshed

Stage 2 B06–B18 is source/review/CI complete on PR #303. Stable Stage-2 head `10f51529bf5bf64b7b24ab8424f3ae821de46b39` had exact-head FixList CI `35500580582` green. The fresh CodeRabbit follow-up on that exact corrected surface reported `Comments: 0` and no actionable finding (PR #303 issue comment `5748778814`, 2026-09-20T08:48:38Z). This closes the Stage-2 independent-review gate without changing the separate Stage-1 release freeze.

The reviewed isolated Stage-3 inputs were refreshed before integration:

- B19/B20 lane `agent/stage3-b19-b20-decisions-20260919` @ `e74d87acd0cec2955402b96f635f13bc275f3a91`.
- B21–B24 lane `agent/stage3-b21-b24-delivery-20260919` @ `a998b4e38a06d6c163ac8853c3e49e9f10a58cb7`.

Their exact reviewed deltas were copied serially, not merged to `main` and not reimplemented by duplicate workers:

- B19/B20 exact blobs integrated at `c3f9d685e17b26c372a5a47403b478caec36ed2a`.
- B21–B24 exact blobs integrated at `3aebc7375e854ce063ac8853c3e49e9f10a58cb7`.
- Combined exact-head FixList CI `35501672504` passed both jobs.

## RED — real signed-review seam

Commit `ac6ce27b3c492649537d80788f7b02b86ec39e5e` added three behavioral regressions at the canonical Review → signed completion seam and intentionally failed FixList CI `35501924104`.

The regressions require:

1. B19 `impact × reach × page value × confidence` evidence to be attached to final canonical repairs before `build_completion_envelope()` signs Review.
2. Unknown reach to remain `None`/`unknown`, never zero, and arbitrary repair-leverage fields to be unable to become a substitute priority factor.
3. B20 grouping to require the same explicit verified root-cause evidence plus exact matching `scan_id == scan_run_id`; missing/mismatched identity must fail closed to singleton `not_verified` groups.

The non-scanner lint/typecheck/contracts/frontend job stayed green while the scanner regression job failed, proving the new behavioral assertions exposed the absent integration rather than an unrelated build break.

## GREEN — B19/B20 signed authority evidence

Commit `7ba2df83d848fd643bb510374b7da5a18ac749f1` wires the reviewed B19/B20 lane into `repair_contract_v2.py` after the existing complete-or-fail canonical persistence validator and before Review enters the durable signed completion envelope.

Behavior now proven:

- B19 factors are recomputed over each final canonical repair's merged affected-page union, not copied from one pre-merge child.
- `stage3_priority_factors` is versioned by `repair_priority_v3_four_factor_v1`; the same authenticated envelope is exposed as `priority_factors` for the later B24 handoff seam.
- the factor score is exactly impact × reach × page value × confidence when reach and page value are known; unknown denominators remain unknown and do not become zero;
- repair leverage is not read as a fifth/substitute factor;
- B20 consumes pre-fingerprint repair rows so explicit cross-family / SEO-GEO cause evidence is not erased by legacy fingerprint grouping;
- B20 accepts scan identity only when non-empty producer `scan_id` and `scan_run_id` are exactly equal; otherwise the reviewed helper fails closed to singleton/unverified grouping;
- the resulting canonical repairs and `stage3_root_cause_groups` are members of the Review object subsequently signed by `build_completion_envelope()`;
- this change performs no crawl, network request, second request budget, persistence mutation or customer projection.

FixList CI `35501983203` passed both jobs on exact executable head `7ba2df83d848fd643bb510374b7da5a18ac749f1`.

## Independent-review P1 correction — trusted producer identity per B20 member

A fresh CodeRabbit review of the shared B19/B20 authority seam identified one material B20 isolation defect: `stage3_root_causes.py` allowed a repair-local `scan_id` / `scan_run_id` to replace the trusted producer identity passed by `repair_contract_v2.py`. Two foreign repairs with the same local identity could therefore form a verified root-cause group even while the enclosing producer belonged to another scan.

RED commit `6f1e2cc3ae519bbb494cab599579758f9efe427a` added behavioral regressions proving that foreign repair-local identity must not override producer identity and that matching repair-local identity remains allowed. FixList CI `35503985665` failed in the scanner regression job as intended while the lint/typecheck/contracts/frontend job passed.

Implementation commit `56a9362ceb9ec1b06b88e26a0fd7db8fff97e92c` replaced repair-local identity ownership with `_trusted_member_scan_identity()`: the already-validated producer identity is authoritative; a present repair-local `scan_id` or `scan_run_id` is only a consistency assertion and any mismatch downgrades that member to singleton `not_verified`. Missing trusted producer identity cannot be resurrected by a repair-local value.

The first CI on that implementation, `35504067902`, exposed one older lane assertion that still expected a repair-local identity to establish trust when the producer identity was absent. That assertion conflicted with the approved fail-closed semantics and the independent review requirement, so it was strengthened rather than bypassed.

Commit `cbfd2b1f4a696c209dfab90e3981f42b0cbaa481` updates that lane regression to require no trusted scan ID and `not_verified` singleton groups when the helper receives no producer identity. Exact-head FixList CI `35504200573` passed both jobs: root regressions, full scanner-api tests, labelled synthetic corpus, frozen revision, production scanner-image build, lint, typecheck, generated contracts, frontend contracts and production build all passed.

B20 scan isolation now requires all of the following before a verified multi-member group can exist:

- the enclosing producer provides a non-empty exact `scan_id == scan_run_id`;
- every repair-local `scan_id` / `scan_run_id` that is present exactly matches that trusted producer identity;
- explicit versioned verified root-cause evidence and evidence references are present;
- same family, similar wording, matching URLs or repair-local identity alone can never create trust.

A fresh independent follow-up review is still required on the final stable checkpoint before B20 is recorded review-complete.

## Requirement state after this slice

- B19: **partially shared-integrated**. Exact factors/explanations are now on final canonical repairs and inside signed Review. Durable persisted FixItem/customer/card/export consumption still needs an explicit reviewed projection; do not call B19 complete yet.
- B20: **partially shared-integrated and P1-corrected**. Explicit evidenced grouping now enters signed Review and every member is bound to trusted producer identity. Exact-head CI is green; fresh independent follow-up review plus durable persistence/customer projection remain open.
- B21–B24: reviewed lane code is present on the serialized integration branch and combined CI is green, but shared authority/persistence/customer wiring is not yet complete.

## Next action

After the focused follow-up review of the corrected B20 scan-isolation boundary, continue on the same branch with the B21–B24 shared delivery seam. Rank the B19-scored eligible canonical repairs before presentation truncation, derive honest count summaries and authenticated private-preview/handoff data inside the signed authority boundary, then wire only reviewed allowlisted fields through persistence/customer/card/export. Preserve existing health/access/sample/incomplete ceilings and historical v1/HMAC readers. Require RED → GREEN behavioral tests and exact-head CI before marking any requirement complete.

Stage-1 production remains frozen and separate. Do not merge to `main`, publish, promote worker traffic, mutate admission, run a production scan, rotate secrets, broaden schema/RLS, or enable Premium/Grok.