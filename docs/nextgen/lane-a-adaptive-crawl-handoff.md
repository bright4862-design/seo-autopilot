# NextGen Agent A — Adaptive Crawl integration handoff

Issue: #322  
Draft PR: #328  
Lane branch: `agent/nextgen-adaptive-crawl-20260921`

## Scope completed in this lane

This lane adds a pure, shadow-only adaptive crawl foundation. It does not change `run_scan`, `SCAN_BUDGETS`, Standard 150, repair priority, authority/persistence, customer projection, admission, release or deployment behavior.

The helper contracts are versioned and deterministic:

- `adaptive_crawl_v1_shadow` — tranche planning and continuation decisions.
- `adaptive_candidate_score_v1` — per-candidate selection score/reasons.
- `adaptive_tranche_yield_v1` — marginal assessed-page yield telemetry.
- `adaptive_benchmark_v1` — smart-500 vs blind-1000 simulation output.
- `adaptive_tranche_integrity_v1` — fail-closed integrity validation for transported/caller-supplied tranche telemetry.

## Selection contract

`select_adaptive_urls(...)` delegates the first 150 slots to the existing `select_balanced_urls(...)` implementation using the original discovered sequence, before adaptive deduplication. A target of 150 therefore preserves the existing Standard 150 selection order exactly, including the existing sampler's behavior if discovery ever contains duplicate URL identities. For deeper targets, the same exact Standard-150 result is retained as the prefix and only the later adaptive extension operates on a unique URL universe. This prevents pre-deduplication from changing existing bucket counts/quotas and silently drifting the Standard-150 baseline.

Later-tranche ranking uses only evidence already supplied by the caller. It performs no network work. The deterministic score favors uncovered URL families, route signatures and locale-normalized top-level path prefixes, plus existing high-value/trust classification and optional bounded `template_novelty`, `graph_novelty` and `finding_affinity` hints. Locale normalization prevents translated market prefixes such as `/fr/...` and `/de/...` from being rewarded as distinct path-prefix novelty. Non-finite optional metadata (`NaN`, `+/-Infinity`) is ignored instead of affecting ranking. Ties preserve original discovery order before URL lexical order.

The selector is bounded by the number of already-discovered unique URLs available for deeper assessment, the requested target, and an explicit `MAX_ADAPTIVE_TARGET == 1000` safety ceiling. A caller asking for more than 1000 pages cannot make this lane authorize them. Raising that ceiling requires an explicit contract/version change and serialized-integrator budget review.

The selector never claims that exhausting the discovered URL set means the whole site is understood.

## Tranche and telemetry contract

`plan_tranche_targets(...)` defaults to 150 → 500 → 1000 and truncates targets to the current discovered inventory plus the hard 1000-page lane ceiling. It records both the requested ceiling and effective assessment ceiling. The candidate target sequence remains configurable so the integrator can shadow-test intermediate targets without changing selector semantics. An empty candidate-target configuration authorizes no tranche. Malformed optional candidate targets are ignored rather than raising or expanding the crawl.

`build_tranche_yield_telemetry(...)` separates discovered and assessed counts and records marginal novelty for route signatures, template keys, graph edges, finding fingerprints, high-impact finding fingerprints, and high-value families assessed.

Missing signals remain `None` and force `signal_state="insufficient_evidence"`; they are never coerced to zero. Impossible count relationships produce `signal_state="invalid_counts"` and fail closed. Cumulative evidence snapshots must remain monotonic: if a previously observed route/template/edge/finding/high-value-family disappears from the later cumulative snapshot, telemetry records the exact `regressed_signal_keys`, sets `signal_state="invalid_evidence"`, and continuation fails closed.

`continuation_decision(...)` requires the current telemetry contract version and valid count/evidence invariants before it can consider expansion. Expansion can occur only when complete observed novelty/yield crosses the shadow thresholds. A large discovered inventory by itself is not enough. The helper never produces a next target above 1000, and once the 1000-page ceiling is reached the state is `hold` with reason `adaptive_ceiling_reached`. A hold decision always keeps `site_fully_understood=false`.

`finding_fingerprints` are pre-repair evidence identifiers only. They are not final customer Fixes and do not alter repair ranking.

## Telemetry integrity boundary

`scanner-api/app/adaptive_crawl_integrity.py` adds a pure integrity layer for the boundary where telemetry may have been transported, persisted in a shadow store, or supplied by another component before continuation is considered.

`validate_tranche_telemetry(...)` fails closed unless:

- the telemetry contract version is exact;
- discovered/previous-assessed/current-assessed/pages-added counts are non-negative integers with `previous <= current <= discovered`;
- `pages_added == assessed_count - previous_assessed_count`;
- the builder's `counts_valid` and `evidence_monotonic` invariants are true;
- no regressed evidence keys are present;
- observed telemetry has every marginal delta;
- every supplied delta is a non-negative integer;
- every supplied per-100 rate is finite, non-negative, and exactly recomputable from the corresponding delta and `pages_added`.

This prevents forged, stale, malformed, `NaN`/`Infinity`, or internally inconsistent rates from authorizing a deeper crawl.

`verified_continuation_decision(...)` is the recommended serialized-integrator entry point for transported telemetry. It runs the integrity gate first; invalid telemetry returns `insufficient_evidence` with `next_target=None`. Valid telemetry delegates to the existing `continuation_decision(...)`, preserving the current Lane-A thresholds and behavior.

## Serialized integrator hook required

No shared integration surface was modified in this lane. The serialized integrator owns the only required wiring:

1. Keep the current Standard 150 `run_scan` path and `SCAN_BUDGETS["advanced"]["max_pages"] == 150` untouched.
2. Behind a new off-by-default/shadow next-generation flag, after existing discovery/classification has produced the bounded URL inventory, call `plan_tranche_targets(...)`.
3. For the first 150 assessed pages, retain the current `select_balanced_urls(...)` selection and existing crawl/security/deadline behavior exactly.
4. If shadow policy requests another tranche, call `select_adaptive_urls(...)` with already-discovered URLs and only already-available metadata. Do not pre-deduplicate the discovery sequence before calling it; the helper preserves the existing Standard-150 prefix itself.
5. After a tranche has produced accepted retained evidence, construct cumulative snapshots from one stable evidence identity/version and call `build_tranche_yield_telemetry(...)` followed by `verified_continuation_decision(...)` before authorizing any later tranche.
6. Charge all later network work to the integrator-owned global request/deadline/security/robots budgets. This lane deliberately does not create a second fetch loop or budget.
7. Keep telemetry operator/shadow-only until corpus acceptance establishes thresholds and customer semantics.

If the integrator cannot provide a complete or integrity-valid telemetry signal, the correct state is `insufficient_evidence`, not an automatic 1000-page crawl and not a claim of full understanding.

## Benchmark helper

`benchmark_smart_500_vs_blind_1000(...)` compares adaptive selection of up to 500 pages against FIFO selection of up to 1000 already-discovered URLs. It reports assessed-page count, unique finding fingerprints, finding yield per 100 assessed pages, template coverage, family coverage, route-signature coverage, page savings, and shared/smart-only/blind-only finding counts.

`smart_finding_coverage_vs_blind` is a true coverage fraction: `shared findings / blind findings`, so smart-only discoveries cannot inflate the value above 1.0. `smart_efficiency_vs_blind` remains a yield-per-100 ratio. When the blind sample has zero findings, comparison ratios that require a blind denominator are `None` with `finding_comparison_state="no_blind_findings"`.

The benchmark is a deterministic engineering instrument, not a production claim that 500 pages always outperform 1000. Corpus results should decide eventual expansion thresholds.

## Verification

Last exact repository Lane-A checkpoint before the integrity and duplicate-compatibility hardening:

- `PYTHONPATH=. pytest -q tests/test_adaptive_crawl.py` → **21 passed**.
- `PYTHONPATH=. python -m py_compile app/adaptive_crawl.py tests/test_adaptive_crawl.py` → **passed**.

The integrity slice adds `tests/test_adaptive_crawl_integrity.py` with 10 deterministic regressions covering valid delegation, forged-rate rejection, non-finite rates, malformed count types, pages-added mismatch, missing observed deltas, rate-without-delta, honest incomplete evidence, forged monotonic flags, and non-mutation.

The duplicate-compatibility slice adds 2 regressions proving (a) a Standard-150 call is byte-for-byte identical to the existing sampler even when the supplied discovery sequence contains duplicates and (b) deeper adaptive selection retains the exact existing Standard-150 result as its prefix before deduplicating later-tranche candidates. A hermetic targeted harness for those two semantics passed **2/2** in this run.

The branch now contains **23 adaptive-crawl tests + 10 integrity tests = 33 focused tests**. Exact-head repository commands still required:

```text
PYTHONPATH=. pytest -q tests/test_adaptive_crawl.py tests/test_adaptive_crawl_integrity.py
PYTHONPATH=. python -m py_compile app/adaptive_crawl.py app/adaptive_crawl_integrity.py tests/test_adaptive_crawl.py tests/test_adaptive_crawl_integrity.py
```

Exact blocker: this runtime's working container has no repository checkout and outbound DNS cannot resolve `github.com`, so it cannot clone/materialize the branch for the full repository pytest run. GitHub reports no Actions workflow run for this integration-target draft head. Therefore the two new semantics are targeted-harness verified, but the complete **33-test exact-head repository suite is not claimed green yet**. Full repository scanner regression remains a serialized-integrator gate.

## Changed files owned by Lane A

- `scanner-api/app/adaptive_crawl.py`
- `scanner-api/app/adaptive_crawl_integrity.py`
- `scanner-api/tests/test_adaptive_crawl.py`
- `scanner-api/tests/test_adaptive_crawl_integrity.py`
- `docs/nextgen/lane-a-adaptive-crawl-handoff.md`
- `docs/nextgen/lane-a-adaptive-crawl.md`

No serialized-integrator-owned shared surface was changed.

## Rollback

Before serialized integration, rollback is simply omitting the Lane-A commits. After integration, the feature must remain off/shadow by default; removing the integration hook returns behavior to the unchanged Standard 150 path because this lane changes no production budgets or durable data.
