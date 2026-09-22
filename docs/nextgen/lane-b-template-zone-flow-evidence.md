# Lane B handoff — raw-zone template flow evidence

Date: 2026-09-22

Branch: `agent/nextgen-semantic-graph-20260921`

This checkpoint remains inside the Agent-B ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not change `run_scan`, global budgets, final repair priority, customer Fix generation, authority/persistence, customer projection, admission, release/deployment, or production.

## Problem closed

The existing `template_link_flow_evidence_v1_graph_bound` intentionally summarizes the reduced weighted graph. One directed source→target edge retains its strongest observed zone, so repeated observations and mixed-zone evidence are not visible at the template-flow layer. That is correct for compact graph scoring but incomplete for diagnostics. For example, the same product→guide edge can be observed once in navigation and once in article content while the reduced graph exposes only the strongest contextual zone.

## New contract

`template_link_zone_flow_evidence_v2_raw_observation_bound` binds four already-local evidence surfaces together:

- the exact assessed-page identity population;
- validated `template_group_evidence_v1` membership;
- the validated weighted `semantic_graph_evidence_v1` graph;
- the exact bounded raw link observations already used by `link_zone_observation_profile_v1_graph_bound`.

For each directed template pair it emits:

- observed link occurrence count;
- deduplicated directed-edge count;
- observed source/target page counts;
- per-zone occurrence counts;
- per-zone maximum confidence;
- per-zone occurrence-weight sums;
- contextual occurrence and contextual directed-edge counts;
- mixed-zone directed-edge count;
- strongest-zone directed-edge counts from the reduced graph;
- up to five deterministic raw occurrence samples.

Repeated observations never inflate directed-edge counts. Mixed-zone evidence is explicit instead of being hidden by strongest-zone reduction. External and unassessed targets remain excluded from template flow and are reported only as scoped skip counts. Zero observed flow remains assessed-sample evidence and never becomes a sitewide absence claim.

The helper fails closed for duplicate/incomplete page identities, invalid template membership, graph population/integrity failures, graph/raw-link divergence, and directed-edge population mismatch. It performs no network or model work and always keeps `sitewide_template_flow_claim=false`, `sitewide_link_distribution_claim=false`, `sitewide_link_absence_claim=false`, and `customer_fix_created=false`.

## Preferred envelope

`semantic_graph_evidence_v9_template_zone_flow_bound` now extends the v8 B10-cluster-bound envelope with the raw-zone template flow. It does not call the semantic adapter again, so the existing two-call vector determinism/input-isolation contract remains unchanged. If the new template-zone flow cannot be verified, v9 fails the envelope closed; otherwise it preserves the underlying v8 verified/partial/not-verified state.

Preferred future integrator entry point:

```python
build_template_zone_flow_bound_semantic_graph_evidence(...)
```

The serialized integrator should consume this only as evidence. Occurrence counts, template flows, cluster representatives, semantic similarities, and source→target opportunities must not directly become final repairs, customer ranking, persistence/authority, or customer projection decisions.

## Tests added

Two focused test files add 12 regressions:

- `scanner-api/tests/test_semantic_graph_template_zone_flow.py` — 9 tests for mixed-zone preservation, repeated occurrences, directional template pairs, same-template flow, deterministic ordering, external/unassessed scope, duplicate identity fail-closed behavior, raw-link/graph divergence, and zero-link semantics.
- `scanner-api/tests/test_semantic_graph_template_zone_flow_binding.py` — 3 envelope tests for v9 transport, preservation of the two semantic-adapter calls, partial semantic coverage, and coexistence with B10 cluster evidence.

Expected Lane-B focused accounting after this checkpoint: **180 tests across 24 `test_semantic_graph*.py` files**.

Repository-native execution is not claimed in this runtime. The execution container cannot resolve `github.com`, and GitHub has no pull-request workflow run for the exact checkpoint. The required integration gate remains:

```bash
cd scanner-api
pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph*.py tests/test_semantic_graph*.py
```

CodeRabbit's commit status on draft heads is informational only when it says review was skipped; it is not test or review acceptance.

## Integration / rollback

Integration is additive. The integrator can continue consuming v8 if this evidence is not yet needed. To roll back the slice, omit the v9 wrapper and the new template-zone-flow module; no shared orchestration or persisted schema depends on either contract.
