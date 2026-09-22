# Lane C — resolved canonical + contract-bound parity hardening

Branch: `agent/nextgen-browser-performance-20260921`  
Issue: #324  
Draft PR: #331

## Why this slice exists

The existing `nextgen_critical_content_parity_v1` comparator correctly preserves raw/render identity, failed renders, extractor absence and critical-field deltas, but two integration risks remained:

1. a document-relative canonical such as `/products/a` could compare unequal to the equivalent absolute rendered canonical `https://example.com/products/a`; and
2. the original aggregate coverage helper can bind parity rows to sampled URLs without independently re-running the full parity evidence contract, so a structurally forged completed dictionary could look complete if its top-level state/identity flags were plausible.

This slice closes both gaps without changing browser execution, provider calls, budgets, scoring, persistence, release or production.

## Additive contracts

`scanner-api/app/nextgen_browser_performance_parity_hardening.py` adds:

- `nextgen_critical_content_parity_v2_resolved`
- `nextgen_critical_content_parity_v2_resolved_integrity_v1`
- `nextgen_browser_parity_coverage_v2_contract_bound`
- canonical resolution marker `document_identity_v1`

`compare_critical_content_parity_resolved(...)` deep-copies the already-observed raw/rendered page dictionaries, resolves relative/protocol-relative canonical hrefs against each document identity, strips fragments through normalized absolute HTTP(S) identity, then delegates all other parity semantics to the existing v1 comparator. It does not mutate source observations.

`validate_resolved_critical_parity_contract(...)` checks the new envelope metadata and then re-validates the underlying result through `nextgen_browser_performance_integrity_v1`.

`summarize_resolved_critical_parity_coverage(...)` requires the representative sample contract and every resolved parity result contract to pass before completed coverage can be counted. Foreign and duplicate result binding remains fail-closed through the existing coverage helper. Failed render rows remain failed; selected pages with no result remain unassessed.

## Deterministic verification

The focused hermetic slice passed **10/10 in 0.07s** and the new source/test passed `py_compile`.

Covered regressions:

- relative canonical vs equivalent absolute canonical;
- protocol-relative canonical normalization;
- genuinely different resolved canonicals remain `material_delta`;
- raw/rendered input immutability;
- tampered resolution metadata fails contract validation;
- complete mixed matched/material-delta coverage;
- failed vs unassessed coverage separation;
- structurally forged completed parity rejected before counting;
- invalid representative sample contract rejected before counting;
- foreign parity URL remains fail-closed.

The exact full repository gate remains required before integration readiness.

## Integrator hook

For new NextGen browser evidence, prefer:

1. `compare_critical_content_parity_resolved(...)` after the existing safe browser path returns an already-observed rendered page;
2. `validate_resolved_critical_parity_contract(...)` for per-page trust;
3. `summarize_resolved_critical_parity_coverage(...)` over the original representative sample.

The existing v1 parity helpers remain available for compatibility. This lane does not wire either version into `run_scan` or customer scoring.

## Rollback

Delete this helper, its focused test and this note. No migration, persistence rewrite or production rollback is required.
