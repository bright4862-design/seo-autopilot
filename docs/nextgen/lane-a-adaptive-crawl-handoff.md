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
- `adaptive_benchmark_corpus_v1` — deterministic multi-site finding benchmark aggregation.
- `adaptive_priority_benchmark_v1` — important/high-value page coverage for smart-500 vs blind-1000 experiments.
- `adaptive_priority_benchmark_corpus_v1` — deterministic corpus aggregation of priority-page coverage.
- `adaptive_benchmark_population_v1` — exact ordered selected-URL population fingerprint contract.
- `adaptive_benchmark_bundle_v1` — one population-bound finding + priority benchmark envelope.
- `adaptive_benchmark_bundle_corpus_v1` — deterministic corpus aggregation that rejects unpaired or drifted member populations.

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

The helper reports smart/blind assessed counts, smart pages inside/outside the blind reference, important/high-value reference coverage, smart-only priority discoveries, truthful `None` denominators when no reference priority pages exist, and `population_scope_complete=false` unconditionally.

`validate_priority_page_benchmark(...)` recomputes count partitions and coverage ratios, enforces the 500/1000 caps, rejects a false sitewide-completeness claim, and fails closed on malformed transported results.

`summarize_priority_benchmark_corpus(...)` deterministically aggregates only valid per-site results. It reports weighted important/high-value coverage, per-site median coverage, pages saved, and full 500-vs-1000 versus inventory-limited site counts.

These priority labels are benchmark inputs only. They do not change repair priority, customer ranking, or production crawl budgets.

## Population-bound paired benchmark extension

The finding and priority benchmarks are useful independently, but before this checkpoint they could be transported separately and later paired only by site identity/counts. A stale or independently generated benchmark with the same page counts could therefore be accidentally compared against a different smart/blind selected-page population.

`scanner-api/app/adaptive_benchmark_bundle.py` closes that gap without changing crawl behavior:

- `build_adaptive_benchmark_bundle(...)` derives the smart-500 and blind-1000 selected populations once from the exact benchmark candidate sequence, then builds both nested benchmark envelopes from that same experiment;
- exact URL identity is preserved; no lowercasing, slash folding, redirect inference, or URL prettification is introduced;
- duplicate discovery identities are removed only by exact string identity for the engineering benchmark universe, matching the existing finding benchmark behavior;
- whitespace-padded/non-string candidate identities fail closed instead of being silently normalized in the paired evidence contract;
- ordered smart and blind populations receive deterministic SHA-256 fingerprints under `adaptive_benchmark_population_v1`;
- `validate_adaptive_benchmark_bundle(...)` independently validates both nested envelopes, the 500/1000 caps, selected identities, candidate counts, population fingerprints, nested assessed-page counts, and smart-inside/outside-blind partitions;
- a finding or priority envelope that is internally valid but reports a different assessed-page population count is rejected by the bundle boundary;
- `summarize_adaptive_benchmark_bundle_corpus(...)` accepts only integrity-valid paired members, sorts site identities deterministically, requires nested corpus site/page populations to agree, retains per-site smart/blind population fingerprints, and never claims whole-site completeness.

This bundle is the preferred artifact for the eventual smart-500-vs-blind-1000 corpus decision because it makes the finding-yield and priority-page measurements audibly refer to the same selected populations. The SHA-256 values are deterministic integrity fingerprints, not signatures or durable authority.

## Serialized integrator hook required

No shared integration surface was modified in this lane. The serialized integrator owns the only required wiring:

1. Keep the current Standard 150 `run_scan` path and production max-page budget untouched.
2. Behind an off-by-default/shadow next-generation flag, call the tranche planner only after existing bounded discovery/classification.
3. Preserve the existing first-150 selection and crawl/security/deadline behavior exactly.
4. Use `select_adaptive_urls(...)` only for later shadow tranches and only with already-discovered URLs/evidence.
5. Build cumulative telemetry from one stable evidence identity/version and call `verified_continuation_decision(...)` before any later tranche.
6. Charge all later network work to integrator-owned global request/deadline/security/robots budgets. Lane A creates no independent fetch loop.
7. For the smart-500 experiment, prefer `build_adaptive_benchmark_bundle(...)` so finding yield and important/high-value coverage are bound to one exact smart/blind page population. Priority labels must come only from evidence already owned by the integrator or connected lanes.
8. Keep all adaptive outputs operator/shadow-only until corpus acceptance establishes thresholds and customer semantics.

If the integrator cannot provide complete or integrity-valid signals, the correct result is `insufficient_evidence`, not an automatic 1000-page crawl and not a claim that the site is fully understood.

## Verification

Last branch-native repository checkpoint available before later hardening:

- `PYTHONPATH=. pytest -q tests/test_adaptive_crawl.py` → **21 passed**.
- `PYTHONPATH=. python -m py_compile app/adaptive_crawl.py tests/test_adaptive_crawl.py` → **passed**.

Later targeted evidence already recorded on this lane:

- duplicate-compatibility targeted harness → **2/2 passed**;
- benchmark-integrity/corpus exact source/test bytes → **11/11 passed** hermetically;
- priority-page benchmark slice → **11/11 passed** in a hermetic pure-function checkout;
- corresponding targeted `py_compile` checks passed for those checkpoints.

Current population-bound bundle slice:

- an isolated pure-function harness with stubbed existing Lane-A dependencies exercised bundle construction, deterministic exact-population binding, fingerprint tamper rejection, nested population-count drift rejection, exact duplicate handling, and corpus aggregation;
- the equivalent 12 regression scenarios passed **12/12** in that harness;
- the local bundle/test copies used for the harness passed `py_compile`;
- this is targeted contract evidence only, not a claim that the exact GitHub branch-native suite has run.

The branch now contains **67 focused tests**:

- 23 adaptive-crawl tests;
- 10 tranche-integrity tests;
- 11 finding-benchmark-integrity tests;
- 11 priority-page benchmark tests;
- 12 population-bound benchmark-bundle tests.

Exact-head repository commands still required:

```text
PYTHONPATH=. pytest -q \
  tests/test_adaptive_crawl.py \
  tests/test_adaptive_crawl_integrity.py \
  tests/test_adaptive_benchmark_integrity.py \
  tests/test_adaptive_priority_benchmark.py \
  tests/test_adaptive_benchmark_bundle.py

PYTHONPATH=. python -m py_compile \
  app/adaptive_crawl.py \
  app/adaptive_crawl_integrity.py \
  app/adaptive_benchmark_integrity.py \
  app/adaptive_priority_benchmark.py \
  app/adaptive_benchmark_bundle.py \
  tests/test_adaptive_crawl.py \
  tests/test_adaptive_crawl_integrity.py \
  tests/test_adaptive_benchmark_integrity.py \
  tests/test_adaptive_priority_benchmark.py \
  tests/test_adaptive_benchmark_bundle.py
```

**Exact blocker:** the execution container still cannot resolve `github.com`, so it cannot clone/materialize the complete branch for the full 67-test exact-head repository run. This lane therefore does not claim the full 67/67 repository suite green. A PR-triggered workflow on the exact lane head, or an integrator checkout capable of running the commands above, remains required before integration.

Full scanner regression also remains a serialized-integrator gate after Lane A is transplanted into `nextgen/integration-20260921`.

## Changed files owned by Lane A

The PR now changes exactly twelve Lane-A-owned helper/test/docs files:

- `scanner-api/app/adaptive_crawl.py`
- `scanner-api/app/adaptive_crawl_integrity.py`
- `scanner-api/app/adaptive_benchmark_integrity.py`
- `scanner-api/app/adaptive_priority_benchmark.py`
- `scanner-api/app/adaptive_benchmark_bundle.py`
- `scanner-api/tests/test_adaptive_crawl.py`
- `scanner-api/tests/test_adaptive_crawl_integrity.py`
- `scanner-api/tests/test_adaptive_benchmark_integrity.py`
- `scanner-api/tests/test_adaptive_priority_benchmark.py`
- `scanner-api/tests/test_adaptive_benchmark_bundle.py`
- `docs/nextgen/lane-a-adaptive-crawl-handoff.md`
- `docs/nextgen/lane-a-adaptive-crawl.md`

No serialized-integrator-owned shared surface was changed.

## Rollback

Before serialized integration, rollback is simply omitting the Lane-A commits. After integration, the feature must remain off/shadow by default; removing the integration hook returns behavior to the unchanged Standard 150 path because this lane changes no production budget or durable data.
