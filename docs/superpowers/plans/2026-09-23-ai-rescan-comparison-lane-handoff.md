# AI Layer Lane B — H1-1 Rescan Comparison Handoff

Status: lane-owned pure comparison work only. No production wiring, deployment, schema, authority, scoring, crawl, persistence, admission, or customer projection changes are authorized by this document.

## Refreshed baseline

- Source baseline: `main` at `c1080d75f7d1aacd748e74009be7a6c15aa40a93`.
- The current UI helper in `src/lib/scanHistoryPresentation.js` intentionally exposes lineage only and forbids manufacturing improvement/worsening/fixed claims.
- Read-only production evidence confirms the authoritative Funbooker pair:
  - previous scan `6ab272fc6dfa7f9faf97a90f`: score 75, 126 pages crawled/retained, 6 persisted FixItems;
  - current scan `6ab314008da962a9f8c58929`: `previous_scan_id=6ab272fc6dfa7f9faf97a90f`, score 72, 139 pages crawled/retained, 7 persisted FixItems;
  - both rows are complete and carry `standard_review_snapshot_hmac_identity_v1` authority seals;
  - all six prior persisted `repair_fingerprint` values are present again in the rerun; two of those repairs have different `fix_id` values across scans while the fingerprint is unchanged;
  - the rerun adds `missing_h1` with persisted repair fingerprint `0a083526db4cd92724b71932`.

The regression fixture intentionally excludes raw authority proofs.

## Implemented lane-owned contract

`scanner-api/app/scan_comparison.py` provides three pure, versioned boundaries:

1. `scan_comparison_v1`
   - requires exact previous/current scan IDs and exact `current_previous_scan_id` lineage;
   - delegates every fixed/still-detected/came-back/could-not-verify decision to `repair_identity.compare_repair_runs()`;
   - preserves persisted `repair_fingerprint` as a reference identity even when the persisted repair identity is provisional;
   - never upgrades a persisted provisional fingerprint into `verified_fixed` authority;
   - groups unmatched current reference fingerprints only as **new-or-came-back candidates**, never as a verified-new claim;
   - records score and sample context without recomputing score;
   - always keeps score-direction claims disabled in v1.

2. `scan_comparison_presentation_v1`
   - presents score movement descriptively;
   - explicitly warns when assessed sample sizes differ;
   - never emits an overall improvement/regression verdict from score movement;
   - keeps new-or-came-back as a candidate label, not a verified claim.

3. `scan_comparison_transport_v1`
   - accepts only exact scan-bound upstream authority-verification receipts;
   - fingerprints the comparison payload for transport integrity;
   - does not verify or create an authority seal itself;
   - explicitly leaves customer projection unauthorized and requires serialized V8 integrator ownership.

## Fail-closed production finding

The read-only persisted Funbooker FixItems expose durable `repair_fingerprint` values, but the queried rows also report:

- `repair_identity_state = provisional`;
- `repair_identity_stable = false`;
- empty `repair_surface`;
- empty `remediation_family`.

That matters because the canonical `compare_repair_runs()` contract deliberately requires a stable technical repair identity before it may produce `still_detected`, `came_back`, or `verified_fixed`. Lane B therefore does **not** reinterpret the persisted fingerprint as verification authority.

With the current persisted V8 projection, the production-shaped regression correctly yields:

- fixed: 0;
- still detected: 0;
- could not verify: 6;
- one unmatched current fingerprint as a new-or-came-back candidate;
- zero false `verified_fixed` claims.

This is the correct fail-closed state until the serialized integrator can supply comparator-ready stable technical identity from already sealed evidence without weakening authority.

## Integrator handoff

The shared V8 integrator should choose an existing sealed source that can supply the canonical comparator with the stable technical identity fields it already expects. Do not synthesize a repair surface/remediation family from copy, finding IDs, categories, or the provisional persistence fingerprint. If no currently sealed artifact contains that identity, the integration remains `could_not_verify`; adding or changing persistence/schema/authority is outside this lane.

For authority transport, the integrator should provide a bounded verification receipt per scan only after the existing V8 authority reader has verified that scan. The receipt shape expected by this lane is:

```text
state = verified
scan_id = exact opaque ScanRun id
authority_seal_version = existing verified seal version
authority_proof_fingerprint = sha256 of the already-verified proof material
```

The lane transport helper checks exact IDs and receipt shape only. It is not a substitute for V8 authority verification.

## Regression scope

Focused tests cover:

- canonical comparator `verified_fixed` -> summary `fixed` semantics;
- `still_detected` despite finding-ID change when stable technical identity is present;
- `came_back` from a previously verified-fixed repair;
- blocked evidence -> `could_not_verify`, never `verified_fixed`;
- incompatible rule/comparison contract -> `could_not_verify`, never `verified_fixed`;
- exact scan lineage binding;
- persisted fingerprint continuity when finding IDs change;
- deterministic ordering;
- provisional/no-reference fail-closed behavior;
- production Funbooker 75/6/126 -> 72/7/139 shape;
- sample-size warning and no “worse by 3” style claim;
- upstream authority receipt binding and fail-closed receipt errors.

No historical row is mutated by these helpers.
