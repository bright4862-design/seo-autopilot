# Lane A — joint adaptive discovery + Fix evidence decision

Version: `adaptive_joint_evidence_decision_v1`

This slice binds the two existing Lane-A shadow acceptance families before any future integrator consumes a Smart-500 experiment recommendation:

- `adaptive_crawl_experiment_decision_v1` — whether evidence beyond the unchanged Standard 150 is valuable and whether Smart 500 is efficient enough versus the blind 1,000-page reference;
- `adaptive_fix_benchmark_acceptance_v1` — whether the exact Smart-500 population preserves enough opaque Fix evidence versus the blind 1,000-page reference.

## Why this exists

Both upstream decisions can be individually valid while still being accidentally combined across different same-count Smart-500 populations. `adaptive_joint_evidence_decision_v1` fails closed unless both positive decisions refer to the exact same sorted site IDs and exact same Smart-500 population fingerprints. It also requires matching full-comparison counts and a canonical Fix-corpus fingerprint.

A positive result is only `smart_500_joint_evidence_candidate`. It is not a crawl entitlement, production budget authorization, release acceptance, customer-visible claim, or repair-priority decision.

## Conservative outcomes

The helper propagates upstream uncertainty and reference-retention decisions without upgrading authority:

- upstream insufficient evidence → `insufficient_evidence`;
- 150→500 value not demonstrated → `standard_150_joint_reference_retained`;
- discovery evidence retains blind 1,000 → `blind_1000_joint_reference_retained`;
- Fix evidence retains blind 1,000 → `blind_1000_joint_reference_retained`;
- both evidence families positive and exact populations match → `smart_500_joint_evidence_candidate`.

Every output hard-codes:

- `population_scope_complete = false`;
- `production_budget_authorized = false`;
- `site_fully_understood = false`.

Forged upstream authority/completeness flags are rejected.

## Standard 150 preservation

This helper does not select, fetch, schedule, rank, persist, or project pages. It consumes already-produced shadow decision envelopes only, so it cannot alter Standard 150 behavior. Positive output records `standard_150_contract = unchanged_upstream_reference`; the actual Standard-150 prefix remains owned and proven by the existing selection/manifest/value contracts.

## Focused verification

The slice adds 16 focused tests covering:

- exact positive discovery+Fix population binding;
- deterministic output and JSON transport;
- same-count different site populations;
- same-site different Smart-500 populations;
- malformed population fingerprints;
- full-comparison count drift;
- malformed Fix-corpus identity;
- Standard-150 retention precedence;
- blind-1,000 retention from either evidence family;
- insufficient-evidence propagation;
- forged authority/completeness flags;
- unknown versions/decision states;
- input immutability.

Hermetic verification performed before commit:

```text
PYTHONPATH=/mnt/data/lane_a_turn11 pytest -q tests/test_adaptive_joint_evidence_decision.py
16 passed

python -m py_compile \
  app/adaptive_joint_evidence_decision.py \
  tests/test_adaptive_joint_evidence_decision.py
passed
```

## Integrator handoff

No shared-surface change is made here. If the serialized integrator later wants one combined shadow recommendation, it may call `evaluate_joint_adaptive_evidence(...)` only after producing both existing upstream decision envelopes. The returned decision must remain observational until a separate integrator-owned rollout decision explicitly authorizes any production behavior.

Do not wire this helper into `run_scan`, global budgets, repair priority, authority/persistence, customer projection, admission, release/deployment, or production from the Lane-A branch.
