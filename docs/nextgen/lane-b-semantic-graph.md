# Agent B — Semantic Graph

Issue: #323
Draft PR: #329
Branch: `agent/nextgen-semantic-graph-20260921`
Integration base: `nextgen/integration-20260921`

This lane implements only the Semantic Graph work defined in
`docs/nextgen/2026-09-21-parallel-engineering-lanes.md`. It does not wire
customer-facing Fixes, repair priority, persistence, authority, scan
orchestration, admission, release, deployment, or production behavior.

## Implemented contracts

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
- complete bounded semantic-pair analysis for downstream clustering/candidates,
  independent of the public 250-row serialized sample cap;
- B10-compatible near-duplicate candidates using only verified
  `sha256_5_token_shingles_v1` main-content fingerprints, never raw main copy;
- cannibalization candidates only when both pages are usable and explicitly
  indexable, with verified near duplicates excluded and unverified duplicate
  status kept separate from verified-distinct evidence;
- source→target internal-link opportunity evidence scoped only to observed
  assessed pages, never sitewide absence/orphan claims;
- hard bounds of 1,000 pages, 50,000 link observations, and 2,000 links per
  source so this lane cannot create an unbounded analysis path.

Every graph/opportunity envelope is scoped to `observed_assessed_pages_only` and
sets `sitewide_orphan_claim` / `sitewide_link_absence_claim` to false.

### `scanner-api/app/semantic_graph_html.py`

Pure accepted-HTML adapter for zero-configuration link-zone evidence. It:

- performs no fetch/network work;
- accepts only already-observed HTML plus source URL;
- refuses HTML above 2 MB;
- resolves bounded HTTP(S) link targets locally;
- excludes hidden/inert and non-HTTP(S) links from accepted observations;
- emits only bounded anchor text and ancestor tag/role/class/id signals;
- never returns raw HTML;
- preserves an explicit unknown state when structural evidence is insufficient.

This adapter is intentionally not wired into `extract.py` or `scanner.py` in the
lane branch. Integration ownership remains serialized.

### `scanner-api/app/semantic_graph_contextual.py`

Additive `contextual_internal_link_opportunity_v1` evidence for body/contextual
link upgrades. It:

- allows a contextual recommendation when the observed directed edge exists only
  in navigation/header/footer/listing/facet/aside/unknown zones;
- suppresses only when an observed contextual edge already exists;
- preserves `observed_edge_present`, `existing_strongest_zone`, assessed-sample
  scope, and `sitewide_link_absence_claim=False`;
- fails closed when graph version/scope, page population, node/edge identity,
  edge endpoints/zones/weights, or semantic-vector population is inconsistent;
- recomputes node inbound/outbound unique-edge counts and six-decimal weight sums
  from the validated edge set and rejects transported node metrics that disagree;
- rejects boolean/coercible edge counts and non-finite or over-precision graph
  weights before they can influence opportunity scoring.

The node-metric recomputation closes the latest independent-review P1 where a
forged `weighted_in`/`weighted_out` could previously alter top-candidate ordering
while still passing the first contextual integrity gate.

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
- Incomplete observed-link coverage never becomes proof of sitewide orphaning or
  global link absence.
- Transported graph metrics must be internally consistent with validated edges
  before they can influence contextual opportunity scoring.

## Verification state

Previously executed repository checkpoint:

```text
PYTHONPATH=. pytest -q tests/test_semantic_graph.py tests/test_semantic_graph_html.py
.................                                                        [100%]
17 passed in 0.42s

python -m py_compile app/semantic_graph.py app/semantic_graph_html.py \
  tests/test_semantic_graph.py tests/test_semantic_graph_html.py
PASS
```

Later committed regression coverage adds:

- two cannibalization evidence-truthfulness tests;
- ten contextual-link/integrity tests, including forged inbound/outbound node
  weights and edge counts.

The branch therefore contains **29 focused Lane-B tests** across four test files.
The latest graph-metric correction was checked in a hermetic pure validator
harness: one valid internally consistent graph was accepted and all four forged
metric/count cases failed closed with the expected reason.

The complete 29-test exact-head repository suite is **not claimed green yet**.
This automation runtime cannot clone the repository because outbound DNS cannot
resolve `github.com`, and PR #329 currently has no PR-triggered workflow run for
the exact head. Required gate:

```text
cd scanner-api
PYTHONPATH=. pytest -q \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py

python -m py_compile \
  app/semantic_graph.py \
  app/semantic_graph_html.py \
  app/semantic_graph_contextual.py \
  tests/test_semantic_graph.py \
  tests/test_semantic_graph_html.py \
  tests/test_semantic_graph_cannibalization_evidence.py \
  tests/test_semantic_graph_contextual.py
```

Do not accept the lane for serialized transplant until the exact-head repository
suite executes green and current material review findings are cleared.

## Serialized integrator handoff

Recommended minimal integration sequence, still shadow/off by default:

1. After accepted page evidence exists and before producer-only B10 fields are
   privacy-projected, construct Lane-B page inputs from retained assessed pages.
2. Supply link observations from already-accepted HTML using
   `semantic_graph_html.extract_link_zone_observations`, or map equivalent
   existing extractor evidence into the same local contract. Do not refetch.
3. Build the weighted graph and semantic evidence as pure analyzers. Do not allow
   them to mutate assessed pages or scan authority.
4. For generic absent-edge evidence, the original opportunity helper remains
   available. For a specifically contextual/body-link opportunity, prefer
   `contextual_internal_link_opportunities(...)` so a navigation/footer edge does
   not incorrectly suppress a contextual upgrade.
5. Keep the envelope internal/shadow first. Feed only candidate evidence into
   the existing B20 root-cause layer after serialized review; that layer remains
   responsible for grouping, repair identity, final priority, and customer copy.
6. Preserve the existing B10 producer ordering: hashed main-content evidence may
   be consumed transiently for near-duplicate analysis, but raw main copy must
   never be persisted or customer-projected.
7. Require explicit indexability evidence before promoting a cannibalization
   candidate. Missing indexability stays unverified rather than assumed.
8. Preserve `graph_integrity_state` and assessed-sample scope. A missing observed
   edge is never proof of sitewide absence, and an internally inconsistent graph
   is never verified recommendation evidence.

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
  placement; the accepted-HTML adapter supplies richer evidence when the
  integrator chooses to wire it.
- The contextual graph integrity layer proves internal consistency of transported
  graph metrics; it is not a substitute for serialized authority/signature or
  durable evidence provenance, which remain integrator-owned.

## Changed files owned by this lane

- `docs/nextgen/lane-b-contextual-link-hardening.md`
- `docs/nextgen/lane-b-semantic-graph-hardening.md`
- `docs/nextgen/lane-b-semantic-graph.md`
- `scanner-api/app/semantic_graph.py`
- `scanner-api/app/semantic_graph_contextual.py`
- `scanner-api/app/semantic_graph_html.py`
- `scanner-api/tests/test_semantic_graph.py`
- `scanner-api/tests/test_semantic_graph_cannibalization_evidence.py`
- `scanner-api/tests/test_semantic_graph_contextual.py`
- `scanner-api/tests/test_semantic_graph_html.py`

No merge or deployment is authorized from this lane.
