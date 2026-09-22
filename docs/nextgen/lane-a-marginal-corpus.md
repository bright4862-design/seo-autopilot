# Agent A — marginal-gap corpus checkpoint

Issue: #322  
Draft PR: #328  
Branch: `agent/nextgen-adaptive-crawl-20260921`

## Purpose

This checkpoint adds a deterministic corpus layer over the existing 150 → 500 → 1000 marginal-yield benchmark. The goal is to make the Smart-500-vs-blind-1000 experiment answer a sharper question: across sites with a real 1,000-page reference population, how much evidence remains in the blind 500→1000 tail, and is high-impact evidence actually observed rather than silently treated as zero?

Nothing here changes Standard 150 or authorizes a larger crawl. The helper is pure/shadow-only and performs no network, persistence, scoring, admission, release or deployment work.

## New contract

`scanner-api/app/adaptive_marginal_corpus.py` adds:

- `adaptive_marginal_gap_corpus_v1`;
- `summarize_marginal_gap_corpus(...)`, which first requires every source benchmark to pass `adaptive_marginal_population_integrity_v1`;
- deterministic site ordering and explicit separation of full 500-vs-1000 sites from inventory-limited sites;
- site-scoped aggregate Smart-500 finding coverage, missed reference findings, blind-tail pages and blind-tail marginal finding yield;
- median per-site Smart-500 coverage and blind-tail finding yield, so one very large site cannot hide weak sites;
- a separate high-impact evidence state (`observed`, `partially_observed`, `not_observed`, `not_applicable`) that keeps aggregate high-impact metrics unknown unless every full-comparison site actually observed them;
- per-site Smart-500 and blind-1000 population fingerprints retained in the corpus output;
- `validate_marginal_gap_corpus(...)`, which recomputes transported counts, ratios, medians, tail yields, population classes, high-impact states and false authority/completeness claims.

Finding fingerprints are intentionally site-scoped when aggregated. The same textual fingerprint on two different sites is two independent observations; the corpus does not globally deduplicate them.

## Verification

The new helper and test file both pass `py_compile`. An isolated pure-function harness exercised the 11 new regression scenarios with a stubbed strict source-integrity boundary and passed **11/11**. This is targeted evidence for the new corpus logic only; it is not a claim that the exact branch-native repository suite ran.

The lane now contains **113 focused tests by file inventory**: the previous 102 plus 11 new marginal-corpus regressions.

Exact-head repository command still required from `scanner-api/`:

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
  tests/test_adaptive_marginal_corpus.py
```

plus `py_compile` for all nine Lane-A helper modules and nine focused test files.

## Integration handoff

For the Smart-500 corpus experiment, the serialized integrator should use this corpus summary only as shadow decision evidence after strict per-site marginal population validation. A positive finding-coverage result is not enough if high-impact evidence is only partially observed. The helper never sets production budget authority and never claims the site is fully understood.

## Blocker

The current execution environment still cannot perform a complete exact-head repository checkout, and the lane PR does not have a PR-triggered exact-head workflow gate. Therefore the full **113/113** branch-native focused suite is not claimed green. Full scanner regression remains an integration-branch responsibility after selective transplant.
