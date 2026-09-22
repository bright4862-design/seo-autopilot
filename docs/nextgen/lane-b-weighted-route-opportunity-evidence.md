# Lane B handoff — weighted assessed-route opportunity evidence

## Scope

This checkpoint stays entirely inside the Agent B ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

It adds deterministic weighted-route evidence to already-produced source→target contextual internal-link candidates. It does **not** create customer Fixes, set repair priority, write authority/persistence, modify customer projection, touch `run_scan`, alter admission/workers/schema/credentials, or change release/deployment/production behavior.

## New evidence contract

`scanner-api/app/semantic_graph_opportunity_weighted_route.py` adds:

- `template_contextual_internal_link_opportunity_v4_weighted_route_bound`
- deterministic widest-path evidence over the already-validated weighted assessed-page graph
- max-bottleneck route selection, where route strength is the minimum edge weight on the path
- deterministic tie-breaking: larger bottleneck, then fewer hops, then lexicographically smaller full URL path
- observed widest-route hop count and bottleneck weight
- mean observed edge weight along the selected route
- extra hops versus the independently recomputed shortest directed route
- deterministic bottleneck-edge evidence with source, target, strongest link zone and weight
- per-zone edge counts along the selected widest route
- bounded route URL samples that preserve both source and target endpoints
- explicit disclosure when the upstream contextual-candidate sample is truncated

The helper validates the transported v3 graph-neighborhood candidate evidence before use, then independently validates the weighted graph. It recomputes forward and reverse shortest-path hop counts and fails closed if transported neighborhood measurements disagree with the graph. Forged graph node counts or weighted metrics continue to fail through the shared graph-integrity boundary.

A missing assessed route remains `no_observed_route_in_assessed_graph`; it is never promoted into a sitewide orphan, reachability, or link-absence claim. Weighted-route evidence is descriptive evidence only and `customer_fix_created` remains false.

## Preferred additive envelope

`scanner-api/app/semantic_graph_evidence_weighted_route_bound.py` adds:

- `semantic_graph_evidence_v13_weighted_route_opportunity_bound`

v13 extends the existing v12 money-page-reachability envelope. It consumes only the already-built graph and already-produced v3 graph-neighborhood contextual opportunity evidence, so it adds **no semantic vectorizer/model/provider invocation**. The existing two-call semantic adapter determinism/input-isolation boundary is preserved.

A weighted-route integrity failure fails the v13 envelope closed. An independently existing v12 failure, such as an invalid trusted seed identity, remains authoritative even if the weighted contextual-route evidence itself is still descriptive and internally verified.

## Focused regressions

Two new test files add **14 focused regressions**:

- `scanner-api/tests/test_semantic_graph_opportunity_weighted_route.py` — 11 tests
- `scanner-api/tests/test_semantic_graph_weighted_route_binding.py` — 3 tests

Coverage includes:

- choosing a stronger three-hop contextual route over a weaker two-hop navigation route
- deterministic fewer-hop and lexicographic tie-breaking
- existing non-contextual direct-edge upgrades
- sample-scoped no-route evidence
- forged shortest-path measurement rejection
- forged route-state rejection
- forged graph weighted-metric rejection
- candidate-truncation disclosure
- input non-mutation
- bounded long-route samples retaining both endpoints
- verified zero-candidate behavior
- v13 envelope composition without a third semantic-vectorizer call
- no-semantic-candidate composition
- preservation of an underlying v12 seed-integrity failure

Based on the preceding Lane-B checkpoint of 219 focused tests across 30 semantic-graph test files, the expected Lane-B accounting is now **233 tests across 32 `test_semantic_graph*.py` files**.

Syntax compilation was checked for the new helper, envelope and focused test sources. A hermetic widest-path algorithm harness passed **7/7** cases, and supplementary helper-shape/integrity checks passed **4/4**. These checks do not replace the exact-head repository-native pytest gate.

The exact integration gate remains:

```bash
cd scanner-api
python -m pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph*.py tests/test_semantic_graph*.py
```

Do not claim the full 233-test exact-head suite green until those commands or equivalent exact-head CI actually pass.

## Integrator guidance

When the serialized integrator is ready to consume Lane B, prefer `build_weighted_route_bound_semantic_graph_evidence(...)` as the additive full evidence envelope. Treat route strength, selected path, bottleneck edge, link-zone composition, semantic similarity, template evidence, cluster evidence, cannibalization/near-duplicate candidates, money-page reachability, and source→target opportunities as descriptive assessed-sample evidence only.

Do not convert widest-route evidence directly into a customer Fix, final repair priority, authority/persistence decision, customer projection, admission decision, release gate, deployment action, or production behavior. Preserve upstream truncation and sample-scope fields so a displayed candidate sample is never represented as complete when it is not.

No merge or deployment is authorized from this lane.
