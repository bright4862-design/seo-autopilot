# Lane A checkpoint — manifest-bound cross-evidence lineage

Branch: `agent/nextgen-adaptive-crawl-20260921`  
Draft PR: #328  
Issue: #322

## What this checkpoint adds

Lane A already had two independent replay-manifest bindings:

- `adaptive_manifest_marginal_binding_v1` proves the Smart 150/500/1000 marginal telemetry belongs to exact replay-validated tranche selections.
- `adaptive_manifest_benchmark_binding_v1` proves the Smart-500-vs-blind-1000 benchmark belongs to the same exact discovery input and Smart manifest population.

Those artifacts were individually fail-closed, but a later consumer could still receive one valid marginal binding from experiment A and one valid benchmark binding from experiment B. `scanner-api/app/adaptive_manifest_evidence_lineage.py` adds a pure cross-evidence join so the pair must reconcile before downstream experiment decisioning can treat them as one evidence lineage.

## Contract

`build_manifest_evidence_lineage(...)` requires both source bindings to be valid, shadow-only artifacts and independently checks:

- exact unique candidate count agreement;
- raw/unique/duplicate candidate arithmetic from the benchmark binding;
- exact manifest discovery-population fingerprint agreement;
- canonical lowercase SHA-256 shape for both source binding fingerprints and benchmark population fingerprints;
- strictly increasing bounded manifest selection targets;
- exact 150, 500 and 1000 marginal checkpoint identities;
- exact bounded page geometry at every checkpoint (`min(checkpoint, unique candidates)`);
- exact inventory-limited manifest target semantics;
- Smart-500 page-count agreement between marginal and benchmark evidence;
- exact blind-1000 bounded reference count;
- continued Standard-150 preservation.

The resulting `adaptive_manifest_evidence_lineage_v1` certificate contains the shared discovery identity, bounded 150/500/1000 page counts, all marginal checkpoint population fingerprints, both benchmark population fingerprints, both source binding fingerprints, and one deterministic `lineage_fingerprint` over that identity.

`validate_manifest_evidence_lineage(...)` rebuilds the artifact and rejects transported/tampered certificates.

## Safety boundary

This helper does not select or crawl pages, make network calls, persist data, change budgets, alter repair priority, write authority, project customer output, change admission, release or deployment behavior, or authorize production expansion. Every success and failure keeps:

- `population_scope_complete=false`
- `production_budget_authorized=false`
- `site_fully_understood=false`

Standard 150 remains the existing sampler-defined baseline. The helper only verifies lineage around already-produced shadow evidence.

## Focused verification

Exact committed helper/test bytes were exercised in a hermetic pure-function package:

```text
PYTHONPATH=. pytest -q tests/test_adaptive_manifest_evidence_lineage.py
17 passed

python -m py_compile \
  app/adaptive_manifest_evidence_lineage.py \
  tests/test_adaptive_manifest_evidence_lineage.py
passed
```

Coverage includes full 1,000-page references, 620-page inventory limits, sub-500 and sub-150 populations, exact duplicate transport accounting, candidate-count mismatch, discovery-fingerprint mismatch, malformed fingerprint shape, Smart-500 checkpoint drift, blind-reference drift, inventory-limited manifest-target drift, duplicate/missing checkpoints, forged authority claims, JSON transport/tamper rejection, determinism and input immutability.

The Lane-A focused inventory is now **234 tests**: prior 217 plus 17 lineage regressions.

## Exact-head repository gate

The current execution shell still cannot resolve `github.com`:

```text
git ls-remote https://github.com/bright4862-design/seo-autopilot.git HEAD
fatal: unable to access 'https://github.com/bright4862-design/seo-autopilot.git/': Could not resolve host: github.com
```

Therefore the full exact-head branch checkout and combined 234-test repository run cannot be executed from this shell. The new helper/test exact committed bytes were verified independently, but the full **234/234 branch-native repository suite is not claimed green**. A GitHub Actions run or integrator-capable checkout remains required for that gate.

## Integrator handoff

No serialized integration surface is changed here. If the integrator later wires the shadow experiment, the recommended order is:

1. build and replay-validate the tranche manifest;
2. build manifest-bound marginal telemetry;
3. build manifest-bound Smart-500/blind-1000 benchmark evidence;
4. build/validate `adaptive_manifest_evidence_lineage_v1`;
5. only then feed corpus/decision helpers with evidence carrying that reconciled lineage.

If the two evidence families do not reconcile, the correct downstream state is `insufficient_evidence`; do not expand a production crawl budget and do not claim the site is fully understood.
