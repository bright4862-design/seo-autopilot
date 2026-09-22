# Lane A — manifest-bound marginal Fix-yield telemetry

## Scope

`adaptive_manifest_fix_yield_v1` is a pure, shadow-only telemetry helper for Agent A. It measures Fix-fingerprint yield on the exact populations already selected by the replay-validated adaptive tranche manifest. It performs no crawling, persistence, repair ranking, budget mutation, admission, release, deployment, or customer projection.

The helper exists to keep "Fix yield" distinct from generic finding yield without crossing the serialized-integrator ownership boundary. Callers supply opaque Fix fingerprints and, optionally, opaque high-impact Fix fingerprints. The helper only deduplicates and counts those identities.

## Contract

The builder requires both:

1. an `adaptive_tranche_selection_manifest_v1`; and
2. the matching `adaptive_tranche_selection_manifest_integrity_v1` with `valid=true`.

The integrity artifact must match the manifest's discovered-population fingerprint, selection targets, and Standard-reference fingerprint. The manifest's tranche populations are then checked again for exact selected/added fingerprints, count arithmetic, prefix nesting above Standard 150, and inventory-limited state.

For each exact tranche, the result reports:

- pages assessed and pages added;
- new and cumulative Fix fingerprints;
- new Fix yield per 100 added pages;
- new and cumulative high-impact Fix fingerprints when that evidence was supplied;
- high-impact Fix yield per 100 added pages;
- exact selected and added population fingerprints.

Missing high-impact evidence remains `not_observed` with `None` metrics. It is never converted to zero.

## Standard 150 and authority boundary

The first manifest tranche must be the exact Standard reference at no more than 150 pages, and its population fingerprint must equal the manifest's Standard-reference fingerprint. The helper therefore measures Fix yield without selecting a different baseline.

Every output hard-codes:

- `population_scope_complete=false`
- `production_budget_authorized=false`
- `site_fully_understood=false`

A positive yield signal is telemetry only. It cannot authorize a 500- or 1,000-page production crawl and cannot alter repair priority.

## Integrity and regression coverage

`validate_manifest_bound_fix_yield(...)` recomputes the complete artifact from the same manifest and Fix evidence and rejects transport drift, arithmetic tampering, changed authority flags, or a mismatched replay-integrity artifact.

Focused regressions cover deterministic 150→500→1000 yield, inventory-limited and sub-150 populations, cross-page Fix deduplication, unknown high-impact evidence, high-impact subset enforcement, replay-integrity mismatch, population/fingerprint tampering, prefix drift, JSON transport, authority-claim tampering, determinism, and input immutability.
