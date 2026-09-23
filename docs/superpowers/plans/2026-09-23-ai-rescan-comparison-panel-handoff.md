# AI Layer Lane B — H1-1 Standalone Comparison Panel Handoff

Status: additive Lane-B presentation library only. This checkpoint does not wire the comparison into the live FixList/V8 reader or writer, and it does not alter authority, persistence, scoring, crawl targets, customer projection, admission, schema, Base44/GCP, IAM, release, deployment, or production.

## Refreshed baseline

At this checkpoint `main` remains `c1080d75f7d1aacd748e74009be7a6c15aa40a93`. Repo instructions and the existing H1-1 comparison/integrity handoffs were re-read before implementation.

The read-only Funbooker regression evidence remains:

- previous scan `6ab272fc6dfa7f9faf97a90f`: score 75, 6 repairs, 126 pages;
- rerun `6ab314008da962a9f8c58929`: `previous_scan_id=6ab272fc6dfa7f9faf97a90f`, score 72, 7 repairs, 139 pages;
- all six previous persisted repair fingerprints survive the rescan, including two whose finding IDs changed;
- the rerun adds H1 fingerprint `0a083526db4cd92724b71932`;
- persisted technical repair identity remains provisional, so canonical comparison still closes at fixed=0, still_detected=0, could_not_verify=6 plus one new-or-came-back candidate;
- the three-point score decrease is descriptive only because the assessed sample changed from 126 to 139 pages.

## Standalone panel model

`src/lib/scanComparisonPanelModel.js` adds `scan_comparison_panel_model_v1`. It accepts only the server-owned `scan_comparison_presentation_v1` shape that the integrator must obtain from `build_validated_customer_scan_comparison_presentation()`.

The model deliberately does not inspect raw FixItems, call a comparator, compare repair fingerprints, recompute a health score or score delta, or infer improvement/regression. It only maps already-safe presentation evidence into a standalone view model.

It fails closed to `state=unavailable` when:

- the payload is not the exact trusted presentation version;
- scan IDs are invalid or self-referential;
- comparison-direction or verified-candidate flags are enabled;
- score/sample/caution context is missing;
- the score line itself contains directional improvement/regression language;
- required counts are missing, non-integer, or negative.

A ready model always carries `comparisonClaimAllowed=false`, `scoreDirectionClaimAllowed=false`, `overallImprovementOrRegressionClaim=null`, `newOrCameBackIsVerifiedClaim=false`, and `historicalRowsMutable=false`.

## Customer-safe Funbooker behavior

For the real production-shaped before/after values, the panel model shows:

- `Health score changed from 75 to 72.`
- `The assessed sample was 126 pages before and 139 pages now.`
- an explicit warning that the changed sample means the score difference alone does not prove improvement or regression;
- Fixed: 0;
- Still detected: 0;
- New or returned candidate: 1;
- Could not verify: 6.

It never turns the score delta into `worse by 3`, and the new H1 remains a candidate rather than a verified historical state.

## Integrator handoff

The serialized V8 integrator should:

1. load/authenticate the two historical scan records through the existing authority reader;
2. build `scan_comparison_v1` through the existing Lane-B helper, which delegates all repair truth to `repair_identity.compare_repair_runs()`;
3. run `validate_scan_comparison_v1()`;
4. derive customer copy with `build_validated_customer_scan_comparison_presentation()`;
5. pass only that presentation object into `buildScanComparisonPanelModel()`;
6. render the resulting standalone panel near scan history/comparison UI without modifying historical rows.

Do not pass raw `scan_comparison_v1` into the panel library and do not use score movement to fill missing comparison states.

The unresolved shared blocker is unchanged: production FixItems still expose provisional technical identity. The authority/persistence owner must locate an already-sealed source of stable `repair_surface` and `remediation_family` before canonical verified fixed/still/came-back states can be promoted. If no such sealed source exists, the comparison must remain `could_not_verify`.

## Pre-push verification

Exact candidate bytes were checked before repository writes:

- `node --check src/lib/scanComparisonPanelModel.js`: passed;
- focused panel-model tests: 11/11 passed;
- panel-model + existing scan-history presentation tests: 15/15 passed.

The library is intentionally not imported by a live V8/FixList component in this lane. No merge or deployment is authorized from Lane B.
