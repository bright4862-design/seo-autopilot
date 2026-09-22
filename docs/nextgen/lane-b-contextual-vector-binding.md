# Agent B contextual vector binding — 2026-09-22

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

This checkpoint remains entirely inside Agent B's ownership boundary from
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not modify
`run_scan`, global scan budgets, final repair priority/customer scoring,
authority/persistence, customer projection, admission, release, deployment,
worker configuration, credentials, or production behavior.

## Gap closed

The previous Lane-B checkpoints added two separate integrity boundaries:

1. `contextual_internal_link_opportunity_v1` validates the assessed graph
   population and recomputes graph node metrics from the observed edge set before
   graph evidence can influence source-to-target opportunity scoring.
2. `semantic_vector_contract_v1` validates local/pluggable vectorizer identity,
   population, sparse-vector shape, numeric bounds, and deterministic
   repeatability.

Those contracts were individually useful, but the contextual opportunity helper
still accepted a caller-supplied `SemanticVectorizer` directly. A consumer could
therefore invoke contextual opportunity scoring with malformed, foreign-population,
or nondeterministic semantic vectors without first applying the semantic-vector
contract.

## Added versioned evidence boundary

`scanner-api/app/semantic_graph_contextual_vector_bound.py` adds
`contextual_internal_link_opportunity_v2_vector_bound`.

The helper:

- validates page and graph identity/integrity before executing caller-provided
  vectorizer code;
- validates the semantic adapter with `semantic_vector_contract_v1`, including a
  second invocation that must produce the same canonical vectors;
- fails closed to `not_verified` when vector evidence is malformed, foreign to
  the assessed population, numerically invalid, zero-norm, execution-failing, or
  nondeterministic;
- never sends those unverified vectors into opportunity scoring;
- seals a copy of the already-validated vector snapshot and delegates contextual
  opportunity analysis against that snapshot, so the underlying vectorizer is not
  called a third time after determinism verification;
- exposes graph-integrity and semantic-vector-integrity states separately;
- preserves assessed-sample scope and `sitewide_link_absence_claim=False`;
- emits evidence only and explicitly records `customer_fix_created=False`.

This is additive. The existing v1 helper remains unchanged for historical/local
compatibility. The serialized integrator should prefer the v2 vector-bound helper
if Lane B is later transplanted into the NextGen integration branch.

## Regressions

`scanner-api/tests/test_semantic_graph_contextual_vector_bound.py` adds seven
deterministic regressions covering:

1. valid deterministic vectors producing bound contextual opportunities;
2. foreign vector URL population failing closed;
3. boolean vector weights failing closed rather than being treated as numeric;
4. nondeterministic vector output failing closed;
5. a vectorizer that changes on a third invocation proving that the downstream
   analyzer uses the sealed validated snapshot and never re-queries the adapter;
6. invalid graph evidence failing before caller vectorizer execution;
7. helper non-mutation of page and graph inputs.

## Verification

A hermetic pure-function harness using the exact new module/test bytes passed:

```text
PYTHONPATH=. pytest -q tests/test_semantic_graph_contextual_vector_bound.py
7 passed in 0.07s

python -m py_compile \
  app/semantic_graph_contextual_vector_bound.py \
  tests/test_semantic_graph_contextual_vector_bound.py
PASS
```

The runtime emitted an unrelated spreadsheet-runtime warmup warning after Python
startup; pytest and `py_compile` both exited 0.

The branch now contains an expected **48 focused Lane-B tests** across six test
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
  tests/test_semantic_graph_contextual_vector_bound.py

python -m py_compile \
  app/semantic_graph.py \
  app/semantic_graph_html.py \
  app/semantic_graph_contextual.py \
  app/semantic_graph_vector_contract.py \
  app/semantic_graph_contextual_vector_bound.py \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py \
  tests/test_semantic_graph_vector_contract.py \
  tests/test_semantic_graph_contextual_vector_bound.py
```

The current automation runtime still cannot clone the repository because outbound
DNS cannot resolve `github.com`, and this integration-target draft has no normal
PR-triggered repository CI run. That remains the exact-head verification blocker.

## Integration handoff

After Agent A is accepted and Lane B reaches exact-head green verification, the
serialized integrator can select
`vector_bound_contextual_internal_link_opportunities(...)` for contextual
source-to-target evidence. Consumers should preserve both
`graph_integrity_state` and `semantic_vector_integrity_state`; a candidate is not
verified semantic evidence unless both boundaries are verified.

No merge or deployment is authorized from this lane.
