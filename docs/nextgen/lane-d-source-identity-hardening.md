# Agent D — connected-evidence source-identity hardening

Issue: #325  
Draft PR: #332  
Lane branch: `agent/nextgen-evidence-connectors-20260921`

## Purpose

`connected_evidence_v1` already validates the generic evidence envelope. This additive slice adds a second pure boundary for **connector/source attribution** so a structurally valid envelope cannot be relabelled as a different provider surface or transport without failing closed.

New contract: `connected_evidence_source_profile_v1` in `scanner-api/app/connected_evidence_source_contract.py`.

The validator first delegates to the existing strict `validate_connected_evidence(...)` envelope contract, then checks the registered provider/source profile for:

- exact provider + source-kind registration;
- exact surface and normalization method;
- exact transport provenance;
- connector-specific operation/surface identifiers;
- required property/site/inspection identity provenance;
- explicit `api_used=false` for Bing AI Performance manual exports;
- URL Inspection record identity matching the inspected URL in provenance;
- Bing cited-page URLs being absolute HTTP(S) URLs on the same host as the imported Bing site property;
- bounded optional import names;
- fail-closed behavior for unregistered provider/source pairs, including speculative Google generative-AI report/API profiles.

The validator returns the original envelope unchanged and performs no network I/O, OAuth/account mutation, persistence, customer projection, scoring, provider calls, or production work.

## Why this slice exists

The generic envelope contract proves shape, chronology, state, boundedness and provenance presence. It intentionally does not know connector-specific semantics. Without a second source-profile boundary, a caller could preserve a valid `connected_evidence_v1` shape while swapping a surface/method/provider operation, marking a Bing manual export as API-backed, or attaching a cited page from a different host to a Bing site property. Those are attribution errors rather than generic schema errors.

This layer keeps those concerns separate: generic structural validation remains stable, while provider-specific identity rules are versioned independently.

## Registered profiles

1. **GSC Search Analytics**
   - provider: `google_search_console`
   - source kind: `search_analytics`
   - surface: `google_search_console.search_analytics`
   - method: `api_response_normalization`
   - transport: `provided_payload`
   - operation: `searchanalytics.query`
   - requires `property_uri`

2. **Google URL Inspection**
   - provider: `google_search_console`
   - source kind: `url_inspection`
   - surface: `google_search_console.url_inspection`
   - method: `api_response_normalization`
   - transport: `provided_payload`
   - operation: `urlInspection.index.inspect`
   - requires `property_uri` and `inspection_url`
   - observed evidence must contain exactly one record whose `inspection_url` matches provenance

3. **Bing Webmaster Tools AI Performance manual export**
   - provider: `microsoft_bing_webmaster_tools`
   - source kind: `ai_performance_export`
   - surface: `bing_webmaster_tools.ai_performance`
   - method: `manual_export_normalization`
   - transport: `manual_export`
   - provider surface: `bing_webmaster_tools_ai_performance`
   - requires `site_url`
   - requires `api_used=false`
   - cited-page URLs, when present, must be absolute HTTP(S) URLs on the same host as `site_url`

4. **GA4 AI-assistant referrals**
   - provider: `google_analytics_4`
   - source kind: `ai_assistant_referrals`
   - surface: `google_analytics_4.referral_traffic`
   - method: `aggregate_row_normalization`
   - transport: `provided_rows`
   - provider surface: `ga4_reporting_export_or_response`
   - requires `property_id`

No Google generative-AI reporting/API profile is registered. A structurally valid envelope claiming such a source fails closed here until an official programmatic route is separately verified and authorized.

## Focused regressions

`scanner-api/tests/test_connected_evidence_source_contract.py` contains **12 deterministic tests** covering:

- versioned source-profile contract acceptance for GSC Search Analytics;
- wrong GSC provider operation rejection;
- wrong surface rejection;
- URL Inspection record/provenance identity mismatch rejection;
- URL Inspection provider-error provenance acceptance;
- Bing `api_used=true` rejection;
- Bing foreign-host cited-page rejection;
- Bing relative cited-page rejection;
- GA4 profile acceptance;
- missing GA4 property identity rejection;
- unregistered provider/source pair rejection;
- non-mutation of evidence.

A hermetic pure-function harness using the exact new module/test contents passed **12/12**, and `py_compile` passed for both new files. This is useful slice-level evidence only; it is **not** a substitute for the exact branch repository suite.

## Exact-head repository gate still required

Before serialized integration, run from `scanner-api/` on the exact lane head:

`PYTHONPATH=. pytest -q tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py`

and:

`python -m py_compile app/connected_evidence.py app/connected_evidence_contract.py app/connected_evidence_source_contract.py tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py`

Expected focused total after this slice: **59 tests** (23 adapter + 24 generic contract + 12 source-profile contract).

This runtime still cannot clone/download the GitHub checkout because outbound DNS resolution for `github.com` is unavailable, and the integration-target draft does not currently provide a PR-triggered Actions run. Do not mark Lane D integration-ready until the exact-head combined run is green and material review findings are resolved.

## Serialized integrator hook

For any future connected-evidence attachment, the safe order is:

1. obtain an already-authorized provider payload/import outside this lane;
2. normalize with the Lane-D adapter;
3. run `validate_connected_evidence(...)`;
4. run `validate_connected_evidence_source_identity(...)`;
5. only then allow the serialized integration layer to consider attaching the evidence as optional enrichment.

This does not alter canonical crawl authority, Standard 150, B01–B28 compatibility, repair priority, persistence, customer projection, admission, release, deployment, schema, IAM, credentials, or production.

Rollback is lane-local: omit the new helper/test/doc from the serialized integration transplant.
