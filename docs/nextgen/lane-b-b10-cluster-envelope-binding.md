# Lane B — B10 near-duplicate cluster envelope binding

Checkpoint scope: Agent B only. This handoff does not authorize merge, deployment, release, production changes, customer Fix creation, repair-priority changes, authority/persistence writes, customer projection changes, admission changes, or `run_scan` wiring.

## What changed

The standalone `near_duplicate_cluster_evidence_v1_b10_bound` producer is now composed into the preferred Lane-B semantic-analysis and graph-envelope contracts.

### Semantic analysis v4

`semantic_analysis_bundle_v4_b10_cluster_bound` extends the existing cluster-profile-bound single-snapshot analysis without re-running the semantic adapter. It adds:

- `near_duplicate_cluster_evidence`;
- explicit B10 cluster coverage state;
- a pair-vs-cluster binding state and reason;
- a permanent `sitewide_near_duplicate_claim=false` guard.

The binder cross-checks the legacy B10 pair candidate producer against the B10 cluster producer whenever both are verified. `eligible_pages` must equal `eligible_page_count`, and the full pair producer `candidate_count` must equal cluster evidence `qualifying_pair_count`. A divergence fails the B10 binding closed instead of silently transporting contradictory evidence.

Missing verified B10 main-content evidence remains `not_verified`; it is not converted into a clean/no-duplicate conclusion. Partial B10 coverage remains explicitly partial.

### Graph envelope v8

`semantic_graph_evidence_v8_b10_cluster_bound` extends the v7 cluster-profile-bound envelope. It reuses v7's already-computed semantic analysis and binds B10 cluster evidence onto that result, so the caller-provided semantic vectorizer remains limited to the two integrity/repeatability calls owned by `semantic_vector_contract_v1`. B10 cluster composition cannot trigger an additional model/provider/vectorizer call.

The envelope exposes the B10 cluster evidence, binding state/reason, and B10 coverage state while retaining the existing no-sitewide-orphan, no-link-absence, no-semantic-coverage, and no-customer-Fix semantics. Incomplete B10 evidence does not invalidate independently verified graph/semantic evidence; consumers must inspect the B10-specific state before using duplication evidence.

## Tests

Added `scanner-api/tests/test_semantic_graph_near_duplicate_cluster_binding.py` with 8 focused regressions covering:

1. pair/cluster count binding on a complete verified B10 population;
2. no extra semantic-vectorizer invocation;
3. partial B10 population coverage;
4. missing B10 evidence remaining unknown/not verified;
5. fail-closed pair-vs-cluster count divergence;
6. input non-mutation at the binding boundary;
7. v8 full-envelope composition and no-sitewide/no-Fix guards;
8. duplicate page identity rejection before semantic-vectorizer execution.

This raises the expected Lane-B focused accounting from 160 to **168 tests across 22 semantic-graph test files**.

Syntax verification for the two new app modules and the focused test file passed with `python -m py_compile`. A supplementary hermetic composition harness passed 5 wrapper/binding checks. That harness is not a substitute for repository-native pytest.

The complete exact-head repository suite is not claimed green because this runtime cannot resolve `github.com` for a branch-native checkout and there is no pull-request GitHub Actions run for the current head at this checkpoint.

Exact integration gate:

```bash
cd scanner-api
pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph*.py tests/test_semantic_graph*.py
```

## Integrator guidance

Prefer `build_near_duplicate_cluster_bound_semantic_graph_evidence(...)` when the serialized integrator is ready to consume the full Lane-B evidence package. Treat `representative_url`, cluster membership, pair similarities, and chaining as descriptive assessed-sample evidence only. Do not directly convert them into canonical selection, customer Fixes, repair priority, persistence/authority decisions, or sitewide duplication claims.

If `near_duplicate_cluster_binding_state != "verified"`, do not infer a no-duplicate result. Preserve the B10-specific reason and coverage state as unknown evidence.
