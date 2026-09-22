# Agent A — marginal yield benchmark checkpoint

Issue: #322  
Draft PR: #328  
Branch: `agent/nextgen-adaptive-crawl-20260921`

## Purpose

This checkpoint adds a pure engineering benchmark for the exact question the Lane-A experiment needs to answer: what does each additional tranche actually discover, and how much Fix/high-impact yield remains in the blind 500→1000 tail?

Nothing in this checkpoint authorizes a production crawl budget or changes Standard 150. It performs no network, persistence, authority, repair-priority, customer-projection, admission, release, deployment, worker, credential, schema, or production work.

## New contracts

`scanner-api/app/adaptive_marginal_benchmark.py` adds:

- `adaptive_marginal_benchmark_v1` — deterministic Smart and blind/FIFO marginal-yield curves at 150, 500 and 1000 checkpoints;
- `adaptive_marginal_gap_v1` — a decision-oriented summary of the Smart-500 gap versus the blind-1000 reference.

For each checkpoint the curve records:

- exact assessed-page and incremental-page counts;
- a deterministic selected-population fingerprint;
- newly discovered unique finding fingerprints and yield per 100 added pages;
- optional high-impact finding fingerprints and yield per 100 added pages;
- newly discovered templates, families and route signatures plus cumulative counts;
- cumulative reference findings covered and coverage against the blind-1000 reference;
- explicit `no_incremental_pages` when an inventory-limited site cannot supply another tranche.

Unknown high-impact evidence remains `not_observed`/`None`; it is never converted to a zero. Empty blind-reference finding sets likewise produce unknown coverage rather than a fake 0% result.

The Smart curve uses the existing deterministic Lane-A selector. The blind curve is the exact FIFO reference population. URL identities are exact and whitespace-padded/non-string identities fail closed rather than being normalized. Exact duplicates are deduplicated deterministically for the benchmark candidate universe.

## Integrity boundary

`validate_marginal_yield_benchmark(...)` fails closed on:

- contract/checkpoint drift;
- false sitewide-population claims;
- candidate/reference/inventory count mismatches;
- page-cap and page-delta inconsistencies;
- malformed population fingerprints;
- forged finding/high-impact deltas, yields or reference coverage;
- forged template/family/route marginal discovery deltas;
- high-impact metrics transported when high-impact evidence was not observed;
- blind-reference totals that do not reconcile with the final blind-1000 row.

The validator deliberately does not claim a cryptographic signature or durable authority. Population hashes are deterministic engineering integrity fingerprints only.

## Smart-500 gap summary

`summarize_smart_500_gap(...)` exposes the most decision-relevant measurements without making a budget decision:

- Smart-500 coverage of blind-1000 reference findings;
- number of blind-reference findings still missed by Smart 500;
- blind 500→1000 tail pages;
- new unique findings and high-impact findings introduced by that tail;
- marginal tail yield per 100 pages;
- `production_budget_authorized=false` and `site_fully_understood=false` unconditionally.

This should be paired with the existing population-bound finding/priority benchmark bundle and shadow acceptance policy. The serialized integrator remains the only owner that can later decide whether any production budget changes.

## Verification

The exact source/test text prepared for this checkpoint was exercised in a hermetic Python package with Lane-A-compatible stub dependencies:

```text
PYTHONPATH=. pytest -q tests/test_adaptive_marginal_benchmark.py
14 passed
```

and:

```text
python -m py_compile app/adaptive_marginal_benchmark.py tests/test_adaptive_marginal_benchmark.py
passed
```

The 14 regressions cover deterministic 150/500/1000 curves, inventory-limited sites, unknown high-impact evidence, empty reference findings, malformed URL identities, exact duplicate handling, blind-tail gap reporting, forged page deltas, forged finding yield, forged marginal template discovery, false reference coverage, unexpected high-impact metrics, reference-page tampering and input immutability.

This is targeted pure-function evidence. The complete exact-head repository suite still needs to run with the real repository dependencies before integration acceptance.

## Required exact-head gate

Run from `scanner-api/`:

```text
PYTHONPATH=. pytest -q \
  tests/test_adaptive_crawl.py \
  tests/test_adaptive_crawl_integrity.py \
  tests/test_adaptive_benchmark_integrity.py \
  tests/test_adaptive_priority_benchmark.py \
  tests/test_adaptive_benchmark_bundle.py \
  tests/test_adaptive_benchmark_acceptance.py \
  tests/test_adaptive_marginal_benchmark.py
```

and the matching `py_compile` gate for all seven Lane-A helper modules and seven focused test files.

The lane now contains 94 focused tests by file inventory: the prior 80 plus these 14 new regressions.

## Integration handoff

The serialized integrator may later call `build_marginal_yield_benchmark(...)` only in an off-by-default/shadow benchmark path using already-discovered candidate/evidence data. It must not create an independent fetch loop. The helper's Smart-500 gap is engineering evidence only and cannot change `run_scan`, global scan budgets, repair priority, authority/persistence, customer projection, admission, release, deployment, workers, or production behavior.

## Blocker

There is still no PR-triggered exact-head workflow for this integration-target draft, so the complete 94-test exact-head repository suite is not claimed green in this checkpoint. Full scanner regression remains a serialized-integrator gate after transplant.
