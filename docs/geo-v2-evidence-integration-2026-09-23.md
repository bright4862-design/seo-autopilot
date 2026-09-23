# GEO v2 evidence integration checkpoint

Date: 2026-09-23

Base: `99e74965775f731c120e185b0e26d11f150c084f`.
Source reviewed: GEO lane `10102a6eaa470106f5dbc3c24ddf61273eb9bba9`.

## Scope and release state

This checkpoint brings a focused set of pure evidence helpers onto current main.
It does not change the existing v1 adapter, evaluator, runtime, crawler,
robots policy, authority seal, persistence, customer projection or UI. It makes
no network/model call. No historical saved result is recomputed or reinterpreted.
Production activation belongs to the serialized integrator.

The original lane expanded evidence semantics under the v1 adapter name. This
checkpoint isolates them in `geo_evidence_v2_candidate`. V1 and v2 retained
records reject cross-version use. Keeping v1 frozen avoids silently changing
historical evidence meaning.

## Deterministic evidence

`scanner-api/app/geo_evidence_v2.py` exports the same explicit callable shape:

- `extract_geo_evidence(html, page) -> retained record`
- `assess_geo_pages(pages, *, parent_authoritative=False, entry_verified=False,
  access_limited=False) -> candidate assessment`

The extractor does not mutate the page. The assessment expects the caller to
place its versioned record under `page["geo_evidence"]` in the provided page
view. It rejects a v1 record in that position. This is not permission to overwrite
existing persisted evidence; a shadow evaluation must use separate page views.
The full v2 extraction implementation remains isolated so future v2 semantic
changes cannot mutate the frozen v1 contract through shared global constants.

Accepted raw HTML can now provide positive evidence through a bounded JSON-LD
subject that has a recognized schema.org context/type, agrees with the whitespace/case-normalized visible
H1, and is explicitly bound to the current page. `url`, `@id` fragments and
`mainEntityOfPage` are supported. Conflicting page identities fail closed.
Article support can use identified author links, ISO dates and citation URLs
from the matching article subject. These assert retained structure only, never
factual accuracy, source quality, freshness or provider ingestion.

Article-only support checks become `not_applicable` only for a positively
identified non-article subject and a complete bounded structural inspection
showing no article semantics. Plain absence of `<article>` is insufficient.
Malformed/oversized JSON-LD, incomplete script/entry/type populations, unsupported
contexts and nested article semantics cannot establish that exclusion.

Positive extraction visits at most 25 scripts, 100,000 characters per script and 50
root/one-level `@graph` entries. A separate negative-only completeness walk is
bounded to 200 container visits and depth 8 per root; it can revoke N/A but
never supply positive subject/support evidence. HTML remains capped at 2 million characters;
assessment remains capped at Standard 150. Crawl/request budgets are untouched.

## Arithmetic and sidecars

`geo_readiness_v2.evaluate_geo_v2(page_ids, observations, **gates)` delegates all
arithmetic and gates to the unchanged v1 evaluator. It adds an unambiguous page
set digest, dimension summaries and explicit unknown cells. The 80% overall and
50% per-dimension coverage gates and equal dimension weights remain intact.
A dimension consisting entirely of N/A still has zero verified mass. A
marketplace Product example therefore still has no numeric score.

All candidate results keep `authority_verified=false`, including internally
assessed examples. An internally computed number is not permission to display a
customer score before authority and evidence requirements are accepted.

Optional pure sidecars:

- `geo_robots_evidence.extract_named_robots_evidence(page)` normalizes only exact
  retained OAI-SearchBot/GPTBot/Googlebot decisions. It does not infer a missing
  bot's policy, and rejects contradictory status/HTTP/directive states. GPTBot
  restrictions are neutral evidence, not scored deductions.
- `geo_llms_txt_evidence.extract_llms_txt_evidence(observation)` accepts an
  already retained response only. It uses a bounded required-H1/structure check,
  rejects contradictory HTML MIME responses, and keeps absence neutral. No
  request is added and neither presence nor validity enters the scored matrix.
- `geo_claim_boundary` is heuristic copy lint for human review, not a grounding
  verifier. Passing it never authorizes arbitrary prose or provider claims.

Neither sidecar measures provider access, indexing, citations, ranking,
visibility, inclusion or traffic.

## Shared integration requirements

The existing raw extraction seam is `scanner-api/app/extract.py`; assessment
seams are `geo_runtime.py`, `review.py` and `scan_job.py`. These are unchanged here.

Before any v2 authority/customer route is activated, the integrator must:

1. Deliberately select matching versioned extraction and assessment together;
   preserve v1 reads and fail closed on unknown/mixed versions.
2. Bind the exact retained page population, typed observation population
   (including states, evidence refs and reasons), raw content digests, gate
   facts and any optional sidecar source records inside an authenticated
   versioned snapshot. Matching aggregate counts or plain SHA-256 values alone
   do not authenticate those sources.
3. Verify exact persistence/reload bytes and scope/owner/scan identity. Refuse
   substituted observations even when aggregate values are unchanged.
4. Preserve withheld customer scores until that versioned authority path is
   accepted. Keep candidate-only fields private; adding a new raw page key also
   requires explicit review of `page_output_privacy.py`.

No unused V8 transport wrappers are imported in this checkpoint. Existing lane
transport code remains a design reference to review separately.

## Validation

The reviewed lane had reproducible false-positive applicability cases. New
regressions reject foreign/unbound same-name subjects, custom contexts and
unknown types, mismatched article subjects, hidden nested Article types,
truncated type/script populations, malformed/oversized structures, and nested
context overrides and duplicate JSON-LD properties. Plain citation text and malformed author/source
URLs cannot be promoted into links through relative-URL resolution. Version mixing, public-URL identity and sidecar status
contradictions also have regressions.

Focused suite: 161 passed, including unchanged v1 evidence/runtime/arithmetic,
v2 candidate compatibility, per-bot and llms.txt sidecars. Compilation and git
whitespace checks also pass. These are hermetic local checks, not a production
GEO acceptance claim; exact-head repository CI remains the integrator gate.
