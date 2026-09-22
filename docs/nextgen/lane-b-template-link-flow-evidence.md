# Agent B graph-bound template link-flow evidence — 2026-09-22

Branch: `agent/nextgen-semantic-graph-20260921`  
Draft PR: #329  
Issue: #323

This checkpoint stays entirely inside the Agent-B ownership boundary in
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not modify
`run_scan`, global budgets, final repair priority/customer scoring,
authority/persistence, customer projection, admission, release/deployment,
worker configuration, credentials, schema, or production behavior.

## Gap closed

Lane B already produced deterministic page/template groups, link-zone evidence,
a weighted assessed-page graph, one-snapshot semantic analysis, cannibalization /
near-duplicate candidates, and contextual source-to-target opportunity evidence.
The preferred full envelope also exposed a site-level strongest-zone summary.

What was still missing was a versioned evidence object that answered a more useful
root-cause question without inventing a Fix: **how do the observed assessed links
flow between template groups, and which strongest link zones carry those observed
flows?**

Counting raw zones alone cannot distinguish, for example, observed article→product
contextual flow from same-template navigation flow. Conversely, generating
unobserved template-pair recommendations here would cross the Lane-B evidence
boundary and risk turning sample absence into a sitewide claim.

## Added contract

`scanner-api/app/semantic_graph_template_flow.py` adds:

- `template_link_flow_evidence_v1_graph_bound`;
- exact template page/group identity validation;
- deterministic `group_id` ↔ `template_key` binding using the producer's
  `tmpl_<sha256(template_key)[:12]>` identity rule, so a caller cannot regroup pages
  under forged but internally self-consistent template IDs;
- exact template-page ↔ graph-node population binding;
- reuse of Lane B's graph integrity validator, including edge endpoints/zones and
  recomputed node edge counts/weights;
- deterministic aggregation by directed source-template → target-template pair;
- observed directed edge count, unique source/target page counts, six-decimal
  observed weight sum, strongest-zone counts, and contextual-edge count;
- bounded deterministic observed edge samples (5 per flow) while preserving the
  full observed edge count;
- explicit `sitewide_template_flow_claim=false`,
  `sitewide_link_absence_claim=false`, and `customer_fix_created=false`.

The helper fails closed rather than transporting ambiguous evidence when template
identity, deterministic group identity, declared group counts/keys, page
population, graph population, edge identity/zone, or graph node metrics are
inconsistent.

A zero-edge assessed graph remains valid **observed evidence with zero observed
flows**. It is not converted into proof that no links exist sitewide.

## Preferred envelope integration

`build_vector_bound_semantic_graph_evidence(...)` now includes the graph-bound
`template_link_flow` evidence and bumps its preferred envelope contract to:

`semantic_graph_evidence_v3_template_flow_bound`

The envelope exposes `template_link_flow_version` and
`sitewide_template_flow_claim=false`. A non-verified template-flow integrity state
prevents the top-level envelope from becoming verified. The legacy
`build_semantic_graph_evidence(...)` remains untouched.

## Regressions added

`scanner-api/tests/test_semantic_graph_template_flow.py` adds eight deterministic
cases covering:

1. article→product flow aggregation across contextual/navigation/footer zones;
2. graph metric forgery failing closed before weights are trusted;
3. exact template-page/graph-node population binding;
4. forged declared template group counts failing closed;
5. forged but internally self-consistent template group IDs failing closed;
6. missing template page identity failing closed;
7. deterministic output across reversed page/link input order;
8. bounded edge samples without hiding the true observed edge count.

`scanner-api/tests/test_semantic_graph_evidence_bound_template_flow.py` adds two
composition cases proving the preferred envelope carries the new flow contract
and that a zero-edge assessed graph stays verified-but-observed-only rather than
becoming a sitewide absence claim.

Expected Lane-B focused total after this checkpoint: **80 tests across 11 test
files** (previous 70 plus 10 new regressions).

## Verification

The local execution container still cannot resolve `github.com`, so an exact-head
repository checkout remains unavailable. A hermetic mirror of the new pure helper
passed focused assertions for:

- valid cross-template observed flow;
- graph node-weight forgery rejection;
- declared template group-count forgery rejection.

The deterministic group-ID hardening was additionally checked by code inspection
against the existing `infer_template_groups` producer identity rule. These are
supplementary checks only. They do **not** replace the required branch-native
exact-head gate:

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
  tests/test_semantic_graph_evidence_bound_template_flow.py

python -m py_compile \
  app/semantic_graph.py \
  app/semantic_graph_html.py \
  app/semantic_graph_contextual.py \
  app/semantic_graph_vector_contract.py \
  app/semantic_graph_contextual_vector_bound.py \
  app/semantic_graph_analysis_bound.py \
  app/semantic_graph_template_flow.py \
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
  tests/test_semantic_graph_evidence_bound_template_flow.py
```

Do not claim 80/80 exact-head green until that repository-native command runs.

## Integration handoff

After Agent A is accepted and Lane B reaches the exact-head gate, the serialized
integrator should continue to prefer `build_vector_bound_semantic_graph_evidence`.
Treat `template_link_flow` as descriptive observed-sample evidence that can inform
the existing root-cause/priority layer later. Do not interpret a missing flow row
as proof that a template pair lacks links sitewide, and do not turn template-flow
counts directly into customer Fixes in this lane.

No merge or deployment is authorized from this branch.
