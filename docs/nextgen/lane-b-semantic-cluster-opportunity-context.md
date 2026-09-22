# Lane B handoff — semantic-cluster context for internal-link opportunities

## Scope

This checkpoint stays entirely inside the Agent B ownership boundary in `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

It binds already-produced weighted contextual source→target internal-link candidates to the already-validated semantic-cluster profile. It does **not** create customer Fixes, set repair priority, write authority/persistence, modify customer projection, touch `run_scan`, alter admission/workers/schema/credentials, or change release/deployment/production behavior.

## New evidence contract

`scanner-api/app/semantic_graph_opportunity_cluster_context.py` adds:

- `template_contextual_internal_link_opportunity_v5_semantic_cluster_bound`
- deterministic source/target semantic-cluster membership for each retained contextual candidate
- explicit candidate relation states: `same_cluster`, `different_clusters`, `source_cluster_only`, `target_cluster_only`, and `unclustered_pair`
- source/target cluster profile state and representative URL when verified
- explicit booleans showing whether either candidate endpoint is the deterministic cluster representative
- transported semantic-vector coverage and pair-population completeness from the validated cluster profile
- preservation of upstream candidate truncation rather than treating the retained candidate sample as complete

The helper validates the v4 weighted-route envelope before use, including graph/neighborhood integrity, route scope, candidate counts/truncation, unique directed candidate identities, and all sitewide-claim guards. It separately validates the cluster-profile envelope, rejects overlapping cluster membership, verifies profile counts/member counts/representative membership, and fails closed on a `not_verified` cluster profile.

Cluster membership remains descriptive semantic evidence. A page that is not present in a qualifying semantic cluster is represented as unclustered within the accepted vector population; that does **not** establish a sitewide topic or coverage claim. `sitewide_semantic_coverage_claim`, sitewide reachability/orphan/link-absence/template-flow/distribution claims, and `customer_fix_created` remain false.

## Preferred additive envelope

`scanner-api/app/semantic_graph_evidence_cluster_context_bound.py` adds:

- `semantic_graph_evidence_v14_cluster_context_opportunity_bound`

v14 extends the existing v13 weighted-route envelope. It consumes only the already-produced weighted-route candidate sample and semantic-cluster profile, so it adds **no semantic vectorizer/model/provider invocation**. The existing two-call semantic adapter determinism/input-isolation boundary is preserved.

A cluster-context integrity failure fails the v14 envelope closed. An independently existing v13 failure remains authoritative even when cluster-context evidence itself is still internally verified and descriptive.

## Focused regressions

Two new test files add **14 focused regressions**:

- `scanner-api/tests/test_semantic_graph_opportunity_cluster_context.py` — 11 tests
- `scanner-api/tests/test_semantic_graph_cluster_context_binding.py` — 3 tests

Coverage includes:

- same-cluster candidate annotation and representative identity
- different-cluster candidate annotation
- explicit unclustered-pair and one-sided-cluster states
- zero-candidate verified behavior
- candidate-truncation disclosure
- overlapping cluster-member rejection
- duplicate directed candidate rejection
- forged candidate-population-completeness rejection
- not-verified cluster-profile rejection
- sitewide semantic-coverage guard rejection
- v14 envelope composition without a third semantic-vectorizer call
- no-semantic-candidate composition
- preservation of an underlying v13 seed-integrity failure

Based on the preceding Lane-B checkpoint of 233 focused tests across 32 semantic-graph test files, the expected Lane-B accounting is now **247 tests across 34 `test_semantic_graph*.py` files**.

Available verification for this slice:

- `python -m py_compile` for both new application modules and both new test files: PASS;
- hermetic helper regressions: **11/11 passed**.

The hermetic helper run validates the new pure binding logic but does not replace the exact-head repository-native suite. The exact integration gate remains:

```bash
cd scanner-api
python -m pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph*.py tests/test_semantic_graph*.py
```

Do not claim the full 247-test exact-head suite green until those commands or equivalent exact-head CI actually pass.

## Integrator guidance

When the serialized integrator is ready to consume Lane B, prefer `build_cluster_context_bound_semantic_graph_evidence(...)` as the additive full evidence envelope. Treat semantic-cluster relation, representative identity, weighted routes, route/link-zone composition, semantic similarity, template evidence, near-duplicate/cannibalization candidates, money-page reachability, and source→target opportunities as descriptive assessed-sample evidence only.

Do not turn `same_cluster` or `different_clusters` directly into a customer Fix, final priority/ranking, canonical choice, authority/persistence decision, customer projection, admission decision, release gate, deployment action, or production behavior. Preserve upstream semantic-coverage and candidate-truncation fields so cluster context is never represented as a complete sitewide topic map when it is not.

No merge or deployment is authorized from this lane.
