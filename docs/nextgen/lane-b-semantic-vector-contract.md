# Agent B semantic-vector integrity checkpoint — 2026-09-22

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

This checkpoint stays inside Lane-B-owned pure helper/test/docs surfaces. It does not modify `scanner.py`, `run_scan`, global budgets, final repair priority, authority/persistence, customer projection, admission, release, deployment, credentials, schema, workers, or production.

## Why this slice exists

Lane B intentionally exposes a pluggable/local `SemanticVectorizer` interface so semantic clustering and candidate evidence do not require a paid or external model. The original interface trusted the adapter's returned dictionary shape. A malformed or nondeterministic local adapter could therefore transport a foreign URL identity, non-finite/bool weights, an unbounded dimension set, duplicate assessed-page identity ambiguity, or different vectors for the same input.

Those conditions must not become trusted semantic-cluster, cannibalization, or source-to-target link evidence.

## Added contract

`scanner-api/app/semantic_graph_vector_contract.py` adds `semantic_vector_contract_v1` plus `ValidatedSemanticVectorizer`.

The contract is pure and network-free. It:

- validates the assessed-page population up to the existing 1,000-page Lane-B ceiling;
- rejects duplicate page identities rather than silently choosing one page;
- requires an explicit bounded vectorizer version;
- rejects vectors for URLs outside the assessed page population;
- rejects malformed/empty vectors, malformed terms, bool/non-numeric/non-finite/extreme weights, and zero-norm vectors;
- bounds each sparse semantic vector to 2,048 dimensions and each dimension label to 128 characters;
- canonicalizes URL/dimension ordering without mutating the source payload;
- invokes the local adapter twice by default and requires byte-equivalent canonical output, making deterministic behavior machine-testable;
- returns `state=not_verified` with a reason and no transported vectors whenever validation fails;
- provides `ValidatedSemanticVectorizer`, which preserves the existing `.vectors(pages)` interface and raises a reasoned `SemanticVectorContractError` instead of handing invalid vectors to existing Lane-B analyzers;
- never creates a customer Fix and retains `scope=observed_assessed_pages_only`.

The integrator may wrap optional/local semantic adapters with `ValidatedSemanticVectorizer` before passing them to the existing `semantic_similarity_matrix`, `semantic_clusters`, `cannibalization_candidates`, `internal_link_opportunities`, or contextual-opportunity analyzers. This lane does not wire that policy into shared orchestration.

## Regression coverage

`scanner-api/tests/test_semantic_graph_vector_contract.py` adds 12 deterministic tests covering:

- valid deterministic vector evidence and non-mutation;
- foreign vector URL rejection;
- duplicate assessed-page identity rejection;
- bool, NaN, +inf, and -inf weight rejection;
- zero-norm rejection;
- per-page dimension bounding;
- explicit nondeterminism detection;
- strict-adapter compatibility for valid local vectors;
- strict-adapter reason propagation for invalid vectors.

Hermetic execution of the new pure slice:

```text
PYTHONPATH=. pytest -q tests/test_semantic_graph_vector_contract.py
............                                                             [100%]
12 passed in 0.09s

python -m py_compile app/semantic_graph_vector_contract.py tests/test_semantic_graph_vector_contract.py
PASS
```

The branch previously contained 29 focused Lane-B tests, so the current branch contains an expected 41 focused tests across five test files. The complete exact-head repository suite is not claimed green from this runtime because outbound DNS cannot resolve `github.com`, so a repository checkout cannot be created here, and this integration-target draft has no PR-triggered CI by default.

Required exact-head gate before serialized integration acceptance:

```text
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py \
  tests/test_semantic_graph_vector_contract.py

python -m py_compile \
  app/semantic_graph.py \
  app/semantic_graph_html.py \
  app/semantic_graph_contextual.py \
  app/semantic_graph_vector_contract.py \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py \
  tests/test_semantic_graph_vector_contract.py
```

## Integration boundary

No serialized surface change is required by this checkpoint. The integrator can adopt the strict adapter at the semantic-analyzer call boundary while keeping the feature shadow/off. The existing graph, B10 duplicate evidence, repair/root-cause authority, final priority, persistence, and customer projection remain unchanged.

No merge or deployment is authorized from this lane.
