# Agent B — Semantic Graph

Issue: #323
Draft PR: #329
Branch: `agent/nextgen-semantic-graph-20260921`
Integration base: `nextgen/integration-20260921`

This lane implements only the Semantic Graph work defined in
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not wire
customer-facing Fixes, repair priority, persistence, authority, scan
orchestration, admission, release, deployment, or production behavior.

## Implemented contract

### `scanner-api/app/semantic_graph.py`

Versioned, pure evidence primitives:

- `semantic_graph_evidence_v1`
- `link_zone_evidence_v1`
- `template_group_evidence_v1`
- `deterministic_local_semantic_v1`
- `near_duplicate_candidate_v1`
- `cannibalization_candidate_v1`
- `internal_link_opportunity_v1`

Implemented behavior:

- deterministic zero-configuration template grouping from an existing declared
  `page_template_family` when available, otherwise from a bounded route pattern;
- link-zone inference for contextual, listing, aside, navigation, header,
  footer, facet, and explicit unknown states, each with confidence/reason;
- weighted internal-link graph edges where contextual evidence weighs more than
  navigation/footer/facet evidence;
- deterministic/local lexical semantic vectors using title, H1, optional local
  semantic terms, and URL path only; no external model is required;
- a pluggable `SemanticVectorizer` interface for later local/optional enrichment;
- deterministic semantic similarity pairs and connected semantic clusters;
- B10-compatible near-duplicate candidates using only verified
  `sha256_5_token_shingles_v1` main-content fingerprints, never raw main copy;
- cannibalization candidates only when both pages are usable and explicitly
  indexable, with verified near-duplicates excluded;
- source→target contextual internal-link opportunity evidence only when an edge
  is absent from the observed graph; no sitewide link-absence claim is made;
- hard bounds of 1,000 pages, 50,000 link observations, and 2,000 links per
  source so this lane cannot create an unbounded analysis path.

Every graph/opportunity envelope is scoped to `observed_assessed_pages_only` and
sets `sitewide_orphan_claim` / `sitewide_link_absence_claim` to false.

### `scanner-api/app/semantic_graph_html.py`

Pure accepted-HTML adapter for zero-configuration link-zone evidence. It:

- performs no fetch/network work;
- accepts only already-observed HTML plus source URL;
- refuses HTML above 2 MB;
- resolves bounded link targets locally;
- emits only bounded anchor text and ancestor tag/role/class/id signals;
- never returns raw HTML;
- preserves an explicit unknown state when structural evidence is insufficient.

This adapter is intentionally not wired into `extract.py` or `scanner.py` in the
lane branch. Integration ownership remains serialized.

## Safety / compatibility invariants

- No `run_scan` or global budget changes.
- No final repair/fix generation and no repair-priority changes.
- No authority, seal, persistence, ScanRun schema, or customer projection change.
- No admission, deployment, release, production, credential, or provider call.
- No external embedding/model dependency for correctness.
- No raw B10 main content is introduced; only the existing verified hashed
  shingle representation is accepted for duplicate evidence.
- A `navigation_presence=False` observation is not promoted to contextual; the
  classifier fails closed to unknown without positive structural evidence.
- Incomplete observed-link coverage never becomes proof of sitewide orphaning.

## Focused verification

Reconstructed the lane-owned files in an isolated scanner package and ran:

```text
PYTHONPATH=. pytest -q tests/test_semantic_graph.py tests/test_semantic_graph_html.py
...........                                                              [100%]
11 passed

python -m py_compile app/semantic_graph.py app/semantic_graph_html.py \
  tests/test_semantic_graph.py tests/test_semantic_graph_html.py
PASS
```

Behavioral coverage includes:

- contextual/navigation/footer/facet/listing/unknown zone semantics;
- zero-config accepted-HTML zone extraction with no raw-HTML output;
- deterministic template grouping;
- contextual links weighted above footer links;
- explicit negative sitewide-orphan capability;
- deterministic local semantic vectors/clusters;
- verified B10 hashed-shingle near-duplicate gating;
- cannibalization exclusion for near duplicates and non-indexable pages;
- source→target opportunity evidence without claiming global absence;
- complete versioned envelope with `customer_fix_created=False`.

The repository-wide scanner suite was not executed from this automation runtime
because it does not expose a full repository checkout. The repository's primary
`FixList CI` workflow also triggers only for pushes/PRs targeting `main`, while
PR #329 correctly targets `nextgen/integration-20260921`. The lane does not alter
that workflow merely to manufacture a check.

## Serialized integrator handoff

Recommended minimal integration sequence, still shadow/off by default:

1. After accepted page evidence exists and before producer-only B10 fields are
   privacy-projected, construct Lane-B page inputs from retained assessed pages.
2. Supply link observations from already-accepted HTML using
   `semantic_graph_html.extract_link_zone_observations`, or map equivalent
   existing extractor evidence into the same local contract. Do not refetch.
3. Call `build_semantic_graph_evidence(...)` as a pure analyzer. Do not allow it
   to mutate assessed pages or scan authority.
4. Keep the envelope internal/shadow first. Feed only candidate evidence into
   the existing B20 root-cause layer after serialized review; that layer remains
   responsible for grouping, repair identity, final priority, and customer copy.
5. Preserve the existing B10 producer ordering: hashed main-content evidence may
   be consumed transiently for near-duplicate analysis, but raw main copy must
   never be persisted or customer-projected.
6. Require explicit indexability evidence before promoting a cannibalization
   candidate. Missing indexability stays unverified rather than assumed.
7. Treat internal-link opportunities as observed-sample candidates. The absence
   of an observed source→target edge is never proof that no such link exists
   elsewhere on the site.

## Risks / follow-up

- Route-pattern template inference is deliberately conservative; declared
  template families remain higher-confidence evidence.
- The default semantic model is lexical/local, not a claim of embedding-level
  semantic understanding. Optional model enrichment belongs behind the provided
  adapter contract and must not become correctness-critical.
- Pairwise semantic comparison is bounded to 1,000 pages but is still O(n²).
  Corpus/shadow benchmarks should measure CPU before promotion; blocking or
  candidate preselection can be added later without changing the evidence
  contract.
- Link-zone confidence depends on available structural evidence. Existing
  `navigation_presence` alone can prove navigation but cannot prove contextual
  placement; the accepted-HTML adapter supplies the richer evidence when the
  integrator chooses to wire it.

## Changed files owned by this lane

- `scanner-api/app/semantic_graph.py`
- `scanner-api/app/semantic_graph_html.py`
- `scanner-api/tests/test_semantic_graph.py`
- `scanner-api/tests/test_semantic_graph_html.py`
- `docs/nextgen/lane-b-semantic-graph.md`

No merge or deployment is authorized from this lane.
