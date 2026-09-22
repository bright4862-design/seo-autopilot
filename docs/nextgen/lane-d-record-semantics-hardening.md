# Agent D — connected-evidence record-semantics hardening

Issue: #325  
Draft PR: #332  
Lane branch: `agent/nextgen-evidence-connectors-20260921`

> **Historical slice note:** this file records the record-semantics boundary as it was introduced. It is not the current integration gate. The authoritative final validation sequence, exact-head pytest/`py_compile` commands, and current focused-test total live in `docs/nextgen/lane-d-evidence-connectors.md`. A serialized integrator must not stop at the boundary documented here.

## Purpose

`connected_evidence_v1` already validates generic envelope shape/chronology and `connected_evidence_source_profile_v1` validates provider/source attribution. This additive slice introduces a third pure boundary, `connected_evidence_record_semantics_v1`, so structurally valid, correctly attributed envelopes can still fail closed when their normalized records are internally contradictory, spoof-prone, or semantically impossible.

The module is `scanner-api/app/connected_evidence_record_contract.py`. It performs no network I/O, authentication, OAuth mutation, provider calls, persistence, scoring, customer projection, `run_scan` wiring, release, deployment, or production work.

## Contract

Call `validate_connected_evidence_record_semantics(evidence)` only after normalization. The helper composes through the existing source-identity validator first, then validates record semantics for the four registered Lane-D providers.

### GSC Search Analytics

- tabular `row_number` values must be positive and unique;
- dimensions must remain a non-empty mapping with string values;
- clicks/impressions must be non-negative integers;
- clicks cannot exceed impressions;
- CTR must be finite and within `0..1`;
- when clicks, impressions and CTR are all present, CTR must agree with clicks/impressions;
- average position must be finite and non-negative.

### Google URL Inspection

- observed evidence must still contain exactly one record;
- `inspection_result_link`, Google canonical and user canonical, when present, must be absolute HTTP(S) URLs;
- `referring_urls` and `sitemap` must be lists whose members are absolute HTTP(S) URLs;
- `last_crawl_time`, when present, must be timezone-aware ISO-8601 and cannot be later than `retrieved_at`.

This closes a provider-shape ambiguity where a malformed scalar collection could otherwise normalize into a list-like value and survive generic/source identity checks.

### Bing AI Performance manual export

- row numbers must be positive/unique;
- `kind` must be one of the normalized evidence kinds and must agree with actual URL/query identity;
- `summary_or_trend` must carry measurable evidence;
- citations must be non-negative integers;
- average cited pages must be finite/non-negative;
- citation share must remain finite and within `0..1`.

The existing source contract continues to prove that cited-page URLs are absolute and same-host with the imported Bing site and that `api_used` is the actual boolean `false`. No Bing AI Performance API is claimed or introduced.

### GA4 AI-assistant referrals

- row numbers must be positive/unique;
- assistant identities must canonicalize to a small registered set;
- when a source is present, its host must be an exact/subdomain match for a registered AI-assistant domain and must agree with the assistant identity;
- substring lookalikes such as `notchatgpt.example` are rejected;
- arbitrary explicit assistant labels are rejected rather than being treated as AI traffic;
- sessions/engaged sessions/users are non-negative integers and key events/revenue are finite/non-negative;
- engaged sessions cannot exceed sessions when both are present.

This is deliberately evidence-honest: recognized GA4 referral evidence proves observed referral traffic only. It does not prove all AI mentions/citations, and an arbitrary caller label cannot create verified AI-assistant provenance.

## Historical slice verification

`scanner-api/tests/test_connected_evidence_record_contract.py` contains the deterministic record-semantics regressions for this boundary. The slice was verified independently when introduced. Those results remain useful regression history but are not the current exact-head integration gate because later Lane-D boundaries compose additional coverage, property-scope, logical-record-identity, and snapshot-bundle semantics.

## Current serialized-integrator requirement

This boundary is necessary but no longer sufficient on its own. For any later connected-evidence attachment:

1. normalize the already-authorized payload/import;
2. validate the complete logical enrichment set with `validate_connected_evidence_snapshot_bundle(...)`;
3. only then attach it as optional connected evidence, still separate from canonical crawl authority.

`validate_connected_evidence_snapshot_bundle(...)` composes the current full Lane-D chain, including generic envelope proof, provider/source provenance, this record-semantic proof, coverage semantics, provider property/source scope, logical-record identity, canonical source/snapshot identity and cross-state coherence. Do not reproduce the historical three-layer sequence from this slice as an integration gate.

For the authoritative exact-head pytest/`py_compile` gate and current focused-test count, use `docs/nextgen/lane-d-evidence-connectors.md` only.

No Standard 150 behavior, B01–B28 authority, persistence, customer projection, repair priority, admission, release/deployment, schema/IAM/credentials, worker configuration, or production path is changed by this lane-local contract.

Rollback is lane-local: omit the Lane-D pure helpers/tests/docs from serialized integration. No durable state or customer data needs reversal.
