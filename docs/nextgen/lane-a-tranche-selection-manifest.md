# Lane A — deterministic tranche selection manifest

Issue: #322  
Draft PR: #328  
Branch: `agent/nextgen-adaptive-crawl-20260921`

## Why this checkpoint exists

Lane A already has deterministic adaptive selection, per-selection replay traces, tranche planning, marginal-yield telemetry, and Smart-500-vs-blind-1,000 benchmark evidence. One missing integrity bridge was an explicit artifact proving that the 150, 500, and 1,000 selection populations used by those later measurements are exact nested populations from the same discovered input and metadata snapshot.

`scanner-api/app/adaptive_tranche_manifest.py` adds that bridge without creating a new selector. It delegates every population to the existing `select_adaptive_urls(...)` helper and every target plan to `plan_tranche_targets(...)`.

## Versioned contract

`adaptive_tranche_selection_manifest_v1` records:

- the exact ordered discovered-input fingerprint and exact-unique count;
- the existing planner targets and the selection targets used for the manifest;
- an exact Standard-150 reference fingerprint selected by the existing selector;
- per-tranche selected URLs and deterministic population fingerprints;
- exact incremental URLs added by each post-150 tranche;
- prefix-nesting checks for every transition at or above Standard 150;
- explicit tranche roles for Standard reference, Smart-500 candidate, blind-1,000 reference, inventory bound, and optional intermediate targets;
- truthful inventory-limited state when exact duplicate discovery identities or bounded inventory prevent a target from being filled.

The manifest ignores pre-150 custom targets as adaptive-prefix anchors once at least 150 pages are assessable. This is intentional: Standard-150 compatibility is the fixed baseline, and smaller quota-based sampler runs are not assumed to be prefixes of the 150-page sampler.

## Standard 150 preservation

The helper never reimplements Standard 150. It directly calls `select_adaptive_urls(...)` at the bounded Standard reference target and requires the first manifest tranche to equal that result exactly. For deeper tranches, the full previous selected population must remain an exact prefix. Any divergence raises instead of transporting misleading marginal evidence.

## Integrity boundary

`validate_adaptive_tranche_selection_manifest(...)` rebuilds the complete artifact from the caller-supplied discovered population, family/path classifiers, metadata, targets, and ceiling. It rejects population-fingerprint drift, target drift, selected/added population tampering, discovery-order or metadata drift, malformed input identities, and forged completeness/budget authority.

Every artifact hard-codes:

- `population_scope_complete=false`;
- `production_budget_authorized=false`;
- `site_fully_understood=false`.

The SHA-256 population fingerprints are deterministic integrity identifiers only; they are not signatures or durable authority.

## Intended handoff

The serialized integrator may later use this artifact in an off-by-default shadow experiment as the common population identity for:

1. Standard-150 baseline evidence;
2. Smart-500 marginal-yield evidence;
3. blind-1,000 reference evidence;
4. the existing finding/priority benchmark bundle and marginal corpus.

The lane helper itself must never schedule pages, mutate `run_scan`, change a global budget, write authority/persistence, compose repair priority, project customer state, alter admission, or participate in release/deployment.

## Verification in this run

A hermetic pure-function package exercised the exact new helper/test bytes and passed **20/20** focused scenarios plus `py_compile`. Coverage includes default 150→500→1000 nesting, exact Standard-150 preservation, exact incremental populations, inventory-limited sites, sub-150 inventories, hard 1,000-page ceiling, optional 300/750 tranches, pre-150 custom targets, duplicate discovery identities, deterministic replay, JSON-like transport, selected/added population tampering, discovery-order drift, forbidden authority claims, malformed identities, and input immutability.

The complete branch-native Lane-A suite is still required from a full checkout. The execution shell cannot resolve `github.com`, so this run does not claim the repository-native total green.

Exact focused commands once a checkout is available:

```text
cd scanner-api
PYTHONPATH=. pytest -q tests/test_adaptive_tranche_manifest.py
PYTHONPATH=. python -m py_compile \
  app/adaptive_tranche_manifest.py \
  tests/test_adaptive_tranche_manifest.py
```

No merge or deployment is part of this checkpoint.
