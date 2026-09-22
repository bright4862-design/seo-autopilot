# Lane B review hardening checkpoint — 2026-09-22

Issue: #323  
Draft PR: #329  
Branch: `agent/nextgen-semantic-graph-20260921`

Authoritative ownership boundary read before this work:
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.
That boundary document is read-only for the lane; writable documentation remains
under `docs/nextgen/lane-b-*`.

## Purpose

Address the current independent review findings without crossing the Agent-B
ownership boundary or changing any customer/release surface.

## Changes

### Contextual-edge normalization

`scanner-api/app/semantic_graph_contextual.py` now normalizes transported
`strongest_zone` identically in graph validation and contextual-opportunity
suppression: surrounding whitespace is stripped before lowercasing.

This closes a correctness gap where a transported value such as
`"  Contextual  "` could pass `_validated_graph(...)` but fail the later
`existing_zone == "contextual"` suppression check, causing a duplicate
contextual source→target opportunity to be emitted even though contextual link
evidence was already present.

The normalized zone is also the value reported as `existing_strongest_zone` for
non-contextual upgrade candidates.

### Regression

`scanner-api/tests/test_semantic_graph_contextual.py` adds
`test_contextual_zone_normalization_matches_graph_validation_before_suppression`.
It proves that:

- padded/case-varied contextual zone evidence still passes graph validation;
- the already-observed contextual direction is suppressed;
- the opposite direction remains independently eligible when no edge was
  observed there.

The expected Lane-B focused total is now **127 tests across 18 test files**.

### Ownership documentation

`docs/nextgen/lane-b-semantic-graph.md` now makes explicit that
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md` is the exact
authoritative ownership contract and a read-only input, not part of the lane's
writable `lane-b-*` documentation surface.

## Verification performed in this runtime

A hermetic targeted harness reproducing the contextual graph contract passed:

```text
PYTHONPATH=. python -m py_compile app/semantic_graph_contextual.py test_slice.py
PYTHONPATH=. pytest -q test_slice.py
..                                                                       [100%]
2 passed in 0.05s
```

The harness covered both padded contextual suppression and normalized reporting
for a padded navigation zone.

The complete exact-head repository suite is **not claimed green** because this
runtime still cannot resolve `github.com` from the container for a repository
checkout. The required repository gate remains:

```text
cd scanner-api
PYTHONPATH=. pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph*.py tests/test_semantic_graph*.py
```

## Remaining review item

CodeRabbit also suggested caching vector norms during the O(n²) semantic pair
scan. That is a non-functional performance optimization, not a correctness
finding. It remains intentionally separate from this correctness-hardening
checkpoint so the reviewed behavioral fix stays minimal and easy to verify.

## Integrator handoff

No integration behavior changes. Preserve the existing rule that graph-zone
validation and downstream zone interpretation must use the same canonical
normalization. Keep all opportunity evidence assessed-sample scoped and do not
promote candidate evidence directly into a customer Fix.

No `run_scan`, global budget, final repair priority, authority/persistence,
customer projection, admission, schema, worker, release/deployment, credential,
or production surface was modified. Nothing was merged or deployed.
