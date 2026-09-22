# Lane B handoff — raw link-zone observation binding

Branch: `agent/nextgen-semantic-graph-20260921`

Code checkpoint before this handoff: `89e9750448e6dbabe89e8653c70d65dc771eb1af`

## Why this slice exists

The weighted semantic graph deliberately reduces repeated source→target link observations to one directed edge and retains only the strongest observed zone. That is useful for graph scoring, but it loses evidence that the same pair was also observed in navigation, footer, listing, aside, or other zones. The existing graph validator also proves node totals against transported edge weights but, by itself, cannot prove that `observed_occurrences`, strongest zone, strongest weight, zone confidence, anchor terms, or skipped-link counters still match the raw bounded link observations.

This slice adds a separate pure, versioned evidence contract rather than changing the existing graph schema.

## New contract

`link_zone_observation_profile_v1_graph_bound`

Implemented in:
- `scanner-api/app/semantic_graph_zone_profile.py`

The helper:
- accepts the already-assessed pages, already-observed bounded raw links, and the Lane-B weighted graph;
- revalidates exact assessed-page graph population and node metrics first;
- independently regenerates the graph-eligible internal-link observation population using the same host/assessed-page rules as the graph producer;
- preserves occurrence-level zone counts and occurrence-weight sums across contextual/listing/aside/navigation/header/footer/facet/unknown observations;
- binds each transported edge to raw evidence for occurrence count, strongest zone, strongest weight, strongest-zone confidence, and bounded anchor-term union;
- binds `skipped_external_links` and `skipped_unassessed_targets` to the raw observations;
- bounds emitted edge profiles at 250 while preserving full observed edge/occurrence counts and an explicit truncation bit;
- fails closed when assessed-page identity coverage is incomplete;
- makes no sitewide link-distribution, link-absence, or orphan claim;
- creates no customer Fix and performs no network/model/provider work.

The preferred full Lane-B envelope is now:

`semantic_graph_evidence_v5_raw_zone_profile_bound`

`build_vector_bound_semantic_graph_evidence(...)` includes both:
- the older strongest-zone-per-directed-edge summary, for compact compatibility; and
- the new raw-observation-bound `link_zone_observation_profile`, for truthful repeated-zone evidence and transport integrity.

## Regressions added

`scanner-api/tests/test_semantic_graph_zone_profile.py` adds 10 focused cases covering:
1. preserving multiple observed zones for one reduced graph edge;
2. forged graph occurrence count;
3. forged strongest zone even when graph node metrics remain balanced;
4. forged edge weight plus consistently forged node totals;
5. forged anchor terms;
6. forged skipped-link counters;
7. deterministic output across raw-link ordering;
8. bounded edge-profile output without hiding total coverage;
9. incomplete assessed-page identity coverage;
10. non-mutation of pages, links, and graph inputs.

`scanner-api/tests/test_semantic_graph_evidence_bound_zone_profile.py` adds 2 envelope-composition cases covering:
- versioned exposure of the raw-observation-bound zone profile; and
- zero-observed-link evidence remaining verified-but-sample-scoped rather than becoming a sitewide absence claim.

Expected Lane-B focused total after this slice: **107 tests across 15 test files**.

A supplementary hermetic logic harness executed during this run passed the valid multi-zone binding, forged occurrence/zone/weight/anchor rejection, deterministic ordering, and 251-edge bounded-output assertions. This is supplementary evidence only, not a substitute for the exact-head repository pytest gate.

## Required exact-head verification before transplant acceptance

```bash
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
  tests/test_semantic_graph_evidence_bound_zone_profile.py

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
  tests/test_semantic_graph_evidence_bound_zone_profile.py
```

## Integration requirements

The serialized integrator should continue to consume `build_vector_bound_semantic_graph_evidence(...)` rather than wiring this helper independently into customer output. Keep `link_zone_observation_profile` descriptive and sample-scoped. It can support later root-cause reasoning about whether a semantically relevant source→target relationship is only visible in global/navigation/template surfaces versus contextual content, but Lane B does not turn that evidence into a customer Fix or priority score.

The new profile should remain tied to the same assessed-page and raw-link population used to construct the weighted graph. Do not reconstruct it from a different crawl, rendered session, later provider result, or customer projection.

## Boundaries preserved

No `run_scan`, global budget, final repair priority, durable authority/persistence, customer projection, admission, release/deployment, schema, credentials, worker configuration, or production behavior was changed. No merge or deployment is authorized from this lane.
