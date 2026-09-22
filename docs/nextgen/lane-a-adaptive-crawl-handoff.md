# NextGen Agent A — Adaptive Crawl integration handoff

Issue: #322  
Draft PR: #328  
Lane branch: `agent/nextgen-adaptive-crawl-20260921`

## Scope completed in this lane

This lane adds a pure, shadow-only adaptive crawl foundation. It does not change `run_scan`, `SCAN_BUDGETS`, Standard 150, repair priority, authority/persistence, customer projection, admission, release, deployment, or production behavior.

Versioned contracts currently present:

- `adaptive_crawl_v1_shadow` — tranche planning and continuation decisions.
- `adaptive_candidate_score_v1` — per-candidate score/reasons.
- `adaptive_tranche_yield_v1` — marginal assessed-page yield telemetry.
- `adaptive_tranche_integrity_v1` — fail-closed telemetry integrity validation.
- `adaptive_benchmark_v1` — smart-500 vs blind-1000 finding/template/family/route benchmark output.
- `adaptive_benchmark_integrity_v1` — fail-closed benchmark integrity validation.
- `adaptive_benchmark_corpus_v1` — deterministic multi-site benchmark aggregation.
- `adaptive_priority_benchmark_v1` — important/high-value page coverage for smart-500 vs blind-1000 experiments.
- `adaptive_priority_benchmark_corpus_v1` — deterministic corpus aggregation of that priority-page coverage.

## Selection and Standard 150 compatibility

`select_adaptive_urls(...)` delegates the first 150 slots to the existing `select_balanced_urls(...)` implementation using the original discovery sequence before adaptive deduplication. This preserves the existing Standard-150 selection order, including its current duplicate-input behavior, for the first 150 slots. Later adaptive selection deduplicates only the deeper candidate universe.

Later-tranche ranking uses only caller-supplied evidence. It favors uncovered families, route signatures, locale-normalized path prefixes, high-value/trust classification, and optional bounded `template_novelty`, `graph_novelty`, and `finding_affinity` hints. Non-finite optional metadata is ignored. Ties preserve discovery order before URL lexical order.

The selector is bounded by already-discovered inventory, requested target, and `MAX_ADAPTIVE_TARGET == 1000`. It performs no network work and never claims that exhausting discovered URLs means the whole site is understood.

## Tranche and telemetry contract

`plan_tranche_targets(...)` defaults to 150 → 500 → 1000, truncates targets to discovered inventory, and enforces the hard 1000-page Lane-A ceiling. Optional intermediate targets remain configurable for shadow experiments.

`build_tranche_yield_telemetry(...)` separates discovered and assessed counts and measures marginal novelty for route signatures, template keys, graph edges, finding fingerprints, high-impact finding fingerprints, and high-value families assessed. Missing signals remain unknown. Invalid count relationships or regressed cumulative evidence fail closed.

`verified_continuation_decision(...)` is the recommended serialized-integrator boundary. It first verifies exact count/delta/rate integrity, then delegates to the Lane-A continuation policy. Invalid, stale, forged, non-finite, or incomplete evidence cannot authorize a deeper tranche. A large discovered inventory by itself never causes automatic expansion.

## Finding-yield benchmark

`benchmark_smart_500_vs_blind_1000(...)` compares adaptive selection of up to 500 pages with FIFO selection of up to 1000 already-discovered URLs. It reports assessed-page counts, unique finding fingerprints, finding yield per 100 pages, template/family/route coverage, page savings, and shared/smart-only/blind-only finding counts.

`validate_adaptive_benchmark(...)` rejects wrong versions, page-count cap violations, impossible coverage counts, non-finite or forged yields, inconsistent finding partitions, forged page-savings totals, inconsistent comparison states, and forged coverage/efficiency ratios.

`summarize_benchmark_corpus(...)` accepts only non-empty string site identities and only integrity-valid member results. It reports aggregate site-scoped findings, weighted finding coverage/efficiency, median site coverage, pages saved, and separate full 500-vs-1000 versus inventory-limited site counts.

## Priority-page benchmark extension

`scanner-api/app/adaptive_priority_benchmark.py` adds a second engineering-only benchmark dimension so the smart-500 experiment can measure commercially important coverage instead of judging success only by finding yield.

`build_priority_page_benchmark(...)` consumes exact selected URL identities from the smart and blind samples plus caller-declared `important_urls` and optional `high_value_urls`. It intentionally does **no URL normalization**: `/x`, `/x/`, and `/X` remain distinct evidence identities. Empty, whitespace-padded, non-string, or duplicate identities fail closed.

The helper reports:

- smart and blind assessed-page counts under explicit 500/1000 caps;
- smart pages inside and outside the blind reference sample;
- important-page coverage against priority pages actually present in the blind reference;
- high-value-page coverage against the same reference principle;
- smart-only important/high-value discoveries separately, so they cannot inflate the coverage ratio;
- `None` rather than zero when the blind reference contains no priority pages;
- `population_scope_complete=false` unconditionally, because this experiment is not proof of whole-site completeness.

`validate_priority_page_benchmark(...)` recomputes count partitions and coverage ratios, enforces the 500/1000 caps, rejects a false sitewide-completeness claim, and fails closed on malformed transported results.

`summarize_priority_benchmark_corpus(...)` deterministically aggregates only valid per-site results. It reports weighted important/high-value coverage, per-site median coverage, pages saved, and full 500-vs-1000 versus inventory-limited site counts. This is intended for the corpus experiment that decides whether smart 500 is sufficient for the default NextGen ceiling.

These priority labels are benchmark inputs only. They do not change repair priority, customer ranking, or production crawl budgets.

## Serialized integrator hook required

No shared integration surface was modified in this lane. The serialized integrator owns the only required wiring:

1. Keep the current Standard 150 `run_scan` path and production max-page budget untouched.
2. Behind an off-by-default/shadow next-generation flag, call the tranche planner only after existing bounded discovery/classification.
3. Preserve the existing first-150 selection and crawl/security/deadline behavior exactly.
4. Use `select_adaptive_urls(...)` only for later shadow tranches and only with already-discovered URLs/evidence.
5. Build cumulative telemetry from one stable evidence identity/version and call `verified_continuation_decision(...)` before any later tranche.
6. Charge all later network work to integrator-owned global request/deadline/security/robots budgets. Lane A creates no independent fetch loop.
7. For the smart-500 experiment, pass the actual smart and blind selected URL identities into `build_priority_page_benchmark(...)`; label important/high-value URLs only from evidence already owned by the integrator or connected lanes.
8. Keep all adaptive outputs operator/shadow-only until corpus acceptance establishes thresholds and customer semantics.

If the integrator cannot provide complete or integrity-valid signals, the correct result is `insufficient_evidence`, not an automatic 1000-page crawl and not a claim that the site is fully understood.

## Verification

Last branch-native repository checkpoint available before later hardening:

- `PYTHONPATH=. pytest -q tests/test_adaptive_crawl.py` → **21 passed**.
- `PYTHONPATH=. python -m py_compile app/adaptive_crawl.py tests/test_adaptive_crawl.py` → **passed**.

Later targeted evidence already recorded on this lane:

- duplicate-compatibility targeted harness → **2/2 passed**;
- benchmark-integrity/corpus exact source/test bytes → **11/11 passed** hermetically;
- corresponding `py_compile` → **passed**.

Current priority-page benchmark slice:

- `PYTHONPATH=. pytest -q tests/test_adaptive_priority_benchmark.py` → **11/11 passed** in a hermetic pure-function checkout;
- `python -m py_compile app/adaptive_priority_benchmark.py tests/test_adaptive_priority_benchmark.py` → **passed**;
- verified local Git blob SHAs match the committed GitHub blobs exactly:
  - `scanner-api/app/adaptive_priority_benchmark.py` → `8c399e530bca3be961f27a0f0b6c5a8aa6947e1e`
  - `scanner-api/tests/test_adaptive_priority_benchmark.py` → `12b4d8bca0ace5b1beee993f5470457ba7da89ca`

The branch now contains **55 focused tests**:

- 23 adaptive-crawl tests;
- 10 tranche-integrity tests;
- 11 finding-benchmark-integrity tests;
- 11 priority-page benchmark tests.

Exact-head repository commands still required:

```text
PYTHONPATH=. pytest -q \
  tests/test_adaptive_crawl.py \
  tests/test_adaptive_crawl_integrity.py \
  tests/test_adaptive_benchmark_integrity.py \
  tests/test_adaptive_priority_benchmark.py

PYTHONPATH=. python -m py_compile \
  app/adaptive_crawl.py \
  app/adaptive_crawl_integrity.py \
  app/adaptive_benchmark_integrity.py \
  app/adaptive_priority_benchmark.py \
  tests/test_adaptive_crawl.py \
  tests/test_adaptive_crawl_integrity.py \
  tests/test_adaptive_benchmark_integrity.py \
  tests/test_adaptive_priority_benchmark.py
```

**Exact blocker:** the execution container still cannot resolve `github.com`, so it cannot clone/materialize the complete branch for the full 55-test exact-head repository run. This lane therefore does not claim the full 55/55 repository suite green. A PR-triggered workflow on the exact lane head, or an integrator checkout capable of running the commands above, remains required before integration.

Full scanner regression also remains a serialized-integrator gate after Lane A is transplanted into `nextgen/integration-20260921`.

## Changed files owned by Lane A

The PR now changes exactly ten Lane-A-owned helper/test/docs files:

- `scanner-api/app/adaptive_crawl.py`
- `scanner-api/app/adaptive_crawl_integrity.py`
- `scanner-api/app/adaptive_benchmark_integrity.py`
- `scanner-api/app/adaptive_priority_benchmark.py`
- `scanner-api/tests/test_adaptive_crawl.py`
- `scanner-api/tests/test_adaptive_crawl_integrity.py`
- `scanner-api/tests/test_adaptive_benchmark_integrity.py`
- `scanner-api/tests/test_adaptive_priority_benchmark.py`
- `docs/nextgen/lane-a-adaptive-crawl-handoff.md`
- `docs/nextgen/lane-a-adaptive-crawl.md`

No serialized-integrator-owned shared surface was changed.

## Rollback

Before serialized integration, rollback is simply omitting the Lane-A commits. After integration, the feature must remain off/shadow by default; removing the integration hook returns behavior to the unchanged Standard 150 path because this lane changes no production budget or durable data.
