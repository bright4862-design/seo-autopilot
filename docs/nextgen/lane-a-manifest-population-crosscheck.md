# Lane A checkpoint — exact manifest population cross-check

Branch: `agent/nextgen-adaptive-crawl-20260921`  
Draft PR: #328  
Issue: #322

## What this checkpoint adds

Lane A already had replay-manifest bindings for marginal 150/500/1000 telemetry and the Smart-500-vs-blind-1000 benchmark, plus a cross-evidence lineage certificate. One identity gap remained: the two evidence families used different population fingerprint formats, so a later consumer could not independently prove that both artifacts referred to the exact same Smart-500 manifest population rather than two same-count selections from the same discovery input.

`scanner-api/app/adaptive_manifest_population_crosscheck.py` closes that gap without changing selection or crawl behavior. It accepts one replay-validated tranche manifest, one manifest-bound marginal artifact, one manifest-bound benchmark artifact, and the exact discovered URL sequence, then independently recomputes every population identity from the manifest-selected URLs.

## Contract

`build_manifest_population_crosscheck(...)` verifies:

- the tranche manifest replay-integrity identity matches the transported manifest;
- exact raw, unique, and duplicate discovery counts;
- exact ordered discovery-population fingerprint;
- exact manifest populations for the nominal 150, 500, and 1,000 checkpoints, including inventory-limited terminal populations;
- every manifest `selected_population_fingerprint`;
- every marginal checkpoint page count, manifest target/role, inventory state, and marginal population fingerprint;
- exact Standard-150 prefix preservation inside the Smart population;
- exact Smart-500 benchmark population fingerprint computed from the manifest Smart population;
- exact blind-1,000 benchmark fingerprint computed from the FIFO unique discovery reference;
- canonical SHA-256 shape for both source binding fingerprints;
- all source artifacts remain shadow-only and make no authority/completeness claims.

The result is `adaptive_manifest_population_crosscheck_v1`, carrying the exact manifest, marginal, Smart benchmark, and blind benchmark population fingerprints plus one deterministic `crosscheck_fingerprint`.

`validate_manifest_population_crosscheck(...)` rebuilds the artifact and rejects transported/tampered cross-checks.

## Why this matters

The prior cross-evidence lineage reconciled discovery identity, counts, targets, and page geometry, but the marginal and benchmark bindings intentionally hash selected populations differently. This helper supplies the missing common replay surface: both evidence families must now resolve back to the same exact manifest-selected URLs. A benchmark or marginal artifact generated from a different Smart selection is rejected even when candidate counts, discovery order, and target sizes all match.

## Focused verification

The exact new helper/test bytes were exercised in a hermetic pure-function package:

```text
PYTHONPATH=. pytest -q tests/test_adaptive_manifest_population_crosscheck.py
16 passed

python -m py_compile \
  app/adaptive_manifest_population_crosscheck.py \
  tests/test_adaptive_manifest_population_crosscheck.py
passed
```

Coverage includes full 1,000-page references, 620-page inventory limits, sub-500 and sub-150 inventories, duplicate discovery transport, same-discovery/different-Smart-population benchmark transplant rejection, marginal transplant rejection, blind FIFO drift, discovery-order drift, replay-integrity mismatch, manifest selected-population fingerprint drift, forbidden authority claims, malformed binding fingerprints, duplicate/missing checkpoints, JSON transport/tamper rejection, determinism, input immutability, and shadow-only flags.

The Lane-A focused inventory is now **250 tests**: prior 234 plus 16 cross-check regressions.

## Safety boundary

This slice is pure and shadow-only. It does not modify `run_scan`, scanner global budgets, repair priority, authority/persistence, customer projection, admission, release/deployment, worker controls, credentials, or production behavior. It does not crawl, fetch, persist, or authorize a larger crawl. Standard 150 is only verified as the unchanged prefix of the exact manifest selection.

Every success and failure keeps:

- `population_scope_complete=false`
- `production_budget_authorized=false`
- `site_fully_understood=false`

## Exact-head repository gate

The execution shell still cannot resolve `github.com`, so a complete exact-head checkout and combined repository-native Lane-A run cannot be executed from this runtime. The new helper/test exact bytes are verified independently, but the full **250/250 exact-head repository suite is not claimed green** until GitHub Actions or an integrator-capable checkout executes it.

## Integrator handoff

If the serialized integrator later wires the shadow experiment, run this cross-check after replay-validating the tranche manifest and building both manifest-bound evidence artifacts. A failed cross-check must produce `insufficient_evidence`; it must never expand a production crawl budget or claim the site is fully understood.
