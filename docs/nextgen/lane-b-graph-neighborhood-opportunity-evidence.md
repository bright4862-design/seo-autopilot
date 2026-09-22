# Lane B handoff — assessed graph-neighborhood opportunity evidence

## Scope

This checkpoint remains inside the Agent B ownership boundary defined by `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

It adds deterministic, assessed-sample route evidence to the existing source→target contextual internal-link opportunity chain. It does **not** create customer Fixes, rank repairs, write persistence/authority, touch `run_scan`, alter admission/workers, or change release/deployment/production behavior.

## New evidence contract

`scanner-api/app/semantic_graph_opportunity_neighborhood.py` adds:

- `template_contextual_internal_link_opportunity_v3_graph_neighborhood_bound`
- directed shortest-path hops from candidate source to target in the already-validated assessed internal-link graph
- reverse shortest-path hops measured independently
- deterministic two-hop bridge evidence
- bridge bottleneck weights derived only from the existing weighted graph edges
- shared outbound-neighbour and inbound-neighbour counts
- explicit assessed-graph route state (`reachable_in_assessed_graph` vs `no_observed_route_in_assessed_graph`)

The contract deliberately does **not** interpret an unobserved route as a sitewide orphan or reachability failure. `sitewide_reachability_claim`, `sitewide_orphan_claim`, `sitewide_link_absence_claim`, template-flow/distribution claims, and `customer_fix_created` remain false.

An existing non-contextual direct edge remains a legitimate contextual-upgrade candidate. In that case the graph route is one hop; the helper verifies that the candidate's transported edge-presence and strongest-zone evidence exactly matches the graph. Candidate/graph divergence fails closed to `not_verified`.

Two-hop bridge samples are bounded to eight rows and sorted deterministically by descending bottleneck edge weight and then URL. Full bridge count remains available separately so sample truncation is explicit.

## Preferred additive envelope

`scanner-api/app/semantic_graph_evidence_opportunity_neighborhood_bound.py` adds:

- `semantic_graph_evidence_v11_graph_neighborhood_opportunity_bound`

The v11 wrapper extends v10 and consumes only the already-produced raw-zone contextual opportunities plus the already-built weighted graph. It performs no additional semantic/vector/provider invocation. The existing two-call adapter determinism/input-isolation boundary therefore remains unchanged.

## Regressions added

Two focused test files add 14 behavioral regressions:

- `scanner-api/tests/test_semantic_graph_opportunity_neighborhood.py` — 11 tests
- `scanner-api/tests/test_semantic_graph_opportunity_neighborhood_binding.py` — 3 tests

Coverage includes:

- two-hop and longer directed routes
- no-route sample-scoped evidence
- reverse-route independence
- deterministic bridge ordering by bottleneck weight
- existing non-contextual direct-edge contextual upgrades
- candidate/graph edge-presence mismatch fail-closed behavior
- candidate/graph strongest-zone mismatch fail-closed behavior
- forged graph metric rejection
- unverified raw-zone evidence rejection
- verified zero-candidate state
- v11 composition without extra vectorizer calls
- partial semantic coverage without invented route candidates

Expected Lane-B focused accounting is now **205 tests across 28 semantic-graph test files** (previous checkpoint: 191 across 26).

## Verification performed in this run

The four newly authored Python source/test files were syntax-compiled before publication.

A hermetic pure-helper harness passed 4/4 checks covering two-hop bridge evidence, direct non-contextual route evidence, no-route evidence, and candidate/graph edge-presence divergence.

A hermetic v11 composition harness passed 4/4 assertions covering envelope versioning, the unchanged two vectorizer calls, partial-state preservation, and non-sitewide route guards.

The full branch-native 205-test pytest suite is **not claimed green** at this checkpoint. The execution environment could not resolve `github.com` for a local checkout, and GitHub reported no workflow run for the pre-handoff exact head `840391a81f4b4503064b68ac2926b7723ff4b916`.

Integration should therefore require an exact-head repository-native run such as:

```bash
cd scanner-api
python -m pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph_opportunity_neighborhood.py app/semantic_graph_evidence_opportunity_neighborhood_bound.py tests/test_semantic_graph_opportunity_neighborhood.py tests/test_semantic_graph_opportunity_neighborhood_binding.py
```

## Ownership guard

No final customer Fix, repair-priority, `run_scan`, authority/persistence, customer projection, admission, schema, worker control, release/deployment, or production surface is part of this checkpoint. Merge/deploy remains the serialized integrator's responsibility.
