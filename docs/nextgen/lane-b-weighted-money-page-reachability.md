# Lane B handoff — weighted money-page reachability evidence

## Scope

This checkpoint remains inside the Agent B ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

It adds deterministic, assessed-sample reachability evidence for already-classified money pages by binding the exact bounded raw-link observations to the validated weighted internal-link graph. It does **not** create customer Fixes, rank repairs, write persistence/authority, touch `run_scan`, alter admission/workers, or change release/deployment/production behavior.

This is a deeper Lane-B evidence layer for blueprint B11. It does not replace the existing Standard-150 B11 producer/provenance contract and does not claim sitewide orphaning.

## New evidence contract

`scanner-api/app/semantic_graph_money_reachability.py` adds:

- `money_page_reachability_v2_weighted_graph_bound`
- graph-bound observed in-edge count and weighted-in evidence
- exact raw-link occurrence counts retained separately from deduplicated directed edges
- inbound navigation/contextual/unknown and full per-zone directed-edge counts
- mixed-zone inbound edge counts so a contextual strongest edge does not erase an observed navigation occurrence on the same source→target pair
- strongest inbound source/zone/weight evidence
- deterministic shortest observed depth from an explicit or retained assessed seed
- explicit `no_observed_route_from_seed_in_assessed_graph` state when the bounded graph contains no seed route
- sample-scoped weak-route reasons for zero observed in-edges, depth >= 4, no observed seed route, and no observed navigation edge
- explicit partial depth state when no trustworthy seed identity is available

Money-page classification is deterministic and uses only already-retained classification evidence: an explicit money-page flag/value class, the established Stage-2 money template-family vocabulary, or an already-produced commercial/conversion/transactional money intent. URL text is not used to invent a money-page classification.

The helper first validates graph metrics and then binds the graph back to the exact raw-link population through the existing `link_zone_observation_profile_v1_graph_bound` contract. Forged graph totals, raw-link/graph divergence, duplicate page identities, or seed identities outside the assessed population fail closed to `not_verified`.

All absence/weakness statements remain assessed-sample evidence only. `sitewide_reachability_claim`, `sitewide_orphan_claim`, `sitewide_navigation_absence_claim`, `sitewide_link_absence_claim`, `sitewide_link_distribution_claim`, and `customer_fix_created` remain false.

## Preferred additive envelope

`scanner-api/app/semantic_graph_evidence_money_reachability_bound.py` adds:

- `semantic_graph_evidence_v12_money_reachability_bound`

The v12 wrapper extends v11 and consumes only the already-built weighted graph plus the same bounded page/link observations. It performs no additional semantic/vector/provider invocation, so the existing two-call adapter determinism/input-isolation boundary remains unchanged.

A reachability-integrity failure fails the additive envelope closed. A missing seed does not: graph/link evidence remains verified while page depth is explicitly partial. Observing zero classified money pages is likewise an assessed-sample zero, not a sitewide statement.

## Regressions added

Two focused test files add 14 behavioral regressions:

- `scanner-api/tests/test_semantic_graph_money_reachability.py` — 11 tests
- `scanner-api/tests/test_semantic_graph_money_reachability_binding.py` — 3 tests

Coverage includes:

- direct navigation reachability
- contextual-only weak-route evidence
- observed depth-four weak routes
- repeated mixed-zone source→target observations
- explicit seed binding
- partial depth when seed evidence is unavailable
- disconnected assessed seed routes without sitewide orphan claims
- out-of-population seed rejection
- forged graph-metric rejection
- raw-link/graph divergence rejection
- verified zero classified-money-page sample
- v12 composition with no additional vectorizer calls
- v12 fail-closed invalid-seed binding
- v12 zero-money-page behavior without invented candidates

Expected Lane-B focused accounting is now **219 tests across 30 semantic-graph test files** (previous checkpoint: 205 across 28).

## Verification performed in this run

The two new application modules and two new test files passed `py_compile` locally.

A hermetic package harness passed **14/14** focused regressions covering the new helper and additive envelope behavior. The harness reproduced the existing weighted-graph/link-zone contracts locally; it is supplementary evidence, not a substitute for the repository-native suite.

The full branch-native 219-test pytest suite is **not claimed green** at this checkpoint because the execution container still cannot resolve `github.com` for a local branch checkout. Integration should therefore require an exact-head repository-native run such as:

```bash
cd scanner-api
python -m pytest -q tests/test_semantic_graph*.py
python -m py_compile \
  app/semantic_graph_money_reachability.py \
  app/semantic_graph_evidence_money_reachability_bound.py \
  tests/test_semantic_graph_money_reachability.py \
  tests/test_semantic_graph_money_reachability_binding.py
```

## Integration hook

The serialized integrator may later pass the submitted/verified seed identity through `seed_urls` when building v12. If no trusted seed is available, leave it unset; the contract intentionally returns partial depth instead of guessing.

No final customer Fix, repair-priority, `run_scan`, authority/persistence, customer projection, admission, schema, worker control, release/deployment, or production surface is part of this checkpoint. Merge/deploy remains the serialized integrator's responsibility.
