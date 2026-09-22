# Lane A — manifest-bound Smart-500 benchmark evidence

Status: shadow-only engineering evidence for Agent A. This checkpoint does not authorize a production crawl budget, deployment, release, persistence change, or customer-visible behavior.

## Purpose

`adaptive_manifest_benchmark_binding_v1` closes the remaining population-lineage gap between the replay-validated 150→500→1000 adaptive tranche manifest and the Smart-500-vs-blind-1000 benchmark bundle. The benchmark bundle already proves that its finding and priority-page evidence share one exact Smart/blind population; this new binding additionally proves that those populations belong to the same discovery input and Smart selector lineage used by the adaptive tranche experiment.

That distinction matters because two benchmark bundles can be internally valid, contain the same page counts, and still describe different URL populations. A coverage result is not eligible for later Smart-500 decisioning unless the Smart population equals the replay-validated manifest selection and the blind reference equals the exact FIFO prefix of the same ordered discovery population.

## Contract

The helper:

- requires `adaptive_tranche_selection_manifest_integrity_v1` with `valid=true` and matching input, selection-target, and Standard-reference identities;
- requires the existing `validate_adaptive_benchmark_bundle(...)` integrity gate;
- receives the original ordered discovered URL identities and verifies their exact raw-input fingerprint against the manifest before using them;
- verifies raw, unique, and exact-duplicate candidate counts across discovery input, manifest, and benchmark bundle;
- binds Smart 500 to the manifest's exact selected population, or to the exact terminal inventory-limited population when fewer than 500 unique candidates exist;
- reconstructs the blind reference as the first `min(1000, unique_discovered)` exact URL identities in discovery order and requires the benchmark's blind population to match it byte-for-byte and order-for-order;
- recomputes the benchmark population fingerprints for both Smart and blind populations;
- verifies that the Smart population starts with the exact replay-validated Standard-150 manifest population;
- rejects discovery-order drift, same-count benchmark transplantation, reordered blind references, candidate-count drift, malformed URL identities, fingerprint drift, and forbidden authority/completeness claims;
- rebuilds a deterministic binding artifact for transport validation.

The binding intentionally fails closed if a benchmark's Smart population does not equal the manifest's exact Smart population, even when both upstream artifacts are independently valid. That is the desired behavior: it prevents a valid-but-unrelated benchmark from being used as evidence for this adaptive experiment.

## Standard 150

No new selector is introduced. Standard 150 remains the existing selector's replay-validated first manifest population. The binding reports `standard_150_preserved=true` only after the benchmark Smart population contains that exact population as its prefix. This helper does not change Standard 150 selection, budget, admission, orchestration, persistence, or customer projection.

## Safety boundary

Every accepted artifact keeps `population_scope_complete=false`, `production_budget_authorized=false`, and `site_fully_understood=false`. The helper performs no network I/O and does not touch `run_scan`, global budgets, repair priority, authority/persistence, customer projection, admission, workers, release, deployment, schema, credentials, or production.

## Verification

`scanner-api/tests/test_adaptive_manifest_benchmark_binding.py` adds 14 focused regressions covering full 500/1000 binding, 620-page and sub-500/sub-150 inventories, invalid replay evidence, replay-identity drift, discovery-order drift, same-count benchmark transplantation, reordered blind-reference transport, duplicate-count drift, forbidden authority claims, malformed identities, transport tampering, shadow-only flags, and input immutability.

A hermetic pure-function harness for the new helper passed 14/14 scenarios, and the new helper/test files passed `py_compile`. Full repository-native exact-head execution remains blocked in the current shell because `github.com` DNS resolution fails; GitHub Actions or another complete checkout must run the exact branch before full-suite acceptance is claimed.
