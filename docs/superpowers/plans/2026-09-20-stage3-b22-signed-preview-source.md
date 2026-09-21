# Stage 3 B22 signed private-preview source checkpoint

Authoritative requirement: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md` B22.

B22 requires an evidence-led private preview: prefer individually verified impact-4/5 findings, otherwise the best verified finding; permit a good-shape message only with the stated coverage qualification; preserve existing entitlements and no-leak rules.

## Scope and release boundary

This slice proves the Python producer/review/signed-authority source only. It does not create, copy, or mutate V7 persistence/customer routes and does not grant an entitlement. The source explicitly records `entitlement_state=requires_authenticated_customer_gate`. Exact owner/customer access remains the V7 responsibility after Stage-1 accepted-main reconciliation.

`main` was refreshed after the review correction and remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`. Current-main `docs/stage-one-evidence-acceptance.md` still records exact-source production publication and fresh non-owner production acceptance as pending. No competing publication, promotion, admission mutation, production scan or rebuild was performed here.

## Original RED -> GREEN source integration

Original RED regression: `29aea5f3ed958805ed21bd2ce75e393e7330ca8f`.

FixList CI `35519071373` failed intentionally in the Python scanner-api job while the independent lint/typecheck/contracts/frontend job passed. The regression failed with `KeyError: 'stage3_private_preview_source'`, proving that the shared signed source did not yet exist. Scanner-api summary at RED: 1 failed, 2037 passed, 18 skipped.

The first implementation sequence was:

- `20849a58acc968a25bd29e72c24abb42626bcb17`: factor the pure evidence-led selector while preserving the existing private helper's authority/exact-owner/exact-scan checks.
- `2f6eb233d89e68475030a18d2157fc3d08b95938`: attach `stage3_private_preview_source` to canonical Review before completion HMAC signing.

FixList CI `35519385104` passed both jobs at `2f6eb233d89e68475030a18d2157fc3d08b95938` with 115 root tests and 2038 scanner-api passed / 18 skipped.

## Fresh independent review finding

Focused CodeRabbit review of the combined B22/B24 signed authority/privacy surface returned a material B22 privacy finding in issue comment `5750750081`: the B22 source could copy arbitrary `coverage_assessment["text"]` into signed `coverage_qualification`. That text is producer-controlled diagnostic material, not an approved customer-safe projection, and could therefore carry private URLs or debug strings into the signed preview source.

The review also exposed an exact B22 semantic gap: when no individually verified impact-4/5 finding exists, the approved spec says **the best verified finding** (singular), not an arbitrary bounded pair of lower-impact findings.

The review result was treated as implementation evidence only after reproduction and correction; no review request or bot status was counted as a pass by itself.

## Review-correction RED

Exact-fallback regression commit: `ac2e1f0e3f1326073a6a37593071c00244338b11`.

FixList CI `35519832761` failed intentionally in the scanner regression job while the independent lint/typecheck/contracts/frontend job passed. This proved the pre-fix selector returned too many lower-impact fallback findings.

The privacy regression expansion then landed at `ba31a4386bb8ac5bf2403048955238676451b756`. It injects distinctive private coverage text and a private URL into Review and requires both to be absent from the preview source and the signed completion envelope. It also proves unknown coverage cannot create a customer-facing good-shape state or qualification text.

## Review correction

Implementation commit: `d2709fb6c430c7bfc0443bd82bc60d43f84764b5`.

`scanner-api/app/stage3_delivery.py` now enforces:

- only `preview_allowed=True` and exact `evidence_state=verified` candidates participate;
- if any individually verified impact-4/5 findings exist, only those high-impact findings are eligible and the existing preview cap remains two;
- otherwise, exactly **one** best verified finding is returned;
- numeric priority zero remains a real known value when ordering preview candidates;
- arbitrary producer `coverage_assessment["text"]` is never copied or signed;
- only explicit normalized `coverage_assessment.state == "sufficient"` can produce a good-shape qualification;
- that qualification is controller-owned fixed customer-safe text: `Coverage was sufficient for the assessed scan scope.`;
- limited, unknown, absent or other coverage states yield `coverage_qualification=None` and cannot create `good_shape`;
- exact trusted producer `scan_id == scan_run_id` remains mandatory for the signed source;
- the source remains an authenticated input to a later customer gate, not an entitlement grant.

The first CI at this implementation head, `35520342700`, still failed because two older isolated-lane unit tests expected the now-rejected behavior of copying raw coverage text. The implementation was not weakened to satisfy those stale assertions. Scanner-api summary was 2 failed, 2039 passed, 18 skipped.

Commit `e7719996e5454f19d373dc04557792992590d834` updates those stale expectations to the approved fail-closed privacy semantics: limited-coverage arbitrary text is not projected, and sufficient coverage uses only the fixed safe controller wording.

## Final GREEN verification

Exact executable SHA: `e7719996e5454f19d373dc04557792992590d834`.

FixList CI `35520663236` completed successfully on both jobs:

- root regressions: 115 passed;
- scanner-api: 2041 passed, 18 skipped;
- B22 signed-preview integration: 5 passed;
- Stage-3 delivery contract tests: 11 passed;
- labelled Stage-1 corpus: synthetic, 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen beta revision: `01ebe8e90df1e6bd` matched;
- production scanner image built as `sha256:2e7c8c8d71a29aa6a09562728189d41a337d1ab1b2e38486d429c6c3f0d4b0f2`;
- lint, typecheck, generated release contracts, frontend contracts and production frontend build passed.

Execution environment was Ubuntu 24.04.5 / Python 3.12.14. CI requested Node 20 but hosted setup resolved Node `20.20.2`; this run is not represented as exact Node 20.19.5 evidence. GitHub's action runtime also emitted its Node-20 deprecation warning; repository Node commands still used the setup-node 20.20.2 toolchain.

## Requirement state

B22 is **partial, not complete overall**.

Proven at the signed authority boundary:

1. exact trusted producer scan isolation;
2. verified-only evidence-led selection;
3. impact-4/5 findings first with the two-finding cap applying only to that preferred set;
4. exactly one best verified fallback when no verified impact-4/5 finding exists;
5. strict finding allowlist of `rule_id`, `title`, `impact`, `evidence_summary`;
6. no affected-URL, suppressed/operator/debug or arbitrary coverage-text leakage;
7. good-shape only from explicit sufficient coverage state, using fixed customer-safe qualification text;
8. completion-HMAC authentication of the source;
9. explicit `requires_authenticated_customer_gate` rather than fabricated owner/customer authorization.

Remaining applicable acceptance:

1. persist this corrected checkpoint and require exact-head FixList CI on the final stable documentation head;
2. obtain one fresh independent follow-up review of the corrected combined B22/B24 authority/privacy surface and fix any material finding with reproduce-first regressions;
3. after Stage-1 exact-source publication and fresh non-owner acceptance are recorded, reconcile onto the accepted V7 `main` without reverting V7/#308 and run fresh integrated-head CI;
4. consume this authenticated source through the real V7 exact-owner/exact-scan entitlement, persistence/read/customer preview/card/export path without recreating routes;
5. prove reload/history privacy, the two-finding high-impact cap / one-finding fallback behavior, and no suppressed/operator/private leakage in real persisted customer output;
6. prove customer-facing good-shape only when the signed source records explicit sufficient coverage.

No deployment, `main` merge, admission/worker mutation, production scan, schema/RLS change, secret rotation, Premium enablement, or Grok enablement occurred in this correction slice.
