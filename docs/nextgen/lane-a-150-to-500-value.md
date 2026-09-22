# Lane A — Smart 150→500 marginal-value evidence

Issue: #322  
Draft PR: #328  
Branch: `agent/nextgen-adaptive-crawl-20260921`

## Why this checkpoint exists

Lane A already measures whether Smart 500 preserves the evidence found by a blind 1,000-page reference and whether the blind 500→1,000 tail still has material yield. That does **not** answer the preceding rollout question: whether expanding beyond the unchanged Standard 150 actually adds enough new evidence to justify a Smart-500 experiment.

`scanner-api/app/adaptive_150_to_500_value.py` adds that missing, shadow-only measurement. It consumes the existing strict `adaptive_marginal_benchmark_v1` artifacts only after `adaptive_marginal_population_integrity_v1` accepts them. It performs no crawling, network work, persistence, priority composition, customer projection, or production-budget change.

## Versioned contract

`adaptive_150_to_500_value_corpus_v1` aggregates the Smart 150→500 tranche across a deterministic site corpus.

For each site it records:

- exact Smart-150 and Smart-500 assessed-page counts;
- exact ordered-population fingerprints already produced by the marginal benchmark;
- incremental pages from 150→500;
- newly observed finding fingerprints and yield per 100 added pages;
- newly observed template keys, families, and route signatures;
- Smart-150 vs Smart-500 coverage of the blind-1,000 finding reference;
- high-impact finding gain/yield only when that evidence was actually observed.

Sites with fewer than 500 discovered candidates remain visible as `inventory_limited` but do not drive the full 150→500 aggregate. If the corpus has no site with at least 500 candidates, the contract returns `insufficient_evidence`; it does not turn missing comparison evidence into a zero-yield claim.

High-impact evidence remains explicitly `observed`, `partially_observed`, `not_observed`, or `not_applicable` at corpus level. A partially observed corpus never sums known high-impact sites as if the missing sites had zero high-impact discoveries.

## Integrity boundary

`validate_150_to_500_value_corpus(...)` fails closed on:

- malformed or reordered site populations;
- forged 150/500 page arithmetic;
- malformed or inconsistent population fingerprints;
- forged aggregate finding yield or coverage;
- malformed discovery counts;
- forged high-impact yield;
- false `population_scope_complete`, `production_budget_authorized`, or `site_fully_understood` claims.

The fingerprints remain deterministic integrity identifiers, not signatures or durable authority.

## How this should be used

This artifact is engineering evidence only. The serialized integrator may later combine it with the existing population-bound Smart-500-vs-blind-1,000 decision to answer two separate questions:

1. **Does 150→500 add material value over Standard 150?** — this checkpoint.
2. **Does Smart 500 preserve enough value that the blind 500→1,000 tail is no longer worth the additional cost?** — the existing Smart-500 decision.

Neither question, separately or together, authorizes production crawl expansion. Standard 150 remains unchanged until the serialized integrator deliberately wires an off-by-default/shadow experiment and the corpus evidence supports a later product decision.

## Verification in this run

A hermetic pure-function package exercised the new corpus and validator with the same implementation logic and passed **14/14** focused scenarios, including full 150→500 aggregation, inventory-limited handling, no-full-site insufficient evidence, unknown/partial high-impact evidence, source-integrity rejection, invalid site identities, aggregate-yield tampering, budget/completeness tampering, population-fingerprint tampering, high-impact-yield tampering, and input immutability. The helper and test module also passed `py_compile` in that hermetic package.

The exact branch-native repository test remains required:

```text
cd scanner-api
PYTHONPATH=. pytest -q tests/test_adaptive_150_to_500_value.py
PYTHONPATH=. python -m py_compile \
  app/adaptive_150_to_500_value.py \
  tests/test_adaptive_150_to_500_value.py
```

The full Lane-A gate now also includes this test module in addition to the prior 126 focused tests.

**Exact blocker:** this execution container still cannot resolve `github.com` (`git ls-remote` returns `Could not resolve host: github.com`), so it cannot materialize the complete exact-head repository checkout. Do not claim the exact branch-native suite green until GitHub Actions or an integrator checkout runs it.

## Integration ownership

No shared integration surface changed. The serialized integrator remains the only owner allowed to connect this evidence to `run_scan`, global budgets, durable authority/persistence, repair priority, customer projection, admission, release, deployment, or production. The appropriate integration hook is a shadow corpus experiment using already-produced marginal benchmark artifacts; the helper itself must never schedule pages or mutate a crawl budget.
