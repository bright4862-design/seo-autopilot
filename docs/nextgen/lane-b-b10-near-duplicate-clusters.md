# Lane B — B10-bound near-duplicate cluster evidence

## Scope

This checkpoint stays entirely inside the NextGen Agent B Semantic Graph lane on `agent/nextgen-semantic-graph-20260921`. The authoritative ownership boundary remains `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`, which is read-only from this lane.

No customer Fix is created and no `run_scan`, global budget, final repair priority, authority/persistence, customer projection, admission, release/deployment, worker, schema, credential, or production surface is modified.

## Gap closed

The Lane-B foundation already emitted bounded B10-compatible near-duplicate **pair candidates**. Issue #323 also calls for near-duplicate clusters. Pair candidates alone do not describe transitive connected components, and a connected component can contain members whose direct pair similarity is below the threshold because A≈B and B≈C does not imply A≈C.

`scanner-api/app/semantic_graph_near_duplicate_clusters.py` adds the versioned `near_duplicate_cluster_evidence_v1_b10_bound` contract. It consumes only already-retained pages whose main-content evidence is explicitly verified as `sha256_5_token_shingles_v1`.

## Evidence semantics

The helper:

- performs no network, browser, model, embedding-provider, persistence, or customer-output work;
- uses deterministic Jaccard similarity over verified B10 main-content shingle sets;
- creates threshold-qualified connected components with deterministic IDs;
- reports full qualifying-pair count and `pair_scan_complete=true` for the eligible assessed population;
- emits a deterministic representative URL chosen by highest mean within-cluster similarity with URL tie-break;
- emits min/mean/max pair similarity plus deterministic strongest/weakest pair evidence;
- explicitly marks `chaining_observed=true` when a connected component contains a member pair below the threshold;
- distinguishes complete, partial, and not-verified B10 coverage;
- fails closed on duplicate assessed-page identity instead of silently collapsing it;
- bounds emitted clusters to 250 rows while retaining the full cluster count and truncation flag;
- keeps `sitewide_near_duplicate_claim=false`, `sitewide_coverage_claim=false`, and `customer_fix_created=false` in every output.

The representative is descriptive cluster evidence only. It is not a canonical-page choice, deletion/merge recommendation, repair priority, or final customer Fix.

## Focused regressions

`scanner-api/tests/test_semantic_graph_near_duplicate_clusters.py` adds 12 focused tests covering:

1. transitive cluster construction and chaining disclosure;
2. complete verified sample with no candidate;
3. partial B10 coverage without a sitewide claim;
4. duplicate page identity fail-closed behavior;
5. no verified B10 content returning `not_verified` rather than a false clean result;
6. deterministic representative selection and URL tie-break;
7. deterministic output across page input order;
8. input non-mutation; and
9. four invalid threshold boundary/type cases.

Local hermetic verification for the exact new module/test contents passed:

```bash
pytest -q tests/test_semantic_graph_near_duplicate_clusters.py
# 12 passed

python -m py_compile \
  app/semantic_graph_near_duplicate_clusters.py \
  tests/test_semantic_graph_near_duplicate_clusters.py
# PASS
```

Based on the preceding Lane-B checkpoint of 148 focused tests across 20 semantic-graph test files, the expected focused total is now **160 tests across 21 test files**.

The complete exact-head Lane-B repository suite is not claimed green until the branch-native gate runs:

```bash
cd scanner-api
pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph*.py tests/test_semantic_graph*.py
```

## Integrator handoff

The serialized integrator may later consume `near_duplicate_cluster_evidence(...)` alongside the existing pair-level near-duplicate and cannibalization evidence. Preserve its B10-only provenance, assessed-sample coverage state, chaining disclosure, truncation flag, and no-sitewide-claim semantics.

Do not map `representative_url` directly to canonicalization or customer repair. Any root-cause grouping, final repair identity, priority, persistence, customer projection, or authority decision remains integrator-owned.

No merge or deployment is authorized from this lane.
