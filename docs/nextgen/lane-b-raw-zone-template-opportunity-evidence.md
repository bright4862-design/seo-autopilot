# Lane B handoff — raw-zone-bound template contextual opportunities

Checkpoint code/tests head before this handoff document: `12671524ffeeda6d9eadaa4bb383b4503d7e2e5b`.

Authoritative ownership remains `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. This slice is Agent-B-only pure evidence code. It does not modify `run_scan`, global budgets, final repair priority/customer Fix generation, authority/persistence, customer projection, admission, release/deployment, workers, credentials, schema, or production.

## Why this slice

The existing `template_contextual_internal_link_opportunity_v1_graph_bound` correctly binds source→target contextual candidates to validated template membership and reduced graph/template-flow evidence. The newer raw template-zone flow contract preserves additional evidence that the reduced graph intentionally loses: repeated link occurrences, mixed-zone observations on one directed edge, and per-zone occurrence counts.

Without an explicit binding layer, an integrator consuming a contextual candidate had to inspect two separate structures to understand whether the relevant template pair was observed primarily in navigation, listing, contextual content, or mixed zones. This slice keeps those facts together while preserving assessed-sample scope.

## New contract

`template_contextual_internal_link_opportunity_v2_raw_zone_bound`

Implemented in:

- `scanner-api/app/semantic_graph_template_zone_opportunity.py`

It consumes only already-built:

- `template_contextual_internal_link_opportunity_v1_graph_bound` evidence; and
- `template_link_zone_flow_evidence_v2_raw_observation_bound` evidence.

No semantic adapter, model, browser, network request, crawler, persistence writer, or customer projection is invoked.

For every retained source→target candidate the helper now records:

- whether the corresponding directed template-pair flow was observed in the assessed sample;
- raw observed link occurrence count for that template pair;
- deduplicated directed-edge count;
- contextual occurrence count;
- contextual directed-edge count;
- mixed-zone directed-edge count;
- full bounded zone occurrence-count map; and
- an explicit `observed_in_assessed_sample` versus `no_observed_flow_in_assessed_sample` evidence state.

Missing observed flow stays sample-scoped. `sitewide_link_absence_claim`, `sitewide_template_flow_claim`, `sitewide_link_distribution_claim`, and `customer_fix_created` remain `false`.

## Integrity behavior

The binding fails closed when transported evidence is inconsistent. Checks include:

- exact contract version/scope and verified integrity states;
- no customer/sitewide claims crossing the boundary;
- candidate count/truncation/state consistency;
- candidate source/target and template-pair identity consistency;
- exact template-flow population count;
- unique directed template-pair flow identity;
- non-negative occurrence/edge/page metrics;
- exact per-zone occurrence sum equals declared occurrence count;
- exact strongest-zone edge-count sum equals declared directed-edge count;
- contextual occurrence count agrees with the contextual zone bucket;
- contextual/mixed edge counts do not exceed total directed edges;
- contextual edge count does not exceed contextual occurrences;
- full flow edge/occurrence totals agree with the top-level declaration; and
- candidate `observed_template_flow_present` agrees with the raw-zone flow population.

A contradictory transport therefore produces `state=not_verified` rather than emitting enriched candidates.

## Preferred additive envelope

`semantic_graph_evidence_v10_template_zone_opportunity_bound`

Implemented in:

- `scanner-api/app/semantic_graph_evidence_template_zone_opportunity_bound.py`

It extends `semantic_graph_evidence_v9_template_zone_flow_bound`, reuses the existing template-aware contextual candidates and raw template-zone flow, and adds:

- `raw_zone_template_contextual_opportunity_version`; and
- `raw_zone_template_contextual_internal_link_opportunities`.

The wrapper does not invoke the semantic vectorizer/provider again. The existing two-call determinism/input-isolation boundary remains owned below v9. A failed raw-zone opportunity binding fails the v10 envelope closed; otherwise the prior verified/partial state is preserved.

## Focused regressions

New test files:

- `scanner-api/tests/test_semantic_graph_template_zone_opportunity.py` — 8 contract/integrity regressions.
- `scanner-api/tests/test_semantic_graph_template_zone_opportunity_binding.py` — 3 envelope/composition regressions.

This raises expected Lane-B focused accounting from 180 tests across 24 files to **191 tests across 26 `test_semantic_graph*.py` files**.

Coverage includes raw occurrence/mixed-zone enrichment, sample-scoped zero flow, forged version rejection, unverified raw-link rejection, duplicate flow identity rejection, occurrence/edge total divergence, candidate-vs-flow presence divergence, no extra vectorizer calls at v10, mixed non-contextual upgrade evidence, and preservation of partial semantic coverage.

## Verification performed in this environment

Repository-native checkout remains unavailable because the execution environment cannot resolve `github.com` over Git. Therefore exact-head 191/191 pytest is **not claimed** here.

Performed locally against the authored pure helper contract:

- hermetic focused helper regression run: **8/8 passed**;
- `py_compile` for the two new application modules: **PASS**;
- Python syntax compilation for both new test files: **PASS**.

Required branch-native gate when GitHub checkout/CI is available:

```bash
cd scanner-api
pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph*.py tests/test_semantic_graph*.py
```

## Integrator handoff

When the serialized integrator is ready to consume the complete Lane-B package, prefer:

`build_template_zone_opportunity_bound_semantic_graph_evidence(...)`

Treat all semantic/template/link-zone/cannibalization/near-duplicate/opportunity structures as descriptive evidence only. They are inputs to later root-cause/priority integration, not final customer Fixes or direct ranking decisions.

Rollback is additive: ignore/remove the v10 wrapper and continue consuming v9. No persisted schema, authority bytes, production route, admission behavior, deployment manifest, or release configuration is changed by this lane slice.
