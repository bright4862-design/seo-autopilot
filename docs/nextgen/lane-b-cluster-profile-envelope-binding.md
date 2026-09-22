# Lane B — same-snapshot cluster-profile envelope binding

## Scope

This checkpoint stays entirely inside the NextGen Agent B Semantic Graph lane. It does not create customer Fixes and does not touch `run_scan`, final repair priority, authority/persistence, customer projection, admission, release/deployment, or production.

The authoritative ownership boundary remains `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`; that file is read-only from this lane.

## New evidence contracts

### `semantic_analysis_bundle_v3_cluster_profile_bound`

`scanner-api/app/semantic_graph_analysis_profile_bound.py` extends the existing single-snapshot semantic-analysis boundary with `semantic_cluster_profile_v1_vector_bound` evidence.

Key guarantees:

- A caller-provided semantic vectorizer is invoked only by `semantic_vector_contract_v1`.
- With determinism verification enabled, the adapter is invoked at most twice: the accepted call plus the repeatability call.
- Semantic clusters, cannibalization candidates, contextual source-to-target internal-link opportunities, and semantic-cluster profiles all consume the same sealed accepted vector snapshot.
- Cluster profiling never triggers a third adapter/provider/model invocation.
- Invalid page identity or semantic-vector integrity fails profile evidence closed.
- Partial vector population coverage remains explicitly subset-scoped; it is never promoted to sitewide semantic coverage.
- B10 near-duplicate evidence remains independent because it is based on verified main-content shingles, not semantic vectors.
- `representative_url` and centroid terms remain descriptive evidence only. They are not canonical-page recommendations, repair priority, or customer Fixes.

The prior `semantic_analysis_bundle_v2_semantic_coverage_bound` implementation is left unchanged for compatibility.

### `semantic_graph_evidence_v7_cluster_profile_bound`

`scanner-api/app/semantic_graph_evidence_cluster_profile_bound.py` composes the v3 semantic analysis into the existing Lane-B graph evidence shape while retaining:

- template evidence;
- weighted assessed-page internal-link graph evidence;
- strongest-zone summaries and raw link-zone observation profiles;
- observed template-to-template link flow;
- semantic clusters;
- near-duplicate and cannibalization candidates;
- contextual source-to-target link opportunities;
- template-bound contextual opportunity evidence; and
- explicit page-identity / semantic-vector coverage state.

The v7 envelope exposes `semantic_cluster_profile` and `semantic_cluster_profile_version` directly. A partial semantic-vector population keeps the envelope `partial`; invalid semantic/profile evidence fails closed. Clean `no_cluster_observed` profile evidence remains descriptive and does not prevent an otherwise verified envelope.

Every sitewide absence/distribution/coverage flag remains false, and `customer_fix_created` remains false.

The prior `semantic_graph_evidence_v6_semantic_coverage_bound` implementation is left unchanged for compatibility.

## Focused regressions

`scanner-api/tests/test_semantic_graph_cluster_profile_binding.py` adds 8 behavioral regressions covering:

1. same-snapshot profile generation with exactly two adapter calls;
2. a stateful adapter that would change on a third call, proving no third call occurs;
3. nondeterministic adapter fail-closed profile behavior;
4. partial semantic-vector population with subset-scoped cluster profiles;
5. page/graph input non-mutation;
6. v7 envelope profile exposure plus non-sitewide/non-Fix guards;
7. v7 partial-coverage state preservation; and
8. duplicate assessed-page identity rejection before adapter execution.

Based on the preceding Lane-B checkpoint (136 focused tests across 19 files), this raises the expected focused Lane-B total to **144 tests across 20 files**.

## Verification

A local syntax/bytecode compile check passed for the exact three newly-authored files:

```bash
python -m py_compile \
  scanner-api/app/semantic_graph_analysis_profile_bound.py \
  scanner-api/app/semantic_graph_evidence_cluster_profile_bound.py \
  scanner-api/tests/test_semantic_graph_cluster_profile_binding.py
```

The current execution container cannot resolve `github.com`, so a branch-native checkout and exact-head pytest run are not available from this environment. Do not treat the compile check as a substitute for repository-native regression execution.

Integration gate for the lane head:

```bash
cd scanner-api
pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph*.py tests/test_semantic_graph*.py
```

Expected focused accounting: **144 tests / 20 Lane-B semantic-graph test files**. Only claim exact-head green after the repository-native command or an exact-head CI run actually passes.

## Integrator handoff

Prefer `build_cluster_profile_bound_semantic_graph_evidence` when the integrator needs cluster-profile evidence. Treat all output as bounded evidence only. Do not convert cluster representatives, centroid terms, candidate pairs, template flow, or link-zone observations directly into final customer Fixes or repair priority without the serialized integrator's separate authority and acceptance logic.
