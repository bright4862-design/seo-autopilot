# Lane B — vector-bound semantic cluster profile evidence

Issue: #323  
Draft PR: #329  
Branch: `agent/nextgen-semantic-graph-20260921`

## Purpose

This checkpoint adds a deterministic, local-only profile contract for semantic clusters without creating customer Fixes or changing repair priority, authority/persistence, `run_scan`, admission, release, deployment, or production behavior.

`scanner-api/app/semantic_graph_cluster_profile.py` consumes two already-produced Lane-B artifacts:

- `semantic_cluster_evidence_v1_vector_bound`; and
- `semantic_vector_contract_v1`.

It does **not** invoke a model, provider, crawler, or vectorizer. That is deliberate: cluster profiling must stay bound to the exact vector snapshot that already passed population, numeric, determinism, and input-isolation checks rather than triggering a third adapter call.

## Evidence contract

Version: `semantic_cluster_profile_v1_vector_bound`.

For each validated cluster the helper emits:

- exact cluster/member identity rebound to the validated vector population;
- deterministic centroid evidence;
- representative URL chosen as the member with highest cosine similarity to the centroid, with lexical URL tie-breaking;
- minimum/mean/maximum member-to-centroid similarity;
- up to eight deterministic centroid terms with signed centroid weights;
- semantic population-coverage fields carried forward unchanged;
- `sitewide_semantic_coverage_claim=false`; and
- `customer_fix_created=false`.

The representative URL is descriptive cluster evidence only. It is **not** a canonical recommendation, target page decision, repair priority input, or customer Fix.

## Fail-closed integrity checks

The helper refuses to profile evidence when:

- the vector contract/version/scope is wrong;
- semantic vector integrity, determinism, or input isolation is not verified;
- vectors are malformed/non-finite/zero-norm;
- the vector-bound cluster contract/version/scope/state is invalid;
- a cluster ID does not equal `sem_<sha256(sorted member URLs)[:12]>`;
- a declared page count differs from membership;
- cluster members are duplicated or overlap across clusters; or
- a cluster member is absent from the validated vector population.

A mathematically zero-norm centroid is kept as an explicit per-cluster `not_verified` profile rather than being converted into a false semantic representative.

## Verification

Added `scanner-api/tests/test_semantic_graph_cluster_profile.py` with 9 focused regressions covering:

1. deterministic representative and centroid-term evidence;
2. input-order invariance;
3. forged cluster-ID rejection;
4. overlapping cluster-member rejection;
5. cluster/vector population mismatch rejection;
6. zero-norm centroid handling;
7. partial semantic coverage propagation;
8. clean no-cluster behavior without a sitewide claim; and
9. fail-closed behavior when semantic vector integrity is not verified.

A hermetic execution of this new test file passed **9/9** and the module compiled successfully before publication to the lane branch.

The complete repository-native Lane-B suite must still be run on the exact branch head before integration acceptance; this checkpoint does not claim that broader gate.

## Integration handoff

The safest integration point is inside the existing single-snapshot semantic-analysis boundary, immediately after `semantic_vector_contract_v1` has produced its accepted `semantic_evidence` and `semantic_clusters(...)` has produced the vector-bound cluster artifact. Pass those two dictionaries directly to `semantic_cluster_profile_evidence(...)` while the accepted vector snapshot is still available.

Do not reconstruct vectors, invoke the adapter again, or infer cluster profiles from customer projections. Keep this evidence descriptive and feed any future customer-facing decision only through the serialized root-cause/priority/authority integration path.

No merge or deployment is authorized from this lane.
