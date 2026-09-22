# Agent B vector-bound semantic graph envelope — 2026-09-22

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

This checkpoint stays inside the Agent-B ownership boundary defined by `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It adds only pure semantic-graph evidence composition, focused tests, and this handoff. It does not modify `run_scan`, global budgets, final repair priority/customer scoring, authority/persistence, customer projection, admission, release/deployment, worker configuration, credentials, schema, or production behavior.

## Gap closed

Lane B already had deterministic template/link-zone evidence, weighted assessed-page graph structures, B10-compatible near-duplicate evidence, cannibalization candidates, contextual source→target opportunity evidence, a versioned semantic-vector integrity contract, and a single-snapshot semantic analysis bundle.

One integration footgun remained: the original `build_semantic_graph_evidence(...)` predates the vector-integrity work and independently calls semantic analyzers. A caller supplying a pluggable/stateful local vectorizer could therefore bypass the newer one-snapshot boundary when asking for a complete Lane-B envelope.

## Implementation

New helper: `scanner-api/app/semantic_graph_evidence_bound.py`

Preferred entry point:

`build_vector_bound_semantic_graph_evidence(...)`

The helper:

- validates the bounded page/link inputs using the existing Lane-B limits;
- rejects duplicate assessed-page identities before caller-provided vectorizer code can run;
- builds deterministic template evidence locally;
- builds the weighted assessed-page internal-link graph locally;
- delegates all semantic-dependent clustering, cannibalization, and contextual link-opportunity evidence to `semantic_analysis_bundle_v1_vector_bound`;
- therefore executes a caller-provided semantic adapter only through `semantic_vector_contract_v1`, including population/shape/numeric/determinism/input-isolation checks;
- reuses one sealed accepted vector snapshot for every downstream semantic-dependent output;
- exposes a bounded `link_zone_summary_v1_graph_edge_bound` summary of the strongest zone retained per observed assessed directed graph edge;
- keeps `sitewide_orphan_claim=false`, `sitewide_link_absence_claim=false`, and `customer_fix_created=false` at the envelope boundary.

The link-zone summary is intentionally scoped. It is a summary of the graph's strongest retained zone for each observed assessed source→target edge, not a claim about all links on the site or every raw link occurrence.

## Focused regressions

New suite: `scanner-api/tests/test_semantic_graph_evidence_bound.py`

Seven focused cases cover:

1. complete template + graph + link-zone + semantic composition with a stable adapter;
2. proof that a stateful adapter is never called after the two contract-verification calls;
3. mutating-adapter fail-closed behavior while local template/graph evidence and caller input remain intact;
4. nondeterministic-adapter fail-closed behavior;
5. foreign semantic-vector population rejection;
6. duplicate page identity rejection before adapter execution;
7. strict threshold rejection before adapter execution.

Expected Lane-B focused total is now **69 tests across eight test files** (previously 62 across seven).

Local supplementary syntax verification passed for mirrors of the new module and new test suite with `python -m py_compile`. This is not a substitute for branch-native pytest.

## Required exact-head verification

The execution container still cannot resolve `github.com`, so an exact branch checkout is unavailable. The draft targets the NextGen integration branch rather than `main`, and no PR-triggered workflow currently substitutes for the branch-native gate. Do not claim 69/69 exact-head green until this runs from the committed head:

```text
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py \
  tests/test_semantic_graph_vector_contract.py \
  tests/test_semantic_graph_contextual_vector_bound.py \
  tests/test_semantic_graph_analysis_bound.py \
  tests/test_semantic_graph_evidence_bound.py

python -m py_compile \
  app/semantic_graph.py \
  app/semantic_graph_html.py \
  app/semantic_graph_contextual.py \
  app/semantic_graph_vector_contract.py \
  app/semantic_graph_contextual_vector_bound.py \
  app/semantic_graph_analysis_bound.py \
  app/semantic_graph_evidence_bound.py \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py \
  tests/test_semantic_graph_vector_contract.py \
  tests/test_semantic_graph_contextual_vector_bound.py \
  tests/test_semantic_graph_analysis_bound.py \
  tests/test_semantic_graph_evidence_bound.py
```

## Integration handoff

The serialized integrator should prefer `build_vector_bound_semantic_graph_evidence(...)` over the legacy complete-envelope helper when Lane B is transplanted after Agent A. Feed the returned candidate evidence into the existing root-cause/priority architecture; do not translate it directly into customer Fixes inside Lane B.

Preserve these boundaries independently:

- template evidence is deterministic local classification evidence, not page identity;
- B10 near-duplicate evidence remains tied only to verified hashed main-content shingles, never common template/navigation similarity;
- graph/link evidence remains assessed-sample scoped and must not become a sitewide orphan or absence claim;
- semantic adapter evidence must retain semantic-vector integrity, determinism and input-isolation provenance;
- B20 grouping/final repair decisions remain integrator-owned and must use the existing explicit root-cause evidence contracts.

Rollback is trivial: the new helper is additive and has no production wiring. Omitting it leaves existing behavior unchanged.

No merge or deployment is authorized from this lane.
