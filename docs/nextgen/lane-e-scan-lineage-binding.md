# Lane E — exact scan-lineage binding for proving observations

This slice adds `fix_verification_scan_lineage_binding_v1_exact_source_scan_ids` as an additive pure boundary above the existing final observation replays.

URL-origin binding proves that evidence belongs to the same website origin, but it cannot prove that current page observations, rule evaluations, comparison-contract metadata, and the current fix population all came from the same scan run. That leaves a same-origin mixed-scan ambiguity: evidence from two different scans of the same site could otherwise be assembled into an apparently comparable proof.

The new boundary requires exact, non-whitespace historical/current scan IDs, requires historical and current IDs to differ, and requires every proof-bearing source object to carry an exact matching source-scan claim through one of the existing source aliases (`scan_run_id`, `scan_id`, or `source_scan_id`). Conflicting aliases, missing source claims, normalized/coerced IDs, or any foreign-scan row fail closed before the existing PASS/PARTIAL/FAIL or regression-reopen machinery runs.

Two additive authority-facing pure wrappers are provided:

- `fix_verified_fixed_scan_bound_observation_replay_v1_exact_source_scan_ids`
- `fix_regression_reopen_scan_bound_observation_replay_v1_exact_source_scan_ids`

They first prove scan lineage, then delegate unchanged to the existing final observation replay paths. The existing `repair_verification_v3_contract_comparable` implementation is untouched. A disappeared URL remains `COULD_NOT_VERIFY`, never proof of a fix.

Focused regressions cover exact lineage acceptance, malformed authoritative IDs, same-scan replay, historical/current source mismatches, missing page source identity, conflicting rule-evaluation aliases, foreign current-fix rows, positive verified-fixed replay, disappeared-URL non-proof, and regression reopening.

Serialized integration guidance: source `previous_scan_id` and `scan_id` only from authoritative ScanRun/crawl-scope lineage, and attach the same authoritative current scan ID to every page, rule-evaluation, comparison-contract, and current-fix row passed into the scan-bound wrapper. Do not synthesize IDs from repair text, URL identity, timestamps, client input, or customer projection. If the source scan cannot be proven exactly, persist/project nothing and retain `COULD_NOT_VERIFY`/no-reopen semantics.

No durable authority/persistence/customer projection, `run_scan`, global budgets, admission, release/deploy, worker configuration, or production behavior is changed by this slice.
