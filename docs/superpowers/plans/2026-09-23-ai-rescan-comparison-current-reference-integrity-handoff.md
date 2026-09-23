# AI Layer Lane B — H1-1 Current Repair Reference Integrity Handoff

Status: additive Lane-B pure comparison-contract hardening only. No shared V8 reader/writer, authority creation/verification, customer FixList projection, persistence/schema, crawl/scoring/ranking, admission, Base44/GCP/IAM/secrets, release, deployment, or production surface is modified here.

## Why this slice exists

`scan_comparison_v1` already serialized every historical repair comparison and exactly reconciled previous-scan identity coverage. The current scan was represented only by aggregate counts plus `new_or_came_back_repair_fingerprints`. That left a serialized-integrity gap: a numerically plausible current identity count, continuity flag, current finding ID, or candidate fingerprint could be changed without the envelope containing enough deterministic current-row reference evidence to prove the contradiction.

This slice does not add another comparison engine. `repair_identity.compare_repair_runs()` remains the sole authority for `verified_fixed`, `still_detected`, `came_back`, and `could_not_verify`.

## `current_repair_references`

`build_scan_comparison_v1()` now adds a deterministic reference-only list for the exact current repair population. Each row contains only:

- `repair_fingerprint` — persisted continuity fingerprint when present, otherwise a stable computed technical identity when available, otherwise empty;
- `repair_fingerprint_source`;
- `repair_identity_stable`;
- `finding_id`.

The list is deterministically sorted and carries no customer state, score, recommendation, or authority claim. Provisional computed fingerprints are not promoted into references; persisted provisional fingerprints remain continuity references only.

`validate_scan_comparison_v1()` now fail-closes if the serialized current evidence contradicts itself. It exactly reconciles current repair totals, current repairs without a usable reference fingerprint, and current repairs with stable verification identity. It also proves that historical `same_reference_fingerprint_observed` / `current_finding_id` values agree with the serialized current population, and that the candidate-only fingerprint set is exactly `current references - previous references`.

A forged, injected, omitted, reordered, or identity-upgraded current reference therefore cannot reach the validated presentation or signed transport path merely because the summary still looks plausible.

## Real Funbooker fixture

The existing production-shaped fixture remains unchanged and continues to represent:

- previous scan `6ab272fc6dfa7f9faf97a90f`: score 75, 126 retained pages, 6 repairs;
- current scan `6ab314008da962a9f8c58929`: score 72, 139 retained pages, 7 repairs, exact `previous_scan_id` lineage;
- all six previous persisted fingerprints still present in the rerun;
- two finding IDs changed while their persisted fingerprints survived;
- new H1 reference fingerprint `0a083526db4cd92724b71932`;
- persisted technical repair identity remains provisional.

The safe comparison therefore remains `fixed=0`, `still_detected=0`, `could_not_verify=6`, with one candidate-only new-or-came-back fingerprint. The customer presentation remains prohibited from calling 75 -> 72 a regression because the assessed sample changed 126 -> 139 pages.

## Tests added

`scanner-api/tests/test_scan_comparison_current_reference_integrity.py` covers deterministic current references, exact current identity-count reconciliation, injected and omitted candidate fingerprints, continuity-flag and finding-ID tampering, deterministic ordering, prevention of provisional computed-reference promotion, the exact Funbooker before/after shape, and sample-aware customer presentation.

Pre-push isolated compatibility harness: 49/49 passed, including 11 focused tests against the real Funbooker fixture shape. Repository CI remains the authoritative exact-head broad verification after push.

## Serialized integrator handoff

The existing integration sequence remains unchanged:

1. authenticate exact previous/current V8 rows through the existing authority reader;
2. build the V8-bound comparison using the lane-owned adapter;
3. use only the validated nested `scan_comparison_v1` for presentation;
4. create signed comparison transport only from exact scan-bound authority receipts;
5. wire the already-standalone comparison panel only in the serialized integrator.

The integrator should preserve `current_repair_references` intact through any transport or storage step used for comparison presentation. It must not rebuild the candidate set from customer copy or finding IDs.

## Remaining blocker

The production-shaped Funbooker FixItems still have persisted continuity fingerprints but provisional technical identities. No already-sealed source of the explicit stable `repair_surface` plus `remediation_family` required by the canonical comparator has been demonstrated. Until such a source exists, the six historical repairs must remain `could_not_verify`. Any persistence/schema/authority extension belongs to the authority/integration owner, not Lane B.
