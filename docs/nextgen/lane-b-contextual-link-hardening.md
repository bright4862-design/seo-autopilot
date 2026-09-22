# Agent B contextual-link opportunity hardening — 2026-09-22

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

This checkpoint stays entirely inside the Agent-B ownership boundary from
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not change
`run_scan`, global budgets, final repair priority/customer scoring, authority,
persistence, customer projection, admission, release, deployment, worker config,
credentials, or production behavior.

## Problems reproduced by code inspection/review

The original `internal_link_opportunities(...)` treats any observed directed edge
as sufficient to suppress a source→target recommendation. That means a page pair
with only a navigation/footer/listing/facet link cannot surface a contextual-link
upgrade even though Lane B explicitly distinguishes link zones and the proposed
opportunity is contextual.

The same function accepts a transported graph after checking only the graph
version. A same-version graph with a different node population or a foreign edge
could therefore influence absence/opportunity evidence for the wrong assessed
page set.

Independent review of the first contextual hardening checkpoint found a further
P1 integrity defect: `_validated_graph(...)` checked transported node weights only
for finite/non-negative shape. A graph could therefore preserve valid edges while
forging `weighted_in` or `weighted_out`, pass validation, and change opportunity
score ordering. Because the producer derives node metrics from accepted edge rows,
transported node metrics must agree with those rows before they can influence a
candidate score.

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
  edge endpoints, zones, and finite non-negative six-decimal graph weights before
  graph data can influence a recommendation;
- independently recomputes each node's expected inbound/outbound unique-edge
  counts and six-decimal inbound/outbound weight sums from the validated edge set;
- rejects transported node counts or weights that disagree with those recomputed
  metrics, rather than trusting caller-supplied score inputs;
- rejects booleans/coercible non-integer node edge counts and non-finite or
  over-precision graph weights;
- fails closed to `not_verified` when graph identity/integrity is ambiguous;
- continues to require a usable source/target and an explicitly indexable target;
- remains deterministic, bounded by the existing Lane-B candidate limit, and
  performs no network/model/provider call.

This is an additive evidence helper. It intentionally does not rewrite
`run_scan`, customer Fix creation, repair/root-cause composition, or final
priority. The serialized integrator can choose this contextual-specific contract
when wiring Lane B later.

## Regressions added

`scanner-api/tests/test_semantic_graph_contextual.py` now contains ten
deterministic regressions covering:

1. a navigation-only edge remains eligible for a contextual upgrade;
2. an already-contextual edge suppresses a duplicate contextual proposal;
3. graph/page population mismatch fails closed;
4. a foreign graph edge fails closed;
5. a non-indexable target is never proposed;
6. output is deterministic across page-order changes;
7. forged `weighted_in` fails closed;
8. forged `weighted_out` fails closed;
9. forged observed inbound-edge count fails closed;
10. forged observed outbound-edge count fails closed.

The four forged-metric cases were added before the implementation correction.
A hermetic validator harness then confirmed a valid internally consistent graph is
accepted and all four forged metric/count cases fail closed with the expected
reason. This harness is useful evidence for the corrected pure logic, but it does
not replace exact-head repository pytest.

## Exact-head verification blocker

The implementation and regressions are committed, but the current automation
execution environment cannot clone the repository because outbound DNS cannot
resolve `github.com`. This PR targets the NextGen integration branch and currently
has no PR-triggered repository workflow run to use as a substitute.

Do **not** claim the complete exact-head Lane-B suite green until this executes:

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

The branch now contains 29 focused Lane-B tests across those four test files. The
previously executed pre-cannibalization/contextual checkpoint remains 17/17
focused tests green plus `py_compile` PASS. The later two cannibalization evidence
regressions and ten contextual regressions are committed but are not claimed as a
fresh 29/29 repository run in this environment.

## Integration handoff

After Agent A is accepted and Lane B reaches exact-head green verification, the
serialized integrator may transplant this additive module/test with the rest of
Lane B. Prefer `contextual_internal_link_opportunities(...)` where the intended
customer/root-cause evidence is specifically a body/contextual-link opportunity.
Consumers must preserve `observed_edge_present`, `existing_strongest_zone`, the
assessed-sample scope, and `graph_integrity_state`; an existing navigation/footer
edge is not equivalent to an observed contextual edge, and an internally
inconsistent transported graph is not verified evidence.

No merge or deployment is authorized from this lane.
