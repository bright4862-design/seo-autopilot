# Stage-one independent review

Review scope: baseline `7a744a501416b1b9feac462511071fc9f08e1ba1` through local integration checkpoint `bf626105a85acc13d5fb1b097f86ff13cd0ba118`. A fresh-context reviewer inspected the actual branch diff and the approved specification and plans, without editing the checkout.

Verdict at review: **ready with fixes**. No Critical or Minor findings were reported. Root accepted all four Important findings below as release blockers.

| Finding | Reproduced consequence | Required correction |
| --- | --- | --- |
| Raw finding identity | An accepted apex-to-www redirect caused missing-title findings to disappear; semicolon parameters and empty query delimiters also lost their observed spelling. | Preserve exact observed origin and route at current-version production, with verified redirect provenance. |
| Quality finding identity | A soft-404 at `/product?variant=bad` became a repair targeting the healthy `/product`. | Retain exact identity through quality producers and the authenticated customer projection. |
| Image semantic deduplication | Overlapping material-image and uncertain-image groups suppressed each other. | Keep the two actions distinct in grouped and singleton suppression, including unequal group sizes. |
| Grouped search intent | Three noindexed pages discovered only through internal links received invented sitemap and redirect claims. | Keep declared, sitemap and mixed intent evidence through grouping and generate guidance from the observed source. |

The reviewer independently ran 167 focused Python tests and 106 frontend tests, package closure, generated-contract verification and diff checks; all passed. These results did not invalidate the separately reproduced defects.

The review found the versioned identity/seal dispatch, literal cross-runtime fixtures, actual persistence/export integration and explicitly synthetic corpus structurally sound. It declined to judge deferred B06–B24 work, the genuine paired 30-site gate, and computed visibility from external stylesheets. Production cutover and live acceptance remain separate required evidence.

Corrections require reproducing regressions, fresh full-suite verification, regenerated candidate contracts and exact-source CI before merge. The release evidence is tracked in `stage-one-evidence-acceptance.md`; this report does not claim deployment or live acceptance.

## Root resolution and verification

All four Important findings are corrected. `test_raw_finding_published_identity.py` exercises actual apex-to-www and query-specific soft-404 scans through authenticated customer/chat readers and actual cards/exports, exact canonical/navigation/summary identity, and verified versus unverified redirect controls. `test_image_evidence_dedup.py` covers equal and unequal material/uncertain groups and singleton boundaries. `test_indexability_intent_guidance.py` covers declared-only, sitemap-only and mixed evidence.

Each fix was preceded by a failing reproducer. Root also reproduced a weaker image/template redirect selector and replaced it with the shared successful-HTML proof. Full source verification subsequently passed: 1,798 scanner tests (18 intentional skips), 1,479 frontend tests, root Python tests, lint, typecheck, build, package closure, generated contracts, frozen revision and manifest determinism. No Critical, Important or Minor review items remain open in the reviewed stage-one scope. Root's integration decision is to merge after exact-source CI passes; production acceptance is still pending.
