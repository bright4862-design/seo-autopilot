# Agent B semantic-vector input isolation — 2026-09-22

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

This checkpoint remains inside the Agent-B ownership boundary from `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It changes only semantic evidence helpers/tests/docs. It does not modify `run_scan`, global budgets, final repair priority/customer scoring, authority/persistence, customer projection, admission, release/deployment, worker configuration, credentials, schema, or production behavior.

## Gap closed

The prior `semantic_vector_contract_v1` validated adapter identity, vector population/shape/numeric bounds, and repeatability, but it passed caller-owned `pages` directly into pluggable `vectorizer.vectors(...)` calls. A buggy or malicious local adapter could mutate page evidence while still returning deterministic vectors. In the single-snapshot bundle, those mutated page objects could then be consumed by clustering/cannibalization/contextual analyzers, contaminating evidence even though the vector output itself had passed contract checks.

## Implementation

`scanner-api/app/semantic_graph_vector_contract.py` now executes every adapter invocation against a deep-copied page snapshot. It also keeps a second baseline copy and fails closed with `vectorizer_input_mutation` if the adapter mutates its private snapshot before returning. The first and determinism-verification calls each receive fresh equivalent snapshots. Caller-owned pages are never handed to the delegate.

The contract now emits `input_isolation_enforced: true`. `ValidatedSemanticVectorizer` inherits the same behavior and raises `SemanticVectorContractError("vectorizer_input_mutation")` for mutating delegates.

`scanner-api/app/semantic_graph_analysis_bound.py` propagates this provenance as `semantic_vector_input_isolation_enforced`. A mutating adapter now fails before any semantic-dependent cluster, cannibalization, or contextual-link evidence is accepted. Independent B10 near-duplicate evidence remains separate, as before.

This is a fail-closed integrity hardening of the existing Lane-B contract. No customer Fix is created and no network/model/provider work is introduced.

## Regressions

Four focused regression cases were added across the existing vector-contract and single-snapshot bundle suites:

1. an adapter mutating the first invocation fails with `vectorizer_input_mutation` and cannot mutate caller pages;
2. mutation only on the second determinism invocation also fails closed while caller pages remain unchanged;
3. `ValidatedSemanticVectorizer` raises the reasoned mutation error and preserves caller input;
4. the single-snapshot semantic-analysis bundle rejects a mutating adapter before semantic-dependent analyzers and exposes the input-isolation provenance bit.

Expected Lane-B focused total is now **62 tests across the existing seven test files** (previously 58).

A local algorithmic harness reproducing the exact isolation logic passed valid deterministic, first-call mutation, second-call mutation, nondeterminism, and caller-input-preservation assertions. That harness is supplementary only; it does not replace branch-native pytest.

## Exact-head verification blocker

The runtime still cannot clone `github.com` (`Could not resolve host: github.com`), and this draft targets the NextGen integration branch rather than `main`, so the usual PR workflow is not available as a substitute. Do **not** claim 62/62 exact-head green until this branch-native gate executes:

```text
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py \
  tests/test_semantic_graph_vector_contract.py \
  tests/test_semantic_graph_contextual_vector_bound.py \
  tests/test_semantic_graph_analysis_bound.py

python -m py_compile \
  app/semantic_graph.py \
  app/semantic_graph_html.py \
  app/semantic_graph_contextual.py \
  app/semantic_graph_vector_contract.py \
  app/semantic_graph_contextual_vector_bound.py \
  app/semantic_graph_analysis_bound.py \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py \
  tests/test_semantic_graph_vector_contract.py \
  tests/test_semantic_graph_contextual_vector_bound.py \
  tests/test_semantic_graph_analysis_bound.py
```

## Integration handoff

When Lane B is eventually transplanted after Lane A and exact-head verification is green, the serialized integrator should prefer `vector_bound_semantic_analysis_evidence(...)` for multi-output semantic analysis. Preserve both semantic-vector integrity and `semantic_vector_input_isolation_enforced`; do not accept semantic adapter output as trusted evidence if the adapter mutates its input snapshot.

No merge or deployment is authorized from this lane.
