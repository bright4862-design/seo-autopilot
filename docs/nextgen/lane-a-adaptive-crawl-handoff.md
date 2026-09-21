# NextGen Agent A — Adaptive Crawl integration handoff

Issue: #322  
Draft PR: #328  
Lane branch: `agent/nextgen-adaptive-crawl-20260921`

## Scope completed in this lane

This lane adds a pure, shadow-only adaptive crawl foundation. It does not change `run_scan`, `SCAN_BUDGETS`, Standard 150, repair priority, authority/persistence, customer projection, admission, release or deployment behavior.

The helper contract is versioned and deterministic:

- `adaptive_crawl_v1_shadow` — tranche planning and continuation decisions.
- `adaptive_candidate_score_v1` — per-candidate selection score/reasons.
- `adaptive_tranche_yield_v1` — marginal assessed-page yield telemetry.
- `adaptive_benchmark_v1` — smart-500 vs blind-1000 simulation output.

## Selection contract

`select_adaptive_urls(...)` intentionally delegates the first 150 slots to the existing `select_balanced_urls(...)` implementation. A target of 150 therefore returns the existing Standard 150 selection order exactly. Only targets above 150 enter the new greedy extension logic.

Later-tranche ranking uses only evidence already supplied by the caller. It performs no network work. The deterministic score favors uncovered URL families, route signatures and top-level path prefixes, plus existing high-value/trust classification and optional bounded `template_novelty`, `graph_novelty` and `finding_affinity` hints. Ties preserve original discovery order before URL lexical order.

The selector is bounded by the number of already-discovered URLs, the requested target, and an explicit `MAX_ADAPTIVE_TARGET == 1000` safety ceiling. A caller asking for more than 1000 pages cannot make this lane authorize them. Raising that ceiling requires an explicit contract/version change and serialized-integrator budget review.

The selector never claims that exhausting the discovered URL set means the whole site is understood.

## Tranche and telemetry contract

`plan_tranche_targets(...)` defaults to 150 → 500 → 1000 and truncates targets to the current discovered inventory plus the hard 1000-page lane ceiling. It records both the requested ceiling and effective assessment ceiling. The candidate target sequence remains configurable so the integrator can shadow-test 150 → 300/500 → 750/1000 without changing selector semantics. An empty candidate-target configuration authorizes no tranche.

`build_tranche_yield_telemetry(...)` separates discovered and assessed counts and records marginal novelty for:

- route signatures;
- template keys;
- graph edges;
- finding fingerprints;
- high-impact finding fingerprints;
- high-value families assessed.

Missing signals remain `None` and force `signal_state="insufficient_evidence"`; they are never coerced to zero. Impossible count relationships, such as assessed pages exceeding the discovered inventory or a decreasing assessed count, produce `signal_state="invalid_counts"` and fail closed. `continuation_decision(...)` cannot expand on invalid telemetry.

`continuation_decision(...)` can expand only when observed novelty/yield crosses the shadow thresholds. A large discovered inventory by itself is not enough. It never produces a next target above 1000, and once the 1000-page ceiling is reached the state is `hold` with reason `adaptive_ceiling_reached`. A hold decision always keeps `site_fully_understood=false`.

`finding_fingerprints` are pre-repair evidence identifiers only. They are not final customer Fixes and do not alter repair ranking.

## Serialized integrator hook required

No shared integration surface was modified in this lane. The serialized integrator owns the only required wiring:

1. Keep the current Standard 150 `run_scan` path and `SCAN_BUDGETS["advanced"]["max_pages"] == 150` untouched.
2. Behind a new off-by-default/shadow next-generation flag, after existing discovery/classification has produced the bounded URL inventory, call `plan_tranche_targets(...)`.
3. For the first 150 assessed pages, retain the current `select_balanced_urls(...)` selection and existing crawl/security/deadline behavior exactly.
4. If shadow policy requests another tranche, call `select_adaptive_urls(...)` with already-discovered URLs and only already-available metadata. Do not let the helper schedule or fetch URLs itself.
5. After a tranche has produced accepted retained evidence, construct a snapshot from existing evidence and call `build_tranche_yield_telemetry(...)` + `continuation_decision(...)` before authorizing any later tranche.
6. Charge all later network work to the integrator-owned global request/deadline/security/robots budgets. This lane deliberately does not create a second fetch loop or budget.
7. Keep telemetry operator/shadow-only until corpus acceptance establishes thresholds and customer semantics.

If the integrator cannot provide a complete telemetry signal, the correct state is `insufficient_evidence`, not an automatic 1000-page crawl and not a claim of full understanding. If discovered/assessed counters are inconsistent, the correct state is `invalid_counts` and no expansion should occur.

## Benchmark helper

`benchmark_smart_500_vs_blind_1000(...)` compares adaptive selection of up to 500 pages against FIFO selection of up to 1000 already-discovered URLs. It reports assessed-page count, unique finding fingerprints, finding yield per 100 assessed pages, template coverage, family coverage, route-signature coverage, page savings, and shared/smart-only/blind-only finding counts.

When the blind sample has zero findings, comparison ratios are `None` with `finding_comparison_state="no_blind_findings"`; the helper no longer fabricates a denominator merely to produce a numeric ratio.

The benchmark is a deterministic engineering instrument, not a production claim that 500 pages always outperform 1000. Corpus results should decide the eventual expansion thresholds.

## Verification

Focused isolated verification for the current lane behavior:

- `PYTHONPATH=. pytest -q tests/test_adaptive_crawl.py` → **15 passed**.
- `PYTHONPATH=. python -m py_compile app/adaptive_crawl.py tests/test_adaptive_crawl.py` → **passed**.

The isolated harness mirrors the current `sampling.py` behavior needed by this pure module because the automation container cannot resolve GitHub over external DNS. Repository CI on the serialized integration branch remains the authoritative full-environment verification. The lane has not run, merged or deployed any production scanner.

New hardening regressions cover:

- exact Standard-150 selection equality;
- deterministic 500-page extension;
- hard 1000-page selector/planner ceiling even when callers request more;
- configurable 300/750 shadow tranches without allowing >1000;
- empty tranche configuration authorizing nothing;
- unknown telemetry staying unknown;
- invalid discovered/assessed count relationships failing closed;
- no continuation beyond the 1000-page ceiling;
- partial discovered inventory expanding only to the available bound;
- benchmark ratio honesty when blind-1000 observes zero findings.

## Changed files owned by Lane A

- `scanner-api/app/adaptive_crawl.py`
- `scanner-api/tests/test_adaptive_crawl.py`
- `docs/nextgen/lane-a-adaptive-crawl-handoff.md`
- `docs/nextgen/lane-a-adaptive-crawl.md`

No serialized-integrator-owned shared surface was changed.

## Rollback

Before serialized integration, rollback is simply omitting the Lane-A commits. After integration, the feature must remain off/shadow by default; removing the integration hook returns behavior to the unchanged Standard 150 path because this lane changes no production budgets or durable data.
