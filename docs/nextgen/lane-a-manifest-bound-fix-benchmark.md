# Lane A — manifest-bound Smart-500 vs blind-1000 Fix benchmark

## Scope

`adaptive_manifest_fix_benchmark_v1` is a pure, shadow-only benchmark helper for Agent A. It compares opaque Fix-fingerprint evidence from the exact replay-validated Smart-500 population with a FIFO blind-1000 reference from the same discovered URL sequence. It does not crawl, persist, rank repairs, mutate budgets, project customer output, alter admission, release, deploy, or write production state.

This complements the existing manifest-bound marginal Fix-yield telemetry: the marginal helper answers what additional Fix evidence appears as the adaptive population grows, while this helper answers how much Fix evidence Smart 500 preserves relative to a blind 1,000-page reference.

## Population contract

The builder requires:

1. an `adaptive_tranche_selection_manifest_v1`;
2. matching replay-valid `adaptive_tranche_selection_manifest_integrity_v1` evidence;
3. the exact ordered discovery sequence that produced that manifest; and
4. caller-supplied opaque Fix fingerprints, with optional opaque high-impact Fix fingerprints.

It verifies exact raw/unique/duplicate discovery geometry, the manifest discovery fingerprint, tranche count/fingerprint/prefix integrity, Standard-reference identity, and that Smart/Standard pages actually belong to the supplied discovery population. Smart 500 comes only from the exact manifest population. The blind reference is deterministic FIFO exact-identity de-duplication capped at 1,000 pages.

Inventory-limited sites remain explicit. If fewer than 500 unique candidates exist, the exact terminal manifest population is the Smart reference and the blind reference is the exact available unique FIFO population. The helper never invents pages to reach 500 or 1,000.

## Telemetry

The artifact reports:

- Standard, Smart, and blind page counts plus exact population fingerprints;
- pages saved by Smart relative to blind;
- Standard, Smart, blind, shared, blind-only, and Smart-only Fix fingerprint counts;
- Smart Fix coverage versus blind when the blind reference contains Fix evidence;
- incremental Smart Fix fingerprints and Fix yield per 100 pages beyond the unchanged Standard reference;
- optional high-impact Smart/blind/shared/blind-only Fix counts and Smart coverage versus blind.

Missing high-impact evidence remains `not_observed` with `None` metrics instead of being converted to zero. High-impact Fix identities must be part of the corresponding observed Fix population.

## Standard 150 and authority boundary

The manifest Standard reference remains the exact first tranche and cannot exceed 150 pages. Smart must preserve that population as an exact prefix. The helper selects no pages itself and cannot change Standard 150.

Every result hard-codes:

- `population_scope_complete=false`
- `production_budget_authorized=false`
- `site_fully_understood=false`

Fix fingerprints are treated only as opaque evidence identities. The helper assigns no severity, priority, repair order, authority, or production crawl entitlement.

## Integrity and regression coverage

`validate_manifest_bound_fix_benchmark(...)` deterministically rebuilds the artifact from the same manifest, discovery sequence, and Fix evidence, rejecting lineage, arithmetic, fingerprint, or authority-flag drift.

Focused regressions cover exact Smart-500/blind-1000 comparison, blind-only and Smart-only evidence, incremental Fix yield beyond Standard, unknown/high-impact evidence, 620-page and sub-500/sub-150 inventory limits, duplicate discovery identities, replay-integrity drift, same-count discovery transplantation, out-of-discovery Smart population tampering, JSON transport, authority/metric tampering, determinism, and input immutability.
