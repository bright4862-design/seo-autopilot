# Agent D — Evidence Connectors handoff

Issue: #325  
Draft PR: #332  
Integration base: `nextgen/integration-20260921`  
Lane branch: `agent/nextgen-evidence-connectors-20260921`

## Lane boundary

This lane owns only pure, provider-neutral connected-evidence contracts, import/normalization helpers, sanitized fixtures, and tests. It performs no network I/O, OAuth/account mutation, Base44 schema change, authority/persistence write, customer projection, repair-priority change, `run_scan` orchestration, release, deployment, or production mutation.

The common envelope is versioned as `connected_evidence_v1`. Every envelope carries provider, surface, method, source kind, retrieval/observation timestamps, sample/coverage disclosure, evidence-quality confidence, provenance, explicit state, and bounded records. States are `verified`, `stale`, `not_connected`, `not_supported`, `not_verified`, and `provider_error`. Disconnected/stale/unavailable evidence is observational and must never block an otherwise valid Standard 150 scan or fabricate traffic/indexing/AI-visibility claims.

`scanner-api/app/connected_evidence_contract.py` adds a strict fail-closed validator for the envelope. It rejects missing/timezone-free timestamps, future observation timestamps, unknown top-level fields without a schema revision, unavailable states carrying records or claiming an observation timestamp, stale states without a strictly earlier `observed_at`, probability-like confidence labelling, missing transport provenance on observed evidence, oversized metadata/record shapes, non-JSON values, and non-finite JSON numbers such as `NaN`/`Infinity`. Unavailable envelopes remain compatible with the public fail-closed helper when no observation transport exists. The validator does not sign, persist, score, rank, or project evidence.

`scanner-api/app/connected_evidence_source_contract.py` adds `connected_evidence_source_profile_v1`, a second pure boundary that validates registered provider/source attribution after the generic envelope contract. It checks exact surface/method/transport/provider-operation provenance, required connector identities, strict boolean provenance for claims such as Bing `api_used=false`, absolute HTTP(S) URL Inspection identities, exact URL Inspection record/provenance identity, and same-host absolute Bing cited-page URLs. Unregistered source profiles fail closed, including speculative Google generative-AI reporting/API profiles.

The producer fails closed before constructing any envelope when `retrieved_at` cannot be parsed. Timestamp fallback parsing now validates the full string rather than truncating to a date prefix, so malformed values such as `2026-09-20Tinvalid` cannot become verified evidence. Valid date-only values remain supported. Bing and GA4 import observation dates are accumulated only after a row has passed all acceptance checks, so rejected rows cannot move `observed_at`/`coverage.period_end` forward or make stale accepted evidence appear fresh.

## Safe-now adapters

- **Google Search Console Search Analytics:** `normalize_gsc_search_analytics(...)` normalizes already-authorized `searchanalytics.query` response payloads and preserves dimensions, metrics, period coverage, property provenance, and truthful empty/unknown semantics.
- **Google Search Console URL Inspection:** `normalize_google_url_inspection(...)` normalizes already-authorized `urlInspection.index.inspect` payloads. It preserves verdict/indexing/fetch/canonical/last-crawl/referrer/sitemap observations without treating provider output as a guarantee of current search visibility.
- **Bing Webmaster Tools AI Performance:** `normalize_bing_ai_performance_rows(...)` and CSV wrapper accept manual CSV/Excel-derived dictionaries only. The contract preserves grounding query, cited page, citation count, average cited pages, topic/intent/citation share when present, geography/market/surface and import provenance. `api_used` is explicitly false; this lane does not claim an AI Performance API exists.
- **GA4 AI-assistant referrals:** `normalize_ga4_ai_referral_rows(...)` and CSV wrapper normalize aggregate referral rows for recognized assistant hosts and retain landing page, geography/device and traffic/conversion metrics. Referral evidence proves observed traffic only; it does not prove all mentions/citations or AI-answer ranking.
- **CSV import boundary:** bounded UTF-8 CSV parsing rejects oversized files/row sets and duplicate normalized headers.

Freshness fails closed whenever freshness checking is enabled but the provider observation time cannot be established, parsed, or is later than retrieval. GSC Search Analytics, Bing AI Performance imports, and GA4 AI-assistant referrals emit `not_verified` with no retained observation records in that case rather than representing freshness-unknown evidence as `verified`. `stale_after_days=None` remains the explicit opt-out when a caller intentionally chooses not to make a freshness claim. URL Inspection continues to use the time of the authorized inspection response as the observation time unless a separate source observation time is supplied.

Sanitized fixtures live under `scanner-api/tests/fixtures_connected_evidence/` for GSC Search Analytics, URL Inspection, Bing AI Performance and GA4 referral evidence. No test performs a live provider call.

## Future connector work requiring separate owner authorization

These are integration prerequisites, not permissions granted by this lane:

1. GSC Search Analytics live retrieval must use an existing owner-authorized Search Console connection and the documented Search Console API operation; no OAuth client, scope, token, property access, or credential is created here.
2. URL Inspection live retrieval likewise requires owner-authorized Search Console access and the documented URL Inspection operation; this lane does not alter quotas or connection UI.
3. GA4 live retrieval may later use an owner-authorized GA4 reporting/Data API connection or an explicit export import. This lane creates no Analytics property access, OAuth scope, credential, or account link.
4. Bing AI Performance remains import/manual evidence unless a separately verified official programmatic route is available and approved. Do not infer an endpoint from UI/export availability.
5. **No dedicated Google Generative-AI visibility/report API is assumed or implemented.** Until an official programmatic route is verified, any such evidence must remain manual/import/not-supported/not-verified as appropriate.

## Serialized integrator hook

The integrator may later call the pure adapters only after an authorized provider response/import already exists. Before any downstream use, validate each envelope first with `validate_connected_evidence(...)`, then with `validate_connected_evidence_source_identity(...)`. Keep the resulting connected-evidence collection separate from canonical crawl authority. `not_connected`, `not_supported`, `not_verified`, `provider_error`, and `stale` must remain explicit. Any future influence on B18 page value/priority belongs to the serialized integrator and existing signed authority path; this lane intentionally does not implement it.

Recommended integration sequence:

1. obtain authorized payload/import outside this lane;
2. normalize with the provider adapter;
3. validate the generic envelope strictly;
4. validate provider/source identity strictly;
5. attach as optional connected evidence with provenance/coverage intact;
6. only the serialized integration layer may decide whether valid current evidence affects later ranking/repair logic;
7. preserve Standard 150 output unchanged when no connected evidence is present.

## Verification

Focused suites on this lane now contain:

- `scanner-api/tests/test_connected_evidence.py`: **23 adapter tests**;
- `scanner-api/tests/test_connected_evidence_contract.py`: **24 generic contract tests**;
- `scanner-api/tests/test_connected_evidence_source_contract.py`: **15 source-profile tests**;
- `scanner-api/tests/test_connected_evidence_timestamp_hardening.py`: **2 timestamp hardening tests**.

The source-profile additions cover URL Inspection provenance/record identities being absolute HTTP(S) URLs and Bing `api_used` rejecting integer `0` rather than treating it as boolean `False`. The timestamp hardening tests cover a malformed timestamp with a valid date prefix plus continued support for valid date-only timestamps.

Previously executed repository checkpoint:

- `PYTHONPATH=. pytest -q tests/test_connected_evidence_contract.py` → **24 passed**;
- `python -m py_compile app/connected_evidence_contract.py` → passed.

Earlier hermetic slice checks passed the prior producer/freshness and source-profile additions, but they are not a substitute for the exact branch repository suite. The exact branch checkout still cannot be materialized by this runtime because outbound GitHub DNS is unavailable, and the normal repository PR workflow targets `main` while this draft targets `nextgen/integration-20260921`. Therefore the current exact-head focused suite is **not yet certified**.

Before integration, run from `scanner-api/` on the exact lane head:

`PYTHONPATH=. pytest -q tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py`

and:

`python -m py_compile app/connected_evidence.py app/connected_evidence_contract.py app/connected_evidence_source_contract.py tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py`

Expected focused count on this checkpoint is **64 tests total** (23 adapter + 24 generic contract + 15 source-profile + 2 timestamp hardening). Do not mark the lane integration-ready until that exact-head run is green and material review findings are resolved.

CodeRabbit review `5273246519` identified four valid current-head issues. This lane now addresses all four in code/docs/tests: the exact-head verification command includes source-profile coverage, URL Inspection identity values are absolute HTTP(S), boolean provenance is type-strict, and malformed timestamps with valid date prefixes are rejected rather than truncated. A fresh exact-head review is still required before integration readiness is claimed.

## Known risks / truthful unsupported states

- Connected evidence is optional enrichment, not crawl authority.
- Citation share is observational and is not a ranking, quality, or probability score.
- Search Console and Analytics payload freshness depends on the provider/report window; stale evidence remains retained but explicitly labelled.
- Date-less GSC/Bing/GA4 observations do not become `verified` under the default freshness gate; callers must supply a trustworthy observation/report end time or explicitly disable freshness evaluation.
- GA4 referral-source classification cannot measure dark/direct AI traffic or uncited mentions.
- Bing UI/export columns can evolve; unknown columns/rows fail closed rather than being guessed.
- Dedicated Google Gen-AI reporting remains unsupported/not verified until an official programmatic surface is established.
- `connected_evidence_v1` validation is intentionally strict; any future metadata shape expansion should be versioned rather than silently accepted.

Rollback is lane-local: omit these pure modules/tests/docs from the serialized integration branch. No production state, credentials, schema, durable authority, or customer data requires reversal.
