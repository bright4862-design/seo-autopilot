# Agent B contextual-link opportunity hardening — 2026-09-22

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

This checkpoint stays entirely inside the Agent-B ownership boundary from
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not change
`run_scan`, global budgets, final repair priority/customer scoring, authority,
persistence, customer projection, admission, release, deployment, worker config,
credentials, or production behavior.

## Problem reproduced by code inspection

The original `internal_link_opportunities(...)` treats any observed directed edge
as sufficient to suppress a source→target recommendation. That means a page pair
with only a navigation/footer/listing/facet link cannot surface a contextual-link
upgrade even though Lane B explicitly distinguishes link zones and the proposed
opportunity is contextual.

The same function accepts a transported graph after checking only the graph
version. A same-version graph with a different node population or a foreign edge
could therefore influence absence/opportunity evidence for the wrong assessed
page set.

## Added pure evidence helper

`scanner-api/app/semantic_graph_contextual.py` adds the versioned
`contextual_internal_link_opportunity_v1` contract.

It:

- treats an existing non-contextual edge as eligible for a contextual upgrade;
- suppresses a directed proposal only when the strongest observed edge for that
  pair is already contextual;
- preserves whether any edge already exists, its strongest observed zone, and a
  reason distinguishing an upgrade from no observed edge in the assessed sample;
- never turns sample absence into a sitewide absence claim;
- validates graph version, scope, exact page/node population, unique identities,
  edge endpoints, zones, and finite non-negative graph weights before graph data
  can influence a recommendation;
- fails closed to `not_verified` when graph identity/integrity is ambiguous;
- continues to require a usable source/target and an explicitly indexable target;
- remains deterministic, bounded by the existing Lane-B candidate limit, and
  performs no network/model/provider call.

This is an additive evidence helper. It intentionally does not rewrite
`run_scan`, customer Fix creation, repair/root-cause composition, or final
priority. The serialized integrator can choose this contextual-specific contract
when wiring Lane B later.

## Regressions added

`scanner-api/tests/test_semantic_graph_contextual.py` contains six deterministic
regressions covering:

1. a navigation-only edge remains eligible for a contextual upgrade;
2. an already-contextual edge suppresses a duplicate contextual proposal;
3. graph/page population mismatch fails closed;
4. a foreign graph edge fails closed;
5. a non-indexable target is never proposed;
6. output is deterministic across page-order changes.

## Exact-head verification blocker

The implementation and regressions are committed, but the current automation
execution environment still cannot execute the repository checkout: the available
container/Python runner returns infrastructure `ClientError`. This PR targets the
NextGen integration branch and therefore has no repository PR workflow run to use
as a substitute.

Do **not** claim these new tests green until the exact head executes:

```text
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py

python -m py_compile \
  app/semantic_graph.py \
  app/semantic_graph_html.py \
  app/semantic_graph_contextual.py \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py
```

The previously executed pre-cannibalization-hardening checkpoint remains 17/17
focused tests green plus `py_compile` PASS. Neither the later cannibalization
regressions nor this six-test contextual hardening file is claimed as executed in
this environment.

## Integration handoff

After Agent A is accepted and Lane B reaches exact-head green verification, the
serialized integrator may transplant this additive module/test with the rest of
Lane B. Prefer `contextual_internal_link_opportunities(...)` where the intended
customer/root-cause evidence is specifically a body/contextual-link opportunity.
Consumers must preserve `observed_edge_present`, `existing_strongest_zone`, and
the assessed-sample scope; an existing navigation/footer edge is not equivalent
to an observed contextual edge.

No merge or deployment is authorized from this lane.
