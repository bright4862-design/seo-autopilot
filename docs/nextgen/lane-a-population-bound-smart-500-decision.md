# Lane A — population-bound Smart-500 decision checkpoint

Issue: #322  
Draft PR: #328  
Lane: `agent/nextgen-adaptive-crawl-20260921`

## Why this slice exists

The lane already had two complementary corpus views:

- `adaptive_benchmark_bundle_corpus_v1` for Smart-500 coverage versus blind-1000, including important/high-value page coverage; and
- `adaptive_marginal_gap_corpus_v1` for the actual 500→1000 tail yield and high-impact finding evidence.

Previously those two corpus artifacts could be evaluated independently. A Smart-500 coverage result could therefore look acceptable while the blind 500→1000 tail still contained material incremental findings, or while the two corpus artifacts referred to different exact URL populations.

## New contract

`scanner-api/app/adaptive_smart_500_decision.py` adds `adaptive_smart_500_decision_v1` and `evaluate_population_bound_smart_500(...)`.

The helper is pure and shadow-only. It:

1. requires the existing population-bound benchmark corpus and strict marginal-gap corpus versions;
2. requires the marginal corpus to pass its existing integrity validator;
3. reuses `adaptive_benchmark_acceptance_v1` for aggregate finding, median-site, important-page and high-value-page coverage thresholds;
4. requires identical ordered site identities across the two corpus artifacts;
5. requires the exact Smart-500 and blind-1000 population fingerprints to match for every site;
6. requires the full-comparison site count and aggregate Smart-500 finding coverage to reconcile across corpus types;
7. evaluates aggregate and median blind 500→1000 marginal finding yield;
8. by default requires high-impact evidence to be fully observed and retains blind 1000 if Smart 500 missed any high-impact reference finding or if any high-impact finding appears only in the 500→1000 tail;
9. treats unknown, ambiguous, non-finite or identity-drifted evidence as `insufficient_evidence` rather than as zero yield or site completeness; and
10. always returns `production_budget_authorized=false` and `site_fully_understood=false`.

A positive result is only `smart_500_candidate`. It is not a production-budget authorization and does not change Standard 150.

## Default engineering thresholds

The new marginal decision defaults to:

- aggregate blind-tail finding yield ≤ 1.0 new finding per 100 assessed pages;
- median per-site blind-tail finding yield ≤ 1.0 per 100 pages; and
- fully observed high-impact evidence with zero missed/tail-only high-impact findings.

These are explicit engineering defaults and remain caller-configurable for corpus experiments. They are not wired into `run_scan` or any customer-facing budget.

## Focused regression evidence

Added `scanner-api/tests/test_adaptive_smart_500_decision.py` with 12 focused cases covering:

- positive population-bound candidate semantics;
- cross-corpus site-population drift;
- per-site population fingerprint drift;
- marginal-integrity rejection;
- insufficient and failed coverage propagation;
- aggregate and median blind-tail yield failures;
- unknown high-impact evidence;
- tail-only high-impact findings;
- cross-corpus finding-coverage reconciliation;
- invalid/non-finite threshold handling; and
- input immutability / no production authorization.

Hermetic exact-source decision harness: **12/12 passed**.  
`py_compile` for the new helper and equivalent focused test source: **passed**.

The committed helper blob is `32a83b625cba1248a38d29f30fb8a7f436713c56`.

## Exact-head repository gate still required

The lane runtime still cannot resolve `github.com` from the shell, so it cannot materialize the complete branch and execute the repository-native suite. The new test imports the real existing Lane-A modules on branch and therefore still requires an exact-head repository run before integration.

Run from `scanner-api/` when a branch checkout is available:

```text
PYTHONPATH=. pytest -q \
  tests/test_adaptive_crawl.py \
  tests/test_adaptive_crawl_integrity.py \
  tests/test_adaptive_benchmark_integrity.py \
  tests/test_adaptive_priority_benchmark.py \
  tests/test_adaptive_benchmark_bundle.py \
  tests/test_adaptive_benchmark_acceptance.py \
  tests/test_adaptive_marginal_benchmark.py \
  tests/test_adaptive_marginal_integrity.py \
  tests/test_adaptive_marginal_corpus.py \
  tests/test_adaptive_marginal_corpus_integration.py \
  tests/test_adaptive_smart_500_decision.py
```

Also run `python -m py_compile` for all ten Lane-A helper modules and eleven focused Lane-A test modules.

## Integrator handoff

No shared integration surface was changed. If the serialized integrator later runs the Smart-500 shadow experiment, the preferred decision sequence is:

1. produce the population-bound benchmark corpus;
2. produce the strict marginal-gap corpus from the same site experiments;
3. call `evaluate_population_bound_smart_500(...)` only after both are available;
4. treat `smart_500_candidate` as experiment evidence only; and
5. keep the current Standard-150 production path and global budgets unchanged until a separate serialized integration decision.

No merge, deploy, admission, authority/persistence, repair-priority, customer-projection or production change is part of this checkpoint.
