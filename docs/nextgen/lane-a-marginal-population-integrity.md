# Agent A — marginal population integrity checkpoint

Issue: #322  
Draft PR: #328  
Branch: `agent/nextgen-adaptive-crawl-20260921`

## Purpose

This checkpoint hardens the existing 150 → 500 → 1000 marginal-yield benchmark without changing crawl behavior. The base `adaptive_marginal_benchmark_v1` arithmetic validator already checks deltas, yields, caps and reference coverage. The new `adaptive_marginal_population_integrity_v1` layer closes transport-integrity gaps that could otherwise let internally consistent but population-incomplete benchmark evidence pass.

Nothing here authorizes a production crawl expansion. Standard 150, `run_scan`, global budgets, repair priority, authority/persistence, customer projection, admission, release/deployment and production remain untouched.

## New contract

`scanner-api/app/adaptive_marginal_integrity.py` adds `validate_marginal_population_integrity(...)`.

It first requires the existing marginal validator to pass, then additionally requires:

- each Smart and blind checkpoint to contain exactly `min(target, candidate_count, 1000)` pages, not merely a value below the cap;
- every population fingerprint to be lowercase 64-character SHA-256 hex shape;
- unchanged inventory-limited populations to retain the same fingerprint;
- expanded populations to have a different fingerprint;
- cumulative template/family/route cardinalities never to exceed the assessed-page population;
- the final blind reference row to reconcile to the exact reference finding count, not merely a rounded `1.0` coverage value;
- when the candidate inventory is <=1000 pages, Smart and blind final evidence populations to agree exactly on finding/high-impact totals because both strategies contain the complete candidate inventory.

Every success/failure envelope keeps `production_budget_authorized=false` and `site_fully_understood=false`.

## Why this matters

The benchmark is intended to answer whether Smart 500 preserves enough evidence versus blind 1000. A forged or accidentally truncated Smart checkpoint could previously remain arithmetically self-consistent while containing fewer pages than the declared checkpoint. Likewise, a malformed fingerprint could satisfy the older length-only check, and inventory-limited repeated checkpoints could transport a different fingerprint despite representing the same page population.

This integrity layer prevents those states from being accepted as decision evidence.

## Verification

The exact committed helper bytes have Git blob SHA:

`ce073e0a028a7bafe74ee00a5c14a7c38b53c175`

The exact committed test bytes have Git blob SHA:

`44b7b54b68ecb5d2b2748d4151d8324b21db9dcc`

The exact helper bytes were compiled locally and exercised in a hermetic package across eight structural scenarios: valid population evidence, malformed fingerprint, underfilled checkpoint, impossible discovery cardinality, changed fingerprint for unchanged inventory, reused fingerprint for expanded inventory, incomplete Smart full-inventory evidence, and fail-closed propagation of a base-contract failure. Result: **8/8 passed**. The exact committed test file also passed `py_compile`.

This is targeted evidence for the new pure integrity layer. The repository-native focused suite still requires a real checkout with the branch dependencies.

## Updated focused gate

Run from `scanner-api/`:

```text
PYTHONPATH=. pytest -q \
  tests/test_adaptive_crawl.py \
  tests/test_adaptive_crawl_integrity.py \
  tests/test_adaptive_benchmark_integrity.py \
  tests/test_adaptive_priority_benchmark.py \
  tests/test_adaptive_benchmark_bundle.py \
  tests/test_adaptive_benchmark_acceptance.py \
  tests/test_adaptive_marginal_benchmark.py \
  tests/test_adaptive_marginal_integrity.py
```

plus `py_compile` for all eight Lane-A helper modules and eight focused test files.

The lane now contains **102 focused tests by file inventory**: the prior 94 plus 8 new marginal-population-integrity regressions.

## Integration handoff

The serialized integrator should treat `validate_marginal_population_integrity(...)` as the stricter acceptance boundary before using marginal benchmark evidence in any shadow corpus decision. It is pure validation only and creates no fetch loop or budget authority.

## Blocker

The execution container still cannot resolve `github.com` for a complete repository checkout, so the full exact-head repository-native 102-test gate is not claimed green here. If no PR-triggered workflow exists for the exact head, that remains the explicit integration blocker rather than a reason to weaken the evidence contract.
