# Lane A — shadow integrator handoff envelope

`adaptive_shadow_handoff_v1` is a pure, fail-closed handoff contract for the Agent A adaptive crawl lane.

## Why this slice exists

The lane already has a positive joint evidence decision and an exact manifest-lineage certificate, but the serialized integrator still needs one minimal artifact that proves those two outputs belong to the same shadow experiment before any integration review. This helper binds them without touching `run_scan`, global budgets, repair ranking, persistence, customer projection, admission, release, deployment, or production.

## Contract

`build_adaptive_shadow_handoff(joint_decision, joint_lineage)` accepts only:

- a positive `adaptive_joint_evidence_decision_v1` Smart-500 candidate;
- a valid `adaptive_joint_manifest_lineage_v1` certificate;
- exact matching sorted site populations;
- exact matching Smart-500 population fingerprints;
- exact matching joint-evidence and Fix-corpus fingerprints;
- exact matching full blind-1000 comparison counts;
- explicit Standard-150 preservation;
- the unchanged 150 → 500 → 1000 tranche contract;
- valid canonical SHA-256 lineage identities;
- all shadow/authority flags remaining false.

The output carries the exact Standard-150, Smart-500, and tail-1000 population fingerprints, per-site manifest-lineage fingerprints, the joint evidence identity, the Fix corpus identity, the joint lineage identity, and a deterministic `handoff_fingerprint`.

## Safety boundary

A valid handoff is **not** execution authority. It always emits:

- `production_budget_authorized=false`;
- `execution_authorized=false`;
- `population_scope_complete=false`;
- `site_fully_understood=false`;
- `requires_serialized_integrator=true`;
- `handoff_state=shadow_candidate_only`;
- `requested_integrator_action=review_only_no_automatic_expansion`.

Standard 150 remains an unchanged upstream reference. The serialized integrator remains the only owner of any eventual `run_scan` hook or global budget decision.

## Focused verification

Exact helper/test bytes were exercised before commit:

```text
PYTHONPATH=/tmp/lane_a_run12 pytest -q tests/test_adaptive_shadow_handoff.py
16 passed

python -m py_compile \
  app/adaptive_shadow_handoff.py \
  tests/test_adaptive_shadow_handoff.py
passed
```

Regression coverage includes positive exact handoff, deterministic output, JSON transport, same-count Smart-population transplantation, site-set drift, joint-evidence and Fix-corpus identity drift, full-comparison count drift, non-positive upstream decisions, Standard-150 drift, tranche-contract drift, forged authority flags, malformed lineage identity, exact Standard/tail population transport, and input immutability.
