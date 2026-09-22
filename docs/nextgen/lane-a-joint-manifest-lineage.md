# Lane A — joint decision to manifest tranche lineage

`adaptive_joint_manifest_lineage_v1` is a pure, shadow-only integrity helper for the Agent A adaptive crawl lane.

## Why this slice exists

The existing joint adaptive evidence decision proves that discovery/marginal evidence and Fix benchmark evidence agree on the same Smart-500 population. That decision did not itself carry the exact replay-validated 150 → 500 → 1000 manifest lineage for every site. This helper closes that transport gap before a positive Smart-500 engineering candidate is handed to the serialized integrator.

## Contract

`bind_joint_decision_to_manifest_lineage(joint_decision, lineages_by_site)` accepts only a positive `adaptive_joint_evidence_decision_v1` candidate and exact per-site `adaptive_manifest_evidence_lineage_v1` artifacts. It fails closed unless:

- the exact sorted site set matches;
- every Smart-500 population fingerprint matches the joint decision;
- Standard 150 is explicitly preserved in every lineage;
- 150/500/1000 page geometry matches the discovered candidate count, including inventory-limited sites;
- manifest checkpoint fingerprints are canonical SHA-256 identities;
- full blind-1000 comparison counts reconcile exactly;
- selection targets are strictly increasing and capped at 1,000;
- all authority/completeness flags remain false.

The output includes exact per-site Standard-150, Smart-500, and 1,000-tail population fingerprints plus a deterministic `joint_manifest_lineage_fingerprint`.

## Safety boundary

This helper does not crawl, rank repairs, persist authority, project customer results, mutate budgets, change admission, touch release/deployment, or authorize production. A valid result is experiment lineage evidence only. The serialized integrator still owns any future `run_scan` hook and all production budget decisions.

## Focused verification

Exact helper/test bytes were exercised before commit:

```text
PYTHONPATH=/mnt/data/lane_a_run11 pytest -q tests/test_adaptive_joint_manifest_lineage.py
15 passed

python -m py_compile \
  app/adaptive_joint_manifest_lineage.py \
  tests/test_adaptive_joint_manifest_lineage.py
passed
```

Regression coverage includes positive exact lineage, inventory-limited terminal populations, same-count/different Smart-500 transplantation, Standard-150 drift, tranche-geometry tampering, full-comparison count drift, site-set drift, forged authority claims, non-positive joint outcomes, malformed identities, invalid selection-target order, JSON transport, determinism, and input immutability.
