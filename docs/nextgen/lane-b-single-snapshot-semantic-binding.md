# Agent B single-snapshot semantic analysis binding — 2026-09-22

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

This checkpoint stays entirely inside Agent B's ownership boundary from
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not modify
`run_scan`, global scan budgets, final repair priority/customer scoring,
authority/persistence, customer projection, admission, release, deployment,
worker configuration, credentials, or production behavior.

## Gap closed

The previous checkpoint bound contextual source-to-target opportunity scoring to
`semantic_vector_contract_v1`, but the other semantic analyzers remained separate
call sites. A stateful or buggy local adapter could therefore pass one deterministic
check and later return a different semantic snapshot to clustering or
cannibalization analysis if a consumer independently called those helpers.

`scanner-api/app/semantic_graph_analysis_bound.py` adds the versioned
`semantic_analysis_bundle_v1_vector_bound` composition boundary. A caller-provided
semantic adapter is now validated once with repeatability checking, and all
semantic-dependent analyzers consume only a sealed copy of that accepted snapshot.
The underlying adapter is never called after the two contract-verification calls.

The bundle:

- fails closed on duplicate assessed-page identities before adapter execution;
- rejects bool, NaN, infinity, and out-of-range thresholds before adapter execution;
- validates adapter version/population/vector shape/numeric bounds/repeatability via
  `semantic_vector_contract_v1`;
- uses the same sealed semantic snapshot for clustering, cannibalization candidates,
  and contextual source-to-target opportunity evidence;
- preserves B10 near-duplicate evidence independently when semantic vectors fail,
  but does not transport near-duplicate evidence when page identity itself is
  ambiguous;
- isolates graph-integrity failure to contextual-link opportunity evidence, so a
  malformed/foreign graph cannot invalidate otherwise valid cluster or
  cannibalization evidence;
- preserves assessed-sample scope, emits evidence only, and records
  `customer_fix_created=False`.

This is additive. Existing v1 helpers remain unchanged for historical/local
compatibility. The serialized integrator should prefer the single-snapshot bundle
when it later wires multiple semantic outputs from one adapter invocation boundary.

## Regressions

`scanner-api/tests/test_semantic_graph_analysis_bound.py` adds ten deterministic
regression cases covering:

1. one validated snapshot driving clustering, cannibalization, and contextual-link
   evidence;
2. a third-call-changing adapter proving the underlying adapter is invoked only
   twice for contract verification;
3. nondeterministic semantic vectors failing closed before semantic analyzers;
4. foreign vector population failing closed while independent near-duplicate
   evidence remains separately scoped;
5. graph population failure being isolated from valid cluster/cannibalization
   evidence;
6. duplicate page identity failing before adapter execution;
7. bool cluster threshold rejection;
8. NaN contextual threshold rejection;
9. below-minimum duplicate threshold rejection;
10. input page/graph non-mutation.

## Verification

A hermetic pure-composition harness using the exact new module/test bytes passed:

```text
PYTHONPATH=. pytest -q tests/test_semantic_graph_analysis_bound.py
10 passed in 0.09s

python -m py_compile \
  app/semantic_graph_analysis_bound.py \
  tests/test_semantic_graph_analysis_bound.py
PASS
```

The branch now contains an expected **58 focused Lane-B tests** across seven test
files. Do not claim the complete exact-head repository suite green until the
following branch-native gate executes:

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

This runtime still cannot resolve `github.com` from the container, so the exact-head
repository checkout/full branch-native suite remains externally blocked. The draft
PR targets the integration branch rather than `main`, and there is no normal
PR-triggered workflow run for this exact head. These remain verification blockers,
not implementation blockers.

## Integration handoff

After Agent A is accepted and Lane B reaches exact-head green verification, the
serialized integrator can consume
`vector_bound_semantic_analysis_evidence(...)` as the preferred semantic bundle.
It should preserve semantic-vector and graph-integrity states separately and must
not turn any candidate row into a final customer Fix without the existing
root-cause/priority/authority layers.

No merge or deployment is authorized from this lane.
