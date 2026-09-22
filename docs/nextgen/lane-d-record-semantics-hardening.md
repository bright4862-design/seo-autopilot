# Agent D — connected-evidence record-semantics hardening

Issue: #325  
Draft PR: #332  
Lane branch: `agent/nextgen-evidence-connectors-20260921`

## Purpose

`connected_evidence_v1` already validates generic envelope shape/chronology and `connected_evidence_source_profile_v1` validates provider/source attribution. This additive slice introduces a third pure boundary, `connected_evidence_record_semantics_v1`, so structurally valid, correctly attributed envelopes can still fail closed when their normalized records are internally contradictory, spoof-prone, or semantically impossible.

The new module is `scanner-api/app/connected_evidence_record_contract.py`. It performs no network I/O, authentication, OAuth mutation, provider calls, persistence, scoring, customer projection, `run_scan` wiring, release, deployment, or production work.

## Contract

Call `validate_connected_evidence_record_semantics(evidence)` only after normalization. The helper composes through the existing source-identity validator first, then validates record semantics for the four registered Lane-D providers.

### GSC Search Analytics

- tabular `row_number` values must be positive and unique;
- dimensions must remain a non-empty mapping with string values;
- clicks/impressions must be non-negative integers;
- clicks cannot exceed impressions;
- CTR must be finite and within `0..1`;
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
- sessions/engaged sessions/users are non-negative integers and key events/revenue are finite/non-negative.

This is deliberately evidence-honest: recognized GA4 referral evidence proves observed referral traffic only. It does not prove all AI mentions/citations, and an arbitrary caller label cannot create verified AI-assistant provenance.

## Verification

New deterministic suite:

- `scanner-api/tests/test_connected_evidence_record_contract.py`: **13 tests**.

Coverage includes non-mutation/versioning, GA4 lookalike-host rejection, arbitrary assistant rejection, known explicit assistant support, source/assistant mismatch, URL Inspection URL-collection/canonical/future-crawl-time checks, GSC impossible metrics, Bing kind/share contradictions, and duplicate row identities.

A hermetic execution of the new semantic logic (with the pre-existing source-identity boundary stubbed only because this runtime cannot materialize the GitHub checkout) passed **13/13 semantic scenarios**, and the new module passed `py_compile`. This is slice evidence only, not a substitute for repository-native pytest with the real upstream contracts.

Expected focused Lane-D total after this slice: **77 tests**:

- 23 adapter tests;
- 24 generic contract tests;
- 15 source-profile tests;
- 2 timestamp-hardening tests;
- 13 record-semantics tests.

Required exact-head repository command from `scanner-api/` before serialized integration:

`PYTHONPATH=. pytest -q tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py`

and:

`python -m py_compile app/connected_evidence.py app/connected_evidence_contract.py app/connected_evidence_source_contract.py app/connected_evidence_record_contract.py tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py`

The exact-head repository run remains required because this runtime still cannot resolve `github.com` for a checkout and this draft PR targets the NextGen integration branch rather than `main`, so the normal PR workflow does not provide an exact-head certification run.

## Integrator handoff

For any later connected-evidence attachment, the serialized integrator should preserve the three proof layers in order:

1. normalize the already-authorized payload/import;
2. `validate_connected_evidence(...)` — generic envelope proof;
3. `validate_connected_evidence_source_identity(...)` — provider/source provenance proof;
4. `validate_connected_evidence_record_semantics(...)` — normalized record semantic proof;
5. only then attach as optional connected evidence, still separate from canonical crawl authority.

No Standard 150 behavior, B01–B28 authority, persistence, customer projection, repair priority, admission, release/deployment, schema/IAM/credentials, worker configuration, or production path is changed by this lane-local contract.

Rollback is lane-local: omit this module, test file and handoff note from serialized integration. No durable state or customer data needs reversal.
