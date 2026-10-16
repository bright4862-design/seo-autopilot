# Stage 3 B21 signed delivery checkpoint

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`. The approved spec controls over older handoffs.

This checkpoint covers B21 at the canonical Review -> signed completion boundary. It does **not** claim durable FixItem/card/export completion or authorize production movement.

## Release boundary

`main` remains `2ad64dc55ccc49d8fba4259f3b17ad6cdea643ad`, containing V7 and #308. Current-main `docs/stage-one-evidence-acceptance.md` still records exact-source production publication and fresh non-owner acceptance as pending. This later-stage branch must not copy/recreate V7 persistence routes or move production. After the single Stage-1 release operator records acceptance, reconcile onto the then-current accepted `main`, preserve V7/#308, and require fresh integrated-head CI before durable customer-path wiring.

## B21 required semantics for this seam

- attach truthful unique affected URL, observation, known-population and displayed-sample counts to canonical repairs;
- rank every eligible candidate before the existing 36-item presentation cap;
- use authenticated B19 `impact x reach x page value x confidence` evidence without allowing legacy calibration rank to mask it;
- preserve explicit unknown B19 composite state rather than fabricating a score;
- keep the signed delivery summary bounded to counts and displayed fix IDs;
- authenticate the same Review through the existing completion HMAC;
- preserve scan isolation, privacy, Standard-150 limits and historical canonical metadata.

## RED -> GREEN integration history

The first fixture `bd8ac740320a3d239f053ba690dfb5e6b67cb41f` was rejected by the pre-existing canonical persistence validator and is not semantic RED evidence.

Valid RED `513a4438d5622d393bf3031cb2db17f29caa7ee5` / FixList CI `35506946578` failed exactly because the integrated Review had no `stage3_delivery`; the separate lint/typecheck/contracts/frontend job remained green.

Implementation `86cea88d8a90c62a686015fb9fc464fc0dddfd0d` attached B21 counts and bounded delivery metadata before signing. CI `35507077795` then exposed that the temporary delivery view still inherited legacy `priority_rank`, allowing older calibration order to mask authenticated B19 factor order.

`d74240b751d9ac1fefe070036397d016a6d074aa` removes `priority_rank` only from the temporary B21 ranking view while retaining canonical historical metadata. The remaining failed expectation used cross-cutting `broken_page`, for which B19 truthfully leaves reach/composite score unknown. The fixture was corrected rather than fabricating reach.

`e9aa3789b9b143a7b3b8dbdd0e52ad2edf953a0f` uses a family-scoped B19-known candidate and asserts the known score state before ordering. FixList CI `35507339178` passed.

## Independent-review P1 correction: unknown is not sortable zero

Fresh CodeRabbit review identified a material B19/B21 truncation defect: an explicit unknown B19 composite could be normalized to sortable `0.0` and then use `impact` as a tie-breaker. At the 36-item cap, a high-impact unknown repair could therefore displace a repair whose authenticated B19 composite was genuinely known to be exactly `0.0`.

Regression `467fc4aaf184c2cf8ad99e41dc8baa8fd13ac0d2` covers the unknown-vs-known-zero case.

Behavior fix `2b952e14ac72f03c42be794540574bc06a2c55b7` changes `stage3_delivery._candidate_priority()` so every numeric B19 score, including exact zero, belongs to the known sortable segment and every explicit unknown composite is deferred after all known scores. Impact is not used to compare an unknown composite against a known one.

The reviewer additionally required proof at the real signed Review boundary with more than 36 candidates. Commit `881430f0ccd1900535fe2d4483e7d217b382954e` strengthens `test_stage3_b21_signed_delivery_integration.py` with 37 contract-valid repairs: 35 positive known-score repairs, one authenticated known score exactly `0.0`, and one high-impact cross-cutting repair whose B19 composite remains unknown. The regression proves:

- the known-zero repair remains in the 36 displayed IDs;
- the high-impact unknown repair is omitted;
- the exact `stage3_delivery` object is present in the completion Review;
- recomputing the HMAC over `{version, identity, scan, review}` matches the envelope `proof`.

Exact-code FixList CI `35512886836` passed both jobs on `881430f0ccd1900535fe2d4483e7d217b382954e`:

- root scanner regressions: 115 passed;
- scanner-api: 2030 passed, 18 skipped;
- signed B21 integration tests: 2 passed;
- labelled Stage-1 corpus: synthetic, 14 cases, 55 assertions, `full_30_site_gate=not_assessed`;
- frozen revision `01ebe8e90df1e6bd` matched;
- scanner image `sha256:6d49c53baa876bf38bdf4229399e13ab2164ccbbc40a99e5723589b786aa5022` built;
- lint, typecheck, generated release contracts, frontend contracts and production frontend build passed.

CI requested Node 20 and `setup-node` resolved Node `20.20.2`; hosted JavaScript actions separately warned their action runtime is forced onto Node 24. This is not exact Node 20.19.5 evidence.

## Independent follow-up review closure

Focused CodeRabbit follow-up on exact stable head `7236c36cd65fe441a9a90c6a52db9a6c2342125a` returned in PR #303 issue comment `5750062094` on 2026-09-20 and reported: **no unresolved material issue**.

The reviewer explicitly verified:

- B19 uses only impact x reach x page value x confidence;
- `repair_leverage` does not affect `priority_factor_score`;
- unknown reach or page value keeps the composite `None`;
- the temporary B21 view removes legacy `priority_rank`;
- explicit unknown B19 scores sort after every numeric score, including exact `0.0`;
- impact does not compare an unknown composite against a known composite;
- the 36-item truncation occurs after ranking the eligible set;
- the 37-candidate signed regression keeps the known-zero repair, omits the high-impact unknown repair and verifies the completion HMAC over that exact Review;
- B20 still requires trusted producer identity and repair-local identity can only confirm it;
- `stage3_delivery` contains bounded counts/displayed IDs, not raw candidate evidence;
- external scan projection still runs before signing;
- the Stage-3 path adds no crawl/provider/scheduler/request activity and does not alter the Standard-150 assessed-page boundary.

CodeRabbit stated it did not run the repository test suite; that independent review is paired with our exact-code CI above and exact stable-head FixList CI `35513093636`, which passed both jobs on `7236c36cd65fe441a9a90c6a52db9a6c2342125a`.

The **B21 independent-review gate is therefore closed for the signed authority boundary**.

## Proven state and remaining work

B21 is shared-integrated, behaviorally regression-covered, independently reviewed and exact-head CI green **at the signed Review boundary**. It is not complete overall.

Still required before overall B21 completion:

1. reconcile this branch onto accepted `main` after Stage-1 production acceptance so V7/#308 are preserved;
2. wire authenticated B19/B21 rank/count evidence into the real durable V7 persistence/read model without schema/RLS broadening;
3. prove persisted FixItem -> customer card/export output consumes the intended provenance;
4. prove suppressed/operator-only/private evidence cannot enter customer surfaces;
5. run fresh integrated-head CI and focused independent review for that durable customer-visible seam.

No production deployment, admission/worker mutation, live scan, provider connection, schema/RLS mutation, secret rotation, Premium enablement or Grok enablement is authorized by this checkpoint.