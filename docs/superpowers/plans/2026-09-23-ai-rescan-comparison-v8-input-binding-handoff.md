# AI Layer Lane B — H1-1 V8 Input-Binding Handoff

Status: additive Lane-B pure adapter only. This checkpoint does not edit or wire the shared V8 reader/writer, customer FixList projection, authority creation/verification, persistence/schema, crawl/scoring/ranking, admission, Base44/GCP/IAM/secrets, release, deployment, or production.

## Why this slice exists

The canonical `scan_comparison_v1` contract already delegates repair truth to `repair_identity.compare_repair_runs()`, and the signed-authority transport requires exact scan-bound upstream authority receipts. One integration risk remained before those two boundaries: a caller could accidentally assemble an authenticated ScanRun from one scan with a FixList/FixItem population from another scan and then invoke the otherwise-correct comparison helper.

`scanner-api/app/scan_comparison_v8_inputs.py` closes that lane-owned structural gap without creating another comparison engine or authority verifier.

## `scan_comparison_v8_input_binding_v1`

`build_v8_bound_scan_comparison_v1()` accepts the two already-authenticated V8 ScanRun rows, their FixLists, their FixItem populations, and current page evidence supplied by the serialized authority reader. Before invoking comparison it proves:

- `id` and `scan_id`, when both are present, identify the same exact ScanRun;
- current `previous_scan_id` equals the exact previous scan ID;
- each ScanRun's persisted `fix_list_id` points at the supplied FixList;
- each FixList's `scan_run_id` points back at the exact ScanRun;
- every FixItem's `scan_run_id` and `fix_list_id` match that exact scan/FixList pair;
- each FixList `total_fixes` equals the supplied FixItem population;
- persisted ScanRun and FixList health scores agree without recomputing a score;
- sample context comes only from persisted `ScanRun.pages_retained`.

Only after those relationships pass does the adapter call `build_scan_comparison_v1()`. Repair state truth therefore still flows exclusively through `compare_repair_runs()`.

The adapter deep-copies its inputs and returns an ephemeral binding envelope plus the validated canonical comparison. It explicitly records that upstream V8 authority verification is still required and that the adapter itself did not verify authority. It never mutates historical rows.

`validate_v8_scan_comparison_input_binding_v1()` protects a lane-owned binding from count/ID/source/guard tampering and re-runs `validate_scan_comparison_v1()` over the nested comparison. A failed binding must be rebuilt from authenticated source rows; it must not be repaired in the UI.

`build_v8_bound_scan_comparison_transport_v1()` is only a narrow bridge to the already-existing validated signed-authority transport. It accepts exact scan-bound authority receipts created by the existing V8 authority reader; it does not create or verify an authority seal.

## Refreshed production shape

Read-only production evidence was refreshed before this slice. The authoritative Funbooker pair remains:

- previous `6ab272fc6dfa7f9faf97a90f`: score 75, 126 retained pages, FixList `6ab273848d11c45f44f5fbc4`, 6 repairs;
- rerun `6ab314008da962a9f8c58929`: `previous_scan_id=6ab272fc6dfa7f9faf97a90f`, score 72, 139 retained pages, FixList `6ab31484e137e6a837d03cf2`, 7 repairs;
- both persisted FixLists point back to their exact ScanRuns and their `total_fixes` values match the queried FixItem populations;
- all 13 queried FixItems carry the exact `scan_run_id` and `fix_list_id` expected for their persisted parent rows;
- six persisted repair fingerprints survive, including two repairs whose finding IDs changed;
- the rerun adds H1 fingerprint `0a083526db4cd92724b71932`;
- all 13 persisted repair identities remain provisional (`repair_identity_stable=false`, empty `repair_surface`, empty `remediation_family`).

The correct production-shaped comparison therefore remains fail closed: fixed 0, still detected 0, could not verify 6, plus one new-or-came-back candidate. The 75 -> 72 score movement remains descriptive only because the assessed sample changed 126 -> 139 pages.

## Integrator handoff

The serialized V8 integrator should perform the sequence below without adding a second comparison path:

1. authenticate the exact previous/current ScanRun + FixList + FixItem/page populations using the existing owner-bound V8 authority reader;
2. pass those already-authenticated rows into `build_v8_bound_scan_comparison_v1()`;
3. use only `binding["comparison"]` for the existing validated customer presentation path;
4. when signed comparison transport is needed, create exact scan-bound authority verification receipts using the existing authority reader and pass the full binding into `build_v8_bound_scan_comparison_transport_v1()`;
5. render the existing standalone panel model only after validated presentation; do not mutate historical rows.

Current page evidence is still an authority-reader responsibility: this adapter does not invent per-page ownership metadata or independently authenticate detached page rows. If the reader cannot prove that the supplied page evidence belongs to the exact current sealed snapshot, integration must fail closed before this adapter is called.

Historical rows remain readable through the existing historical reader. Rows that cannot satisfy this stronger comparison-input binding are not rewritten or upgraded; cross-scan comparison for them remains unavailable or fail-closed.

## Remaining production blocker

Persisted V8 repair fingerprints are durable references but the queried technical identities remain provisional. The integrator still needs an already-sealed source of the explicit `repair_surface` and `remediation_family` required by `compare_repair_runs()` before the six surviving Funbooker fingerprints can become verified `still_detected`/`came_back` states or before an absent one can become `verified_fixed`. Do not synthesize those fields from copy, category, finding IDs, or the provisional fingerprint. If no sealed source exists, keep `could_not_verify` and hand any persistence/authority design change to the authority owner.
