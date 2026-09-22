# Lane B handoff — semantic population coverage binding

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

Code checkpoint before this handoff: `31176f8fdd38af5ad6b4a9523b8a201505ab3f94`

This checkpoint stays entirely inside the Agent-B ownership boundary from
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not change
`run_scan`, global budgets, final repair priority/customer scoring, durable
authority/persistence, customer projection, admission, release/deployment,
worker configuration, credentials, schema, or production behavior.

## Gap closed

The published `semantic_vector_contract_v1` correctly validated adapter identity,
vector shape, numeric bounds, population membership, determinism, and input
isolation. It intentionally allowed a deterministic adapter to return vectors for
a subset of assessed page identities.

That subset behavior is useful, but the previous downstream contracts did not
separate **vector integrity** from **vector population coverage**. A three-page
assessed corpus with vectors for only two pages could therefore produce valid
semantic candidates while fields such as `semantic_pair_scan_complete` could be
read as if every assessed page identity had participated. The preferred graph
envelope could also reach top-level `verified` without explicitly recording that
one assessed page had no semantic representation.

That was an evidence-truthfulness gap. A complete scan of the vectorized subset is
not the same fact as complete semantic coverage of the assessed population.

## Added pure coverage contract

`scanner-api/app/semantic_graph_coverage.py` adds
`semantic_vector_coverage_v1`.

The helper is pure and provider-free. It records:

- input page count;
- assessed page identity count;
- vectorized page count;
- unidentified page count;
- unvectorized assessed-identity count;
- page-identity coverage (`complete`, `partial`, `none`, `not_verified`);
- semantic-vector coverage (`complete`, `partial`, `none`, `not_verified`);
- whether semantic pair analysis covers every assessed page identity;
- explicit pair scope (`all_assessed_page_identities`,
  `vectorized_assessed_page_subset`, `no_vectorized_pages`, or `not_verified`);
- `sitewide_semantic_coverage_claim=False`.

Counts are strict non-negative integers; booleans/coercible values do not silently
become valid counts. Impossible populations fail closed.

## Contract propagation

`semantic_vector_contract_v1` remains the adapter-integrity contract and retains
its version for compatibility. It now carries the separately versioned semantic
coverage evidence alongside canonical vectors. A deterministic partial vector set
can therefore remain integrity-verified while being coverage-partial.

The preferred semantic-analysis bundle is now
`semantic_analysis_bundle_v2_semantic_coverage_bound`. It transports coverage to
semantic clusters, cannibalization candidates, and contextual source→target link
opportunities while leaving B10 near-duplicate evidence independent because that
evidence is based on verified main-content shingles rather than semantic vectors.

The preferred full Lane-B envelope is now
`semantic_graph_evidence_v6_semantic_coverage_bound`:

- complete semantic coverage may reach top-level `verified` when the other graph,
  template, raw-zone, and template-opportunity integrity boundaries also verify;
- partial valid vector coverage produces top-level `partial` with
  `semantic_vector_coverage_partial` rather than a false full-verification claim;
- zero semantic-vector coverage is `not_verified` with
  `semantic_vector_coverage_unavailable`;
- malformed/not-verified semantic coverage remains fail-closed;
- sitewide semantic coverage is never claimed.

This remains evidence only. No customer Fix is created here.

## Regressions

New focused tests:

- `tests/test_semantic_graph_coverage.py` — 10 cases for complete/partial/none,
  missing identities, invalid counts, impossible populations, and integrity-state
  handling;
- `tests/test_semantic_graph_vector_coverage_binding.py` — 4 cases proving vector
  integrity and vector coverage remain separate and explicit;
- `tests/test_semantic_graph_evidence_bound_semantic_coverage.py` — 3 cases proving
  partial coverage cannot become a fully verified envelope, complete coverage can,
  and zero vectors remain not verified.

The branch therefore contains an expected **124 focused Lane-B tests across 18
test files** (107 previous + 17 new cases).

## Verification performed in this run

The new standalone coverage helper/test bytes passed locally before publication:

```text
PYTHONPATH=. pytest -q tests/test_semantic_graph_coverage.py
10 passed in 0.06s
python -m py_compile app/semantic_graph_coverage.py tests/test_semantic_graph_coverage.py
PASS
```

A supplementary hermetic mirror of the current coverage/vector-contract slice,
including the existing vector-contract regressions and the new coverage-binding
regressions, passed:

```text
PYTHONPATH=. pytest -q \
  tests/test_semantic_graph_vector_contract.py \
  tests/test_semantic_graph_coverage.py \
  tests/test_semantic_graph_vector_coverage_binding.py
29 passed in 0.06s
```

This is supplementary pure-function evidence, not a claim that the exact branch
checkout ran the complete repository-native suite.

The execution container still cannot check out GitHub:

```text
git ls-remote https://github.com/bright4862-design/seo-autopilot.git HEAD
fatal: unable to access 'https://github.com/bright4862-design/seo-autopilot.git/': Could not resolve host: github.com
```

## Exact-head gate required before integration acceptance

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
  app/semantic_graph_evidence_bound.py \
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
```

Do not claim exact-head 124/124 repository green until that gate runs.

## Integration handoff

The serialized integrator should continue to prefer
`build_vector_bound_semantic_graph_evidence(...)`. Preserve semantic adapter
integrity and semantic population coverage as separate facts. In particular:

- `semantic_pair_scan_complete=True` inside a semantic analyzer means its
  qualifying pair enumeration completed for the available vector population;
- use `semantic_pair_population_complete` and `semantic_pair_scope` to determine
  whether that vector population represents every assessed page identity;
- never promote `partial` coverage to a sitewide negative/absence claim;
- B10 near-duplicate evidence remains independently governed by verified
  main-content shingles;
- template/link-zone/graph candidate evidence remains descriptive and should be
  fed into the existing B20/root-cause/priority/authority layers by the serialized
  integrator rather than turned into a customer Fix in this lane.

No merge or deployment is authorized from Lane B.
