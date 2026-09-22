# Lane A — manifest-bound marginal telemetry

Status: shadow-only engineering evidence for Agent A. This document does not authorize a production crawl budget, deployment, release, persistence change, or customer-visible behavior.

## Purpose

`adaptive_manifest_marginal_binding_v1` closes a population-lineage gap between the deterministic adaptive tranche manifest and the 150/500/1000 marginal-yield benchmark. A marginal result can have internally valid counts and hashes while still referring to a different Smart population. The binding helper requires a replay-valid tranche manifest and exact ordered-population agreement before the telemetry is accepted.

## Contract

The helper:

- requires `adaptive_tranche_selection_manifest_integrity_v1` with `valid=true` and matching input, selection-target, and Standard-reference identities;
- requires the existing strict marginal population-integrity validator to accept the benchmark;
- requires the benchmark candidate count to equal the manifest's unique discovered population;
- binds Smart 150, 500, and 1000 checkpoint fingerprints to the manifest-selected URLs using the marginal benchmark's published ordered-population fingerprint algorithm;
- maps an inventory-limited terminal manifest population to later benchmark checkpoints when the whole discovered candidate population is smaller than that checkpoint;
- rejects same-count population transplantation, fingerprint tampering, replay-identity drift, malformed tranche identities, or authority/completeness claims;
- rebuilds a deterministic binding artifact and validates JSON-like transport without depending on tuple/list representation.

Standard 150 is not recomputed or replaced by a new selector. The binding consumes the existing manifest, whose first tranche is already replay-checked against the existing Standard-150 selector. The artifact records `standard_150_preserved=true` only after that lineage and the marginal Smart-150 population agree exactly.

## Safety boundary

Every accepted artifact keeps `population_scope_complete=false`, `production_budget_authorized=false`, and `site_fully_understood=false`. The helper performs no network I/O and does not touch `run_scan`, global budgets, repair priority, authority/persistence, customer projection, admission, workers, release, deployment, or production.

## Tests

`scanner-api/tests/test_adaptive_manifest_marginal_binding.py` covers exact 150/500/1000 binding, inventory-limited and sub-150 populations, candidate-count drift, same-count population transplantation, invalid manifest replay evidence, replay-identity drift, Smart-500 fingerprint tampering, forbidden authority claims, JSON-like transport validation, artifact tampering, shadow-only flags, and input immutability.

A hermetic pure-function harness for the new helper passed 12/12 scenarios plus `py_compile`. The full repository-native exact-head suite still requires a complete checkout/CI runner; the current execution shell cannot resolve `github.com`, so this checkpoint must not be represented as full repository CI acceptance until GitHub Actions or another exact-head runner executes it.
