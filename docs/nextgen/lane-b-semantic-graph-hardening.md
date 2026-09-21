# Agent B semantic-graph hardening checkpoint — 2026-09-21

Branch: `agent/nextgen-semantic-graph-20260921`
Draft PR: #329
Issue: #323

This checkpoint stays within the Lane-B ownership boundary. It does not change
`run_scan`, global scan budgets, final repair priority, customer Fix generation,
authority/persistence, Base44 projection, admission, release, deployment, or
production behavior.

## What changed

The first semantic-graph checkpoint bounded returned candidate lists at 250, but
`semantic_clusters`, cannibalization filtering, and internal-link opportunity
filtering reused that already-truncated public pair list. On sufficiently dense
semantic corpora this could make downstream evidence incomplete: a valid pair
ranked after the first 250 public pair rows might never be considered.

This checkpoint separates **public output bounding** from **analysis coverage**:

- semantic pair generation is now a deterministic iterator over the entire
  bounded assessed corpus (maximum 1,000 pages);
- public similarity output remains capped at 250 rows, but now reports the full
  `qualifying_pair_count` and an explicit `pairs_truncated` flag;
- semantic clustering consumes every qualifying pair and reports
  `pair_scan_complete=True`, so cluster membership no longer depends on the
  public pair-output cap;
- cannibalization analysis scans every qualifying semantic pair before
  usability/indexability/near-duplicate filtering and reports candidate counts;
- internal-link opportunity analysis likewise scans the full bounded semantic
  pair set before filtering/ranking;
- near-duplicate candidate output is now memory-bounded while preserving full
  pair coverage and reporting the full candidate count;
- all customer-facing candidate outputs remain capped at 250 and remain evidence
  only, never final Fixes.

The accepted-HTML link-zone adapter was also hardened so hidden/inert links and
non-HTTP(S) hrefs cannot influence link-zone evidence. Repeated sibling-link
counts now count only visible/navigable HTTP(S) anchors, preventing hidden menu
markup from incorrectly promoting a contextual container to `listing`.

## Focused verification from the prior checkpoint

Executed from an isolated reconstruction of the lane-owned scanner package:

```text
PYTHONPATH=. pytest -q tests/test_semantic_graph.py tests/test_semantic_graph_html.py
.................                                                        [100%]
17 passed in 0.42s

python -m py_compile app/semantic_graph.py app/semantic_graph_html.py \
  tests/test_semantic_graph.py tests/test_semantic_graph_html.py
PASS
```

Those regressions prove:

- a 260-page fully connected semantic cluster remains one 260-page cluster even
  though public pair output truncates at 250 rows;
- cannibalization can still find an eligible pair ranked beyond 250 ineligible
  higher-order/public pair rows;
- internal-link opportunity analysis can still find valid directed opportunities
  beyond that same public pair cap;
- near-duplicate output remains capped while reporting full candidate coverage;
- hidden, inert, `mailto:`, `javascript:`, and `tel:` anchors are excluded from
  accepted link-zone observations;
- hidden anchors do not inflate listing sibling counts.

## 2026-09-22 evidence-truthfulness hardening

A serialized-integration review identified one material overclaim in
`cannibalization_candidates(...)`: a semantic/indexable pair with missing B10
main-content shingle evidence could still be emitted with
`near_duplicate_excluded=True` and the reason
`distinct_indexable_pages_share_local_semantic_intent`. In that case the lane had
not actually verified that the pages were distinct rather than near duplicates.

The lane now fails closed at that evidence boundary:

- verified B10 shingle pairs at or above the duplicate threshold are filtered and
  counted in `near_duplicate_filtered_count`;
- verified B10 shingle pairs below the threshold are emitted with
  `near_duplicate_comparison_state="verified_distinct"`, an observed similarity,
  and `near_duplicate_exclusion_verified=True`;
- pairs lacking verified B10 evidence remain only semantic cannibalization
  candidates and explicitly carry
  `near_duplicate_comparison_state="not_verified"`,
  `near_duplicate_similarity=None`, and
  `near_duplicate_exclusion_verified=False`;
- aggregate verified/not-verified duplicate-comparison counts are exposed so the
  integrator can preserve evidence coverage rather than treating every candidate
  as equally verified.

Two deterministic regressions were added in
`scanner-api/tests/test_semantic_graph_cannibalization_evidence.py` covering the
missing-B10, verified-distinct, and verified-near-duplicate paths.

### Verification blocker on this checkpoint

The code and regressions are committed, but this automation execution environment
could not execute the focused Python suite: the available local Python/container
runners returned infrastructure `ClientError`, and the connected remote execution
runner requires interactive user input that is unavailable in a scheduled run.
GitHub reports no Actions workflow run for this integration-target PR head. The
current head does have `CodeRabbit: success`, but that status is not a substitute
for executing pytest.

Therefore the new two-test file is **not claimed as freshly executed yet**. The
serialized integrator must run:

```text
PYTHONPATH=. pytest -q \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py

python -m py_compile \
  app/semantic_graph.py \
  app/semantic_graph_html.py \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py
```

before transplant acceptance.

## Integrator implications

No new shared wiring is required. The serialized integrator may continue using
`build_semantic_graph_evidence(...)` at the same proposed hook. The contract now
includes pair/candidate coverage telemetry plus explicit near-duplicate comparison
verification state. Consumers must not reinterpret `not_verified` duplicate
comparison as proof that two semantically similar pages are distinct.

The pairwise CPU cost remains O(n²) inside the hard 1,000-page Lane-B bound, but
memory no longer grows with the number of qualifying semantic/duplicate pairs.
Corpus benchmarks should still measure CPU before any shadow feature is promoted.

No merge or deployment is authorized from this lane.
