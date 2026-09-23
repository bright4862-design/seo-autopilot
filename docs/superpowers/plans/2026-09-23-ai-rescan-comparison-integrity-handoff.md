# AI Layer Lane B — H1-1 Serialized Comparison Integrity Handoff

Status: additive Lane-B pure validation only. This checkpoint does not alter V8 authority, persistence, customer projection, scoring, crawling, admission, schema, Base44/GCP, IAM, release, deployment, or production.

## Why this slice exists

`scan_comparison_v1` already delegates repair truth to `repair_identity.compare_repair_runs()`, preserves exact scan lineage, keeps score direction descriptive, and has a fail-closed V8 transport candidate. A later serialized or historical read could still be internally tampered while retaining the same version string. Presentation code must not trust a changed summary count, changed score context, or contradictory candidate fingerprint just because the outer version remains `scan_comparison_v1`.

This slice adds `scanner-api/app/scan_comparison_integrity.py` with version `scan_comparison_integrity_v1`. It does **not** compare repairs and therefore does not create a second comparison engine.

## Contract

`validate_scan_comparison_v1()` rechecks the already-produced envelope before presentation or transport:

- exact previous/current scan IDs and `current_previous_scan_id` lineage;
- canonical row state -> summary-state mapping (`verified_fixed` -> `fixed` only);
- deterministic row order and non-negative comparator evidence counters;
- reference-fingerprint shape/source without promoting provisional fingerprints to verification authority;
- summary counts exactly matching repair rows;
- previous/current repair identity accounting bounds;
- unique sorted new-or-came-back candidate fingerprints that were absent from the previous reference population;
- score delta exactly matching the two source scores;
- sample-size flag exactly matching checked-page counts;
- score-direction claims remaining disabled;
- exact canonical comparison-engine marker;
- `creates_customer_fixes`, `recomputes_score`, and `mutates_historical_rows` remaining false.

Two narrow wrappers call the validator before the existing Lane-B presentation/transport helpers:

- `build_validated_customer_scan_comparison_presentation()`;
- `build_validated_scan_comparison_transport_v1()`.

A contradiction raises and fails closed. The validator never repairs or normalizes a contradictory historical payload. The serialized integrator must rebuild from authenticated source inputs instead.

## Refreshed production evidence

Read-only production evidence remains:

- previous Funbooker scan `6ab272fc6dfa7f9faf97a90f`: score 75, 126 checked/retained pages, 6 FixItems;
- rerun `6ab314008da962a9f8c58929`: exact `previous_scan_id` link, score 72, 139 checked/retained pages, 7 FixItems;
- all six previous persisted repair fingerprints recur; two finding IDs changed while their fingerprints survived;
- current scan adds H1 fingerprint `0a083526db4cd92724b71932`;
- both scans remain authority-sealed and authoritative;
- persisted repair identity is still provisional on all 13 queried FixItems: `repair_identity_stable=false`, empty `repair_surface`, empty `remediation_family`.

Therefore the real production-shaped contract still closes at fixed=0, still_detected=0, could_not_verify=6, plus one new-or-came-back candidate. The three-point score decrease is descriptive only because the sample changed from 126 to 139 pages.

## Integrator handoff

For any serialized/historical `scan_comparison_v1`, run `validate_scan_comparison_v1()` before presentation or authority transport. Never patch a failed payload in the UI. For transport, the existing upstream V8 authority reader must still verify each exact scan and provide the scan-bound authority receipts; this lane does not verify or create authority.

The unresolved production blocker is unchanged: locate an already-sealed source of the stable technical `repair_surface` and `remediation_family` required by `compare_repair_runs()`. Do not infer them from customer copy, category, finding ID, or a provisional persisted fingerprint. If no sealed source exists, keep `could_not_verify` and hand the persistence/authority decision to the serialized owner.

## Verification

Candidate bytes were checked in a branch-native checkout based on Lane-B head `9f2cc47be649d96094d8eb0637954158fdde6ba1`:

- comparison + integrity focused tests: 38/38 passed;
- comparison/integrity + repair identity/repair contract relevant set: 88/88 passed;
- complete `scanner-api` suite: 2139 passed, 18 skipped;
- `py_compile` and `git diff --check`: passed.

No historical row was modified. No merge or deployment is authorized from this lane.
