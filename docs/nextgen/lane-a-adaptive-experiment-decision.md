# Lane A — End-to-end adaptive crawl experiment decision

Issue: #322  
Draft PR: #328  
Branch: `agent/nextgen-adaptive-crawl-20260921`

## Why this checkpoint exists

Lane A already had two separate shadow decisions:

1. whether the Smart 150→500 tranche adds evidence beyond the unchanged Standard 150 baseline; and
2. whether Smart 500 preserves enough evidence relative to a blind 1,000-page reference while the blind 500→1,000 tail has acceptably low marginal yield.

Those two evidence families could still be evaluated independently. `scanner-api/app/adaptive_crawl_experiment_decision.py` adds a fail-closed bridge between them so a positive Smart-500 experiment recommendation requires both stages to pass and requires the Smart-500 population identity to agree across the stages.

## Versioned contract

`adaptive_crawl_experiment_decision_v1` returns one of four engineering-only decisions:

- `smart_500_experiment_candidate` — 150→500 added enough value and the population-bound Smart-500-vs-blind-1,000 decision also passed;
- `standard_150_reference_retained` — the 150→500 tranche did not clear the configured minimum value thresholds;
- `blind_1000_reference_retained` — 150→500 was worthwhile but the 500→1,000 reference tail still contained too much evidence or failed downstream Smart-500 acceptance;
- `insufficient_evidence` — identity, integrity, version, threshold, or required evidence was missing/ambiguous.

Every result hard-codes:

- `population_scope_complete=false`;
- `production_budget_authorized=false`;
- `site_fully_understood=false`.

The helper is pure and does not schedule pages, fetch URLs, persist authority, project customer state, or change any crawl budget.

## 150→500 acceptance

By default the bridge requires the full-site 150→500 comparison corpus to show:

- at least 1.0 new finding per 100 added pages in aggregate;
- at least 1.0 median per-site new finding per 100 added pages;
- at least 0.05 absolute reference-finding coverage gain from Smart 150 to Smart 500;
- fully observed high-impact evidence for all full 150→500 comparison sites.

Thresholds are explicit caller inputs for controlled experiments. Invalid, non-finite, negative, or out-of-range ratio thresholds fail closed. High-impact observation can be explicitly relaxed for exploratory analysis, but it is required by default.

## Cross-stage population binding

A positive `smart_500_experiment_candidate` requires:

- the same ordered site population in the 150→500 value corpus and the downstream Smart-500 decision;
- the exact Smart-500 population fingerprint for every site to agree across both evidence families;
- at least one full blind-1,000 comparison site, and no more blind-1,000 full-comparison sites than full 150→500 sites.

A stale or independently generated Smart-500 artifact with a different page population therefore cannot be combined into a positive experiment result merely because aggregate counts or ratios happen to match.

## Verification in this run

The exact new helper/test bytes were exercised in a hermetic package. The focused suite passed **14/14** scenarios and both modules passed `py_compile`. Coverage includes:

- positive end-to-end Smart-500 experiment candidacy;
- aggregate, median, and coverage-gain failures retaining Standard 150;
- unknown high-impact evidence failing closed by default;
- invalid 150→500 transport and no-full-comparison evidence;
- downstream insufficient evidence;
- productive 500→1,000 tails retaining the blind-1,000 reference;
- cross-stage site identity drift;
- cross-stage Smart-500 population-fingerprint drift;
- invalid thresholds;
- explicit exploratory relaxation of the high-impact observation requirement;
- input immutability.

The branch-native exact-head repository gate is still required:

```text
cd scanner-api
PYTHONPATH=. pytest -q tests/test_adaptive_crawl_experiment_decision.py
PYTHONPATH=. python -m py_compile \
  app/adaptive_crawl_experiment_decision.py \
  tests/test_adaptive_crawl_experiment_decision.py
```

The full Lane-A gate should include this module in addition to the prior 140 focused tests, for **154 focused tests by file inventory**.

## Ownership boundary

This checkpoint does not change Standard 150 or any serialized-integrator-owned surface. In particular it does not modify `run_scan`, global budgets, repair priority, durable authority/persistence, customer projection, admission, release, deployment, workers, schema, credentials, or production. The serialized integrator remains the only owner allowed to wire any future off-by-default/shadow experiment into shared execution.
