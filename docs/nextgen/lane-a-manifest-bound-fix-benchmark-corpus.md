# Lane A — manifest-bound Fix benchmark corpus

## Scope

`adaptive_manifest_fix_benchmark_corpus_v1` aggregates transported per-site `adaptive_manifest_fix_benchmark_v1` artifacts for shadow evaluation of Smart 500 versus blind 1,000. It is pure and deterministic. It performs no crawl, network fetch, repair prioritization, persistence, customer projection, budget mutation, admission, release, deployment, or production write.

The corpus helper complements the existing per-site Fix benchmark by making multi-site Fix evidence comparable without weakening Standard 150 or inventing sitewide completeness.

## Member validation

Before aggregation, each per-site benchmark is checked for:

- exact version and deterministic binding fingerprint;
- valid SHA-256 population fingerprints;
- raw/unique/duplicate candidate arithmetic;
- Standard-reference, Smart-500, and blind-1000 page caps;
- page-savings and incremental-page arithmetic;
- Smart/blind/shared/blind-only/Smart-only Fix partitions;
- Smart Fix coverage and incremental Fix-yield recomputation;
- observed versus not-observed high-impact evidence semantics;
- `standard_150_preserved=true`;
- `population_scope_complete=false`, `production_budget_authorized=false`, and `site_fully_understood=false`.

A member with transport tampering, recomputed-but-inconsistent arithmetic, malformed fingerprints, or forged authority is rejected before it can influence corpus metrics.

## Corpus telemetry

The deterministic corpus output sorts strict unique site identities and reports:

- full 500-vs-1,000 and inventory-limited site counts;
- Smart/blind pages and pages saved;
- site-scoped Smart, blind, shared, blind-only, and Smart-only Fix fingerprint totals;
- weighted Smart Fix coverage versus blind plus median per-site coverage;
- incremental Smart pages and site-scoped Fix fingerprints beyond Standard, with Fix yield per 100 added pages;
- explicit `observed`, `partial`, or `not_observed` high-impact evidence state;
- per-site Smart/blind population and benchmark binding fingerprints;
- a deterministic corpus fingerprint.

Fix identities remain opaque evidence fingerprints. The helper does not assign repair severity, priority, customer ranking, or production entitlement.

## Standard 150 boundary

The corpus can only accept members that preserve the existing Standard reference and keep all authority/completeness flags false. It does not select pages itself and cannot alter the existing Standard 150 path.

## Verification

Exact helper/test bytes were exercised in a hermetic pure-function package:

```text
PYTHONPATH=/mnt/data/lane_a_slice pytest -q tests/test_adaptive_fix_benchmark_corpus.py
14 passed

python -m py_compile \
  app/adaptive_fix_benchmark_corpus.py \
  tests/test_adaptive_fix_benchmark_corpus.py
passed
```

The exact helper/test Git blob SHAs used by that run are recorded in PR #328. Full exact-head repository verification remains a separate gate.
