# Lane B handoff — weighted semantic-cluster link flow

## Scope

This checkpoint remains entirely inside the Agent-B ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

It binds the already-produced weighted assessed-page graph to the already-validated deterministic semantic-cluster profile. It does **not** create customer Fixes, alter final priority/ranking, write authority/persistence, modify customer projection, touch `run_scan`, change admission, release, deployment, or production behavior.

## New evidence contract

`scanner-api/app/semantic_graph_cluster_link_flow.py` adds:

- `semantic_cluster_link_flow_v1_weighted_graph_bound`
- deterministic collapse of page-level directed graph edges into semantic-cluster→semantic-cluster flows
- explicit intra-cluster vs inter-cluster edge counts
- full graph-edge count, clustered-endpoint edge count, and unclustered-endpoint edge count
- directed per-flow edge count, repeated occurrence count, weighted strength, occurrence-weighted strength, min/mean/max edge weight, strongest edge, strongest-zone edge counts, and bounded deterministic edge samples
- per-cluster observed internal weighted strength plus directional cross-cluster inbound/outbound edge, weight, and neighboring-cluster counts
- explicit semantic-vector coverage and pair-population completeness transport from the cluster profile

The helper independently validates the weighted graph before aggregation: graph version/scope, duplicate nodes/edges, endpoint population, non-negative finite weights, zone confidence, strongest-zone identity, edge occurrence counts, node in/out counts, and node weighted in/out totals. It separately validates cluster profile counts, membership, representative identity, overlapping membership, state consistency, and requires every clustered URL to exist in the assessed graph.

`no_cluster_observed` and `no_cluster_flow_observed` remain assessed-sample evidence only. Missing cluster flow is never promoted into a sitewide link-absence, orphan, reachability, semantic coverage, or distribution claim.

The graph stores only the strongest observed zone on each reduced directed edge. Accordingly `strongest_zone_edge_counts` describes reduced graph-edge strongest zones; it is deliberately not presented as a raw link-occurrence zone distribution. The richer raw-zone occurrence evidence remains owned by the existing template-zone-flow contracts.

## Preferred additive envelope

`scanner-api/app/semantic_graph_evidence_cluster_flow_bound.py` adds:

- `semantic_graph_evidence_v15_semantic_cluster_link_flow_bound`

v15 extends the v14 cluster-context opportunity envelope. It reuses the graph and semantic-cluster profile already produced upstream, so it adds **no semantic vectorizer/model/provider invocation** and preserves the existing adapter determinism/input-isolation boundary.

If cluster-flow integrity fails, v15 fails closed. If v14 is already `not_verified`, its existing failure reason remains authoritative.

## Focused regressions

Two new test files add **15 focused regressions**:

- `scanner-api/tests/test_semantic_graph_cluster_link_flow.py` — 12 tests
- `scanner-api/tests/test_semantic_graph_cluster_flow_binding.py` — 3 tests

Coverage includes weighted intra/inter-cluster collapse, occurrence counts, directional cluster summaries, unclustered endpoint accounting, no-cluster/no-flow states, forged node metrics, duplicate graph edges, cluster members outside the graph, overlapping membership, partial cluster profiles, deterministic ordering/tie-breaking, v15 composition, cluster-flow fail-closed behavior, and preservation of an upstream v14 failure.

Based on the preceding Lane-B checkpoint of 247 focused tests across 34 semantic-graph test files, expected Lane-B accounting is now **262 tests across 36 `test_semantic_graph*.py` files**.

Available verification for this slice:

- isolated hermetic run of the exact new helper/wrapper logic: **15/15 passed**;
- `python -m py_compile` for both new application modules and both new test files: PASS.

The full exact-head repository suite is not claimed green until the branch-native gate runs:

```bash
cd scanner-api
python -m pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph*.py tests/test_semantic_graph*.py
```

## Integrator guidance

When the serialized integrator is ready to consume Lane B, prefer `build_cluster_flow_bound_semantic_graph_evidence(...)` as the newest additive evidence envelope. Treat cluster-flow strengths, cluster neighborhood counts, cluster relation, weighted routes, template/link-zone evidence, semantic similarity, cannibalization/near-duplicate candidates, money-page reachability, and source→target opportunities as descriptive assessed-sample evidence only.

Do not convert cluster-flow strength or missing flow directly into a customer Fix, final priority, canonical choice, authority/persistence decision, projection, admission decision, release gate, deployment action, or production behavior.

No merge or deployment is authorized from this lane.
