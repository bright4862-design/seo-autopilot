# Lane A — Smart-500 shadow acceptance checkpoint

Issue: #322  
Draft PR: #328  
Branch: `agent/nextgen-adaptive-crawl-20260921`

This checkpoint supplements `lane-a-adaptive-crawl-handoff.md`. It is engineering-only benchmark policy and does not authorize any production crawl budget or customer-visible behavior.

## Added contract

`scanner-api/app/adaptive_benchmark_acceptance.py` adds `adaptive_benchmark_acceptance_v1` and `evaluate_smart_500_corpus(...)`.

The helper consumes only the integrity-verified `adaptive_benchmark_bundle_corpus_v1` summary. It evaluates whether Smart 500 has enough *shadow corpus evidence* to be considered a candidate against the blind-1000 reference.

Default engineering thresholds are intentionally explicit and conservative:

- at least 10 full 500-vs-1000 comparison sites;
- aggregate finding coverage >= 0.95;
- median per-site finding coverage >= 0.90;
- important-page coverage >= 0.95;
- high-value-page coverage >= 0.95.

A passing result is named `smart_500_candidate`, never approved/released. A failed observed corpus returns `blind_1000_reference_retained`. Missing, malformed, stale-version, incomplete, non-finite, out-of-range, or internally inconsistent evidence returns `insufficient_evidence`.

Every result hard-codes:

- `production_budget_authorized = false`;
- `site_fully_understood = false`.

The helper verifies site-count partitioning, deterministic/sorted unique site identities, Smart-vs-blind page-count relationships, and truthful page savings before thresholds are considered. It does not modify `run_scan`, global budgets, repair priority, authority/persistence, customer projection, admission, release/deployment, workers, credentials, schema, or production behavior.

## Verification

The exact source/test bytes committed in this checkpoint were exercised in a hermetic local package:

```text
PYTHONPATH=. pytest -q tests/test_adaptive_benchmark_acceptance.py
13 passed

PYTHONPATH=. python -m py_compile \
  app/adaptive_benchmark_acceptance.py \
  tests/test_adaptive_benchmark_acceptance.py
passed
```

Git blob identity of the locally tested bytes matches GitHub:

- `scanner-api/app/adaptive_benchmark_acceptance.py`: `3004be411b1f15860c1745de6c29f1bda7a396df`
- `scanner-api/tests/test_adaptive_benchmark_acceptance.py`: `cacc4955fcf242b4e81a6f074ed232d31b59d398`

This raises the Lane-A focused-test inventory from 67 to **80 tests**. The complete exact-head repository suite remains required before integration; targeted hermetic evidence is not a substitute for that gate.

## Serialized integrator handoff

If/when the serialized integrator runs the Smart-500-vs-blind-1000 corpus experiment, it may feed the population-bound corpus summary into `evaluate_smart_500_corpus(...)` as an operator-only acceptance aid. It must not interpret `smart_500_candidate` as permission to change production budgets. Any actual default-budget change remains integrator-owned and requires full regression/corpus acceptance with NextGen still shadow/off until explicitly promoted through the release process.
