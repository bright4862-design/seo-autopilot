# Lane B handoff — semantic URL identity normalization

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

Code/test checkpoint before this handoff: `d901e9ccaf62d6954782bf391924eb8a41cbb1a8`

## Scope

This checkpoint remains entirely inside the Agent-B ownership boundary defined in
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not modify
`run_scan`, global budgets, final repair priority/customer Fix generation,
authority/persistence, customer projection, admission, release/deployment,
worker configuration, credentials, or production behavior.

## Correctness issue closed

Independent review identified a page-identity mismatch between two Lane-B
boundaries:

- graph/contextual identity used `semantic_graph._url()`, which collapses internal
  whitespace via the shared `_text()` normalizer;
- `semantic_vector_contract_v1` used a private `_page_url()` that only stripped
  leading/trailing whitespace.

A page such as `https://e.test/a   b` could therefore be accepted by graph
validation as `https://e.test/a b` while the semantic vector contract accepted a
vector keyed by the uncollapsed string. The contract could report semantic-vector
integrity as verified even though a downstream semantic consumer later rejected
that sealed vector population.

## Change

`scanner-api/app/semantic_graph_vector_contract.py` now reuses the existing
`semantic_graph._url()` normalizer inside `_page_url()`.

That gives page identity one normalization rule across:

- assessed-page population validation;
- semantic-vector population validation;
- sealed semantic clustering;
- cannibalization candidate analysis;
- contextual source-to-target opportunity analysis; and
- weighted-graph population checks.

The vector contract still fails closed on foreign or ambiguous adapter keys. It
does not silently rewrite vectorizer output keys; a pluggable adapter must return
keys matching the shared normalized assessed-page identity.

## Regressions added

Two focused regressions were added:

1. `test_page_identity_uses_shared_internal_whitespace_normalization` in
   `tests/test_semantic_graph_vector_contract.py` verifies that an assessed URL
   containing repeated internal whitespace is represented by the shared normalized
   identity and receives complete semantic-vector coverage.
2. `test_internal_whitespace_uses_one_identity_across_all_semantic_consumers` in
   `tests/test_semantic_graph_analysis_bound.py` verifies the same normalized URL
   survives vector validation, semantic clustering, cannibalization analysis and
   contextual source→target opportunity analysis without contradictory integrity
   states.

The expected Lane-B focused total is now **126 tests across 18 focused test
files** (124 prior + 2 new regressions).

## Verification performed in this runtime

A local hermetic normalization harness passed for:

- repeated internal whitespace collapsing to one shared page identity;
- vector population matching that normalized assessed population; and
- two page inputs that differ only by the collapsible whitespace normalizing to
  the same identity, which is the fail-closed basis for duplicate detection.

The exact repository-native 126-test gate is **not claimed green**. The execution
runtime still cannot clone `github.com`, and no GitHub Actions workflow run exists
for code/test checkpoint `d901e9ccaf62d6954782bf391924eb8a41cbb1a8`.

Required exact-head gate after checkout becomes available:

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
  tests/test_semantic_graph_evidence_bound.py \
  tests/test_semantic_graph_evidence_bound_identity.py \
  tests/test_semantic_graph_template_flow.py \
  tests/test_semantic_graph_evidence_bound_template_flow.py \
  tests/test_semantic_graph_template_opportunity.py \
  tests/test_semantic_graph_evidence_bound_template_opportunity.py \
  tests/test_semantic_graph_zone_profile.py \
  tests/test_semantic_graph_evidence_bound_zone_profile.py \
  tests/test_semantic_graph_coverage.py \
  tests/test_semantic_graph_vector_coverage_binding.py \
  tests/test_semantic_graph_evidence_bound_semantic_coverage.py

python -m py_compile \
  app/semantic_graph.py \
  app/semantic_graph_html.py \
  app/semantic_graph_contextual.py \
  app/semantic_graph_vector_contract.py \
  app/semantic_graph_contextual_vector_bound.py \
  app/semantic_graph_analysis_bound.py \
  app/semantic_graph_template_flow.py \
  app/semantic_graph_template_opportunity.py \
  app/semantic_graph_zone_profile.py \
  app/semantic_graph_coverage.py \
  app/semantic_graph_evidence_bound.py
```

## Integration handoff

The serialized integrator should preserve this single URL-identity normalizer when
Lane B is transplanted. Do not introduce a second page-identity normalization rule
between the graph, semantic-vector, template, or opportunity boundaries.

This checkpoint remains evidence-only. It creates no final customer Fix and makes
no new sitewide absence/orphan claims.

No merge or deployment is authorized from this lane.
