# Lane B handoff — template-bound contextual link opportunities

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

## Scope

This checkpoint extends Lane B's source-to-target contextual internal-link evidence with validated template context. It stays entirely inside Agent-B-owned pure helper/test/docs surfaces and performs no network work, persistence, customer Fix creation, repair prioritization, scan orchestration, release, deployment, or production mutation.

## New contract

`template_contextual_internal_link_opportunity_v1_graph_bound`

The helper `template_contextual_internal_link_opportunities(...)` accepts:

- existing `template_group_evidence_v1` output;
- the exact assessed-page weighted semantic graph;
- existing contextual source-to-target candidate evidence.

Before attaching template context it independently:

1. revalidates template membership and deterministic `group_id` identity;
2. revalidates the weighted graph population, edges, zones, counts, and weights;
3. validates contextual candidate shape, candidate counts/truncation, assessed-page population, directed-pair uniqueness, evidence scope, proposed contextual zone, and sitewide-claim invariants;
4. cross-checks every candidate's `observed_edge_present` and `existing_strongest_zone` against the validated graph;
5. refuses any candidate whose exact directed edge is already contextual;
6. regenerates template-to-template flow from the validated template evidence and graph instead of trusting transported flow rows.

Each accepted candidate is enriched with:

- source/target template group IDs and template keys;
- `cross_template`;
- whether the relevant directed template flow was observed in the assessed sample;
- observed directed-edge count for that template flow;
- observed contextual-edge count for that template flow;
- observed template-flow weight sum;
- an explicit sample-scoped template-flow state.

A missing template flow is emitted only as `no_observed_flow_in_assessed_sample`. It is never proof of sitewide absence.

## Preferred envelope

The preferred Lane-B envelope is now:

`semantic_graph_evidence_v4_template_opportunity_bound`

`build_vector_bound_semantic_graph_evidence(...)` now exposes:

- `template_contextual_opportunity_version`;
- `template_contextual_internal_link_opportunities`.

The envelope still exposes the underlying contextual opportunity evidence unchanged for compatibility and debugging. The new template-bound view is additional evidence for the serialized integrator/root-cause layer; it is not a customer repair.

## New regressions

`tests/test_semantic_graph_template_opportunity.py` adds 8 focused cases covering:

- observed cross-template flow bound to a source→target candidate;
- missing flow retained as assessed-sample-only evidence;
- same-template candidate identity;
- foreign candidate population rejection;
- forged edge-presence rejection;
- rejection when the directed edge is already contextual;
- duplicate candidate-pair rejection;
- deterministic, non-mutating behavior.

`tests/test_semantic_graph_evidence_bound_template_opportunity.py` adds 3 envelope cases covering:

- preferred-envelope exposure of template-bound candidate evidence;
- zero observed template flow without a sitewide absence claim;
- no-candidate state when both directed pairs already have observed contextual edges.

Expected focused Lane-B total after this checkpoint: **91 tests across 13 test files**.

A supplementary hermetic behavior harness for the new template-opportunity logic passed 8/8 assertions. This is not a substitute for the repository-native exact-head gate.

## Required exact-head gate

Run from `scanner-api` before transplant acceptance:

```text
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
  tests/test_semantic_graph_evidence_bound_template_opportunity.py

python -m py_compile \
  app/semantic_graph.py \
  app/semantic_graph_html.py \
  app/semantic_graph_contextual.py \
  app/semantic_graph_vector_contract.py \
  app/semantic_graph_contextual_vector_bound.py \
  app/semantic_graph_analysis_bound.py \
  app/semantic_graph_template_flow.py \
  app/semantic_graph_template_opportunity.py \
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
  tests/test_semantic_graph_evidence_bound_template_opportunity.py
```

The current execution container still cannot resolve `github.com`, so a repository checkout and the exact-head native gate could not be run in this checkpoint. Do not claim 91/91 green until that command is executed against the exact lane head.

## Integration guidance

After Lane B is exact-head green and Agent A is accepted, the serialized integrator may consume `build_vector_bound_semantic_graph_evidence(...)`. For internal-link/root-cause logic, prefer `template_contextual_internal_link_opportunities` when template context matters, but preserve the raw contextual candidate evidence and sample-scope flags.

Do not convert a missing template flow into a sitewide missing-link diagnosis. Do not convert this helper's candidate state directly into a final customer Fix. Candidate evidence should flow through the existing B20/root-cause, repair-priority, authority, persistence, and customer-projection boundaries owned by the serialized integrator.

## Rollback

This checkpoint is additive and Lane-B-local. Rollback is removal of the new helper/tests/handoff plus restoration of the prior `semantic_graph_evidence_v3_template_flow_bound` envelope revision before any serialized integration. No production state, schema, credentials, admission, or deployment surface is changed by this lane.
