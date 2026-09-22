# Lane B — semantic-cluster derivation integrity hardening

## Scope

This checkpoint stays entirely inside the NextGen Agent B Semantic Graph lane defined by `docs/nextgen/2026-09-21-parallel-engineering-lanes.md`.

It does not create customer Fixes and does not modify `run_scan`, global scan budgets, final repair priority/customer scoring, authority/persistence, customer projection, admission, release/deployment, worker controls, credentials, schema, or production behavior.

## Gap closed

`semantic_cluster_profile_v1_vector_bound` already required cluster members to exist in the exact semantic vector snapshot and validated cluster IDs, page counts, duplicate members, determinism, and input isolation. However, a transported cluster partition could still be forged while remaining internally self-consistent: a caller could group valid vector-population URLs into a different connected component, preserve valid `sem_<hash>` identities, and still obtain verified profile evidence.

That is now fail-closed.

Before any centroid, representative URL, similarity range, or centroid-term evidence is emitted, `semantic_cluster_profile_evidence(...)` independently revalidates:

- finite numeric cluster threshold in `[0, 1]` with booleans rejected;
- declared `vectorized_pages` exactly equals the accepted sealed vector population;
- `pair_scan_complete is True`;
- non-negative integer `qualifying_pair_count`;
- the exact qualifying semantic-pair count recomputed from the sealed vector snapshot;
- the exact connected-component cluster partition recomputed from those qualifying pairs; and
- candidate/no-candidate state consistency with the recomputed partition.

The recomputation uses the same deterministic semantic-pair boundary as the Lane-B cluster producer, including the threshold tolerance and connected-component semantics. Transported cluster order and member order remain irrelevant; evidence is canonicalized before comparison.

A valid member set with a forged grouping now fails with `semantic_cluster_derivation_mismatch`. Forged pair counts, incomplete pair scans, vectorized-page counts, invalid thresholds, and inconsistent candidate states each fail with explicit reasons before profile evidence is produced.

## Regressions

`scanner-api/tests/test_semantic_graph_cluster_profile.py` now builds baseline cluster evidence through the real deterministic `semantic_clusters(...)` producer and adds four new derivation-integrity regressions:

1. a valid-population but threshold-inconsistent forged partition fails closed;
2. a forged qualifying-pair count fails closed;
3. an incomplete semantic pair scan cannot produce cluster profiles; and
4. a forged vectorized-page count or invalid threshold cannot produce profile evidence.

The existing cluster-profile tests were also converted from hand-authored incomplete cluster envelopes to authentic producer-shaped metadata, so valid profile tests exercise the same threshold/vectorized-pages/pair-count contract used by the analysis bundle.

Based on the preceding checkpoint of 144 focused tests across 20 Lane-B semantic-graph test files, the expected focused total is now **148 tests across the same 20 files**.

## Verification

A hermetic algorithmic check passed for the new derivation boundary, covering:

- a three-page connected component at threshold `0.39`;
- a two-page connected component plus an unrelated page at threshold `0.9`; and
- a single-vector no-cluster case.

The current execution container still cannot resolve `github.com` for a branch-native checkout, so this checkpoint does **not** claim the complete exact-head 148-test repository suite green.

Exact integration gate:

```bash
cd scanner-api
pytest -q tests/test_semantic_graph*.py
python -m py_compile app/semantic_graph*.py tests/test_semantic_graph*.py
```

Only claim exact-head green after that command or an exact-head CI run passes.

## Integrator handoff

No integration surface changed. The existing preferred `semantic_analysis_bundle_v3_cluster_profile_bound` and `semantic_graph_evidence_v7_cluster_profile_bound` automatically inherit the stricter profile integrity boundary because they already call `semantic_cluster_profile_evidence(...)` on the sealed semantic snapshot.

Treat cluster representatives, centroid terms, semantic clusters, cannibalization candidates, near-duplicate candidates, template/link-zone evidence, and source-to-target link opportunities as descriptive bounded evidence only. They must not become final customer Fixes or final repair priority without serialized integrator authority and acceptance logic.
