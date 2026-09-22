# Lane A — Fix benchmark corpus acceptance

## Scope

`adaptive_fix_benchmark_acceptance_v1` is a pure, shadow-only decision helper for the
manifest-bound Smart-500-vs-blind-1000 Fix benchmark corpus. It evaluates opaque Fix
fingerprint coverage and incremental Fix yield without assigning severity, repair
priority, customer ranking, persistence authority, or crawl entitlement.

The helper does not crawl, fetch, persist, mutate budgets, change admission, write
customer projections, or alter Standard 150. A positive decision is only an
engineering experiment candidate.

## Integrity boundary

Before threshold evaluation, the helper independently validates the transported
`adaptive_manifest_fix_benchmark_corpus_v1` artifact:

- deterministic corpus fingerprint;
- exact sorted/unique site population;
- per-site Smart/blind/binding SHA-256 population fingerprints;
- full-versus-inventory-limited site arithmetic;
- Smart/blind page and page-savings arithmetic;
- Smart/blind/shared/blind-only/Smart-only Fix partitions;
- aggregate Fix coverage and incremental Fix-yield recomputation;
- explicit `observed`, `partial`, or `not_observed` high-impact semantics;
- `standard_150_preserved=true`;
- `population_scope_complete=false`, `production_budget_authorized=false`, and
  `site_fully_understood=false`.

Tampered transport, rebound-but-inconsistent arithmetic, malformed population
identity, or forged authority fails closed before it can influence the decision.

## Shadow acceptance policy

Default engineering thresholds are deliberately conservative and configurable:

- at least 10 full 500-vs-1,000 comparison sites;
- at least 95% aggregate Smart Fix coverage versus blind 1,000;
- at least 90% median per-site Smart Fix coverage;
- at least 0.50 new Fix fingerprints per 100 pages added from Standard 150 to Smart
  500;
- at least 95% high-impact Fix coverage when high-impact evidence is required;
- high-impact evidence is required to be fully observed by default.

Possible outcomes:

- `smart_500_fix_evidence_candidate` — shadow evidence meets all configured gates;
- `blind_1000_fix_reference_retained` — evidence is valid but a coverage/yield gate
  fails;
- `insufficient_evidence` — integrity, identity, observation, denominator, corpus-size,
  or threshold configuration is inadequate.

No outcome authorizes production crawling or changes the existing Standard 150 path.

## Verification

The exact helper/test bytes for this slice were exercised in a hermetic pure-function
package:

```text
PYTHONPATH=/mnt/data/lane_a_turn11 pytest -q tests/test_adaptive_fix_benchmark_acceptance.py
15 passed

python -m py_compile \
  app/adaptive_fix_benchmark_acceptance.py \
  tests/test_adaptive_fix_benchmark_acceptance.py
passed
```

The full branch-native Lane-A suite remains a separate exact-head repository gate.
