# Agent D — Evidence Connectors handoff

Issue: #325  
Draft PR: #332  
Integration base: `nextgen/integration-20260921`  
Lane branch: `agent/nextgen-evidence-connectors-20260921`

## Lane boundary

This lane owns only pure, provider-neutral connected-evidence contracts, import/normalization helpers, sanitized fixtures, and tests. It performs no network I/O, OAuth/account mutation, Base44 schema change, authority/persistence write, customer projection, repair-priority change, `run_scan` orchestration, release, deployment, admission, or production mutation.

The common envelope is versioned as `connected_evidence_v1`. Every envelope carries provider, surface, method, source kind, retrieval/observation timestamps, sample/coverage disclosure, evidence-quality confidence, provenance, explicit state, and bounded records. States are `verified`, `stale`, `not_connected`, `not_supported`, `not_verified`, and `provider_error`. Connected evidence remains optional enrichment and never becomes canonical crawl authority.

This file is the **authoritative Lane-D integration handoff**. Per-slice hardening notes under `docs/nextgen/lane-d-*-hardening.md` are historical design/regression records only; they must not be used as standalone integration gates or exact-head test manifests.

## Validation stack

Lane D exposes seven pure fail-closed validation boundaries.

1. `validate_connected_evidence(...)` / `connected_evidence_v1`
   - strict envelope shape, timestamps, state semantics, JSON bounds, confidence semantics and unavailable/stale invariants;
   - unavailable states cannot carry observed records, `observed_at`, observational sample metadata, or coverage metadata. Their sample shape is limited to `{"coverage_complete_claim": false}` and coverage must remain empty.
2. `validate_connected_evidence_source_identity(...)` / `connected_evidence_source_profile_v1`
   - exact registered provider/source/surface/method/transport profiles, connector provenance, strict boolean provenance, URL Inspection identities, Bing same-host evidence and invalid-port rejection.
3. `validate_connected_evidence_record_semantics(...)` / `connected_evidence_record_semantics_v1`
   - provider-specific record meaning: GSC metric relationships and row identity, URL Inspection URL/timestamp semantics, Bing kind/citation semantics, GA4 assistant/source spoof resistance and metric semantics. GSC CTR must agree with clicks/impressions when all three are present, and GA4 engaged sessions cannot exceed sessions when both are present.
4. `validate_connected_evidence_coverage_semantics(...)` / `connected_evidence_coverage_semantics_v1`
   - binds sample/coverage metadata to the records actually carried by the envelope and rejects forged counts, inconsistent import accounting, dimension-population drift, period/observation contradictions, and record dates later than the stated observation time.
5. `validate_connected_evidence_scope_semantics(...)` / `connected_evidence_scope_semantics_v1`
   - binds observed pages/landing paths to the declared provider property/site scope: GSC Domain and URL-prefix properties, URL Inspection property membership, Bing site-prefix membership, and GA4 property/landing-path identity.
6. `validate_connected_evidence_record_identity_semantics(...)` / `connected_evidence_record_identity_v1`
   - rejects duplicate logical provider rows even when transport row numbers or metrics differ;
   - accepted GA4 assistant aliases are canonicalized for identity;
   - GSC `page` dimensions and Bing cited-page URLs canonicalize harmless HTTP(S) representation aliases (scheme/host case, host trailing dot/IDNA form, default ports, omitted root slash) before duplicate detection while keeping path/query identity significant.
7. `validate_connected_evidence_snapshot_bundle(...)` / `connected_evidence_snapshot_bundle_v1`
   - validates the bounded set of optional connected evidence attached to one logical enrichment snapshot, composes the full prior chain for every item, canonicalizes provider source identities under `connected_evidence_snapshot_source_identity_v1`, canonicalizes observation/window identity under `connected_evidence_snapshot_observation_identity_v1`, rejects duplicate/contradictory source-window identities, and fails closed when one canonical source scope is simultaneously represented as observed and unavailable.

The producer itself fails closed before constructing an envelope when `retrieved_at` is not parseable. Timestamp parsing validates the full input rather than truncating malformed timestamp suffixes. Bing and GA4 observation dates are accumulated only after row acceptance, so rejected rows cannot advance freshness.

## Safe-now adapters

- **Google Search Console Search Analytics:** `normalize_gsc_search_analytics(...)` normalizes already-authorized `searchanalytics.query` response payloads and preserves dimensions, metrics, period coverage and property provenance.
- **Google Search Console URL Inspection:** `normalize_google_url_inspection(...)` normalizes already-authorized `urlInspection.index.inspect` payloads and preserves verdict/indexing/fetch/canonical/last-crawl/referrer/sitemap evidence without treating it as a guarantee of current search visibility.
- **Bing Webmaster Tools AI Performance:** `normalize_bing_ai_performance_rows(...)` and the CSV wrapper accept manual CSV/Excel-derived rows only. `api_used` is explicitly false; this lane does not claim that an AI Performance API exists.
- **GA4 AI-assistant referrals:** `normalize_ga4_ai_referral_rows(...)` and the CSV wrapper normalize aggregate referral rows for recognized assistant hosts. Referral evidence proves observed traffic only; it does not prove all AI mentions/citations.
- **CSV import boundary:** bounded UTF-8 CSV parsing rejects oversized files/row sets and duplicate normalized headers.

Freshness fails closed whenever freshness checking is enabled but the provider observation time cannot be established, parsed, or is later than retrieval. `stale_after_days=None` is the explicit opt-out from making a freshness claim.

Sanitized fixtures live under `scanner-api/tests/fixtures_connected_evidence/`. No deterministic test performs a live provider call.

## Source, record and snapshot integrity notes

- Search Console `sc-domain:` properties accept only their exact DNS domain and subdomains; malformed path/port/IP/domain-property identities fail closed.
- Search Console URL-prefix properties use canonical HTTP(S) prefix membership; sibling hosts are rejected.
- Search Analytics page-scope validation applies only when `page` is an observed dimension. Query-only/other-dimension reports do not fabricate page identity.
- URL Inspection `inspection_url` must belong to its declared Search Console property.
- Bing cited-page URLs must remain inside the declared `site_url` prefix.
- GA4 property identities must be numeric (`properties/<id>` or bare numeric import form), and landing-page evidence must be a root-relative path; `(not set)` remains explicit unknown page identity.
- Provider row numbers are transport positions, not semantic identities. Metrics are measurements, not identity fields, so duplicate logical rows with different metrics fail closed instead of being silently summed.
- GSC page and Bing URL identity canonicalization is intentionally narrow: it collapses representational aliases only. It does not lowercase paths, drop queries, resolve redirects, or invent canonical URLs.
- Snapshot source identities canonicalize GSC domain case/trailing-dot aliases, HTTP(S) host case/default ports/root slash, and GA4 property resource aliases before duplicate detection.
- Snapshot observation identities canonicalize Search Analytics dimension order and equivalent ISO temporal representations. For dated Bing/GA4 evidence lacking `coverage.period_start`, the earliest accepted carried record date is used as a conservative start boundary so different windows sharing one end date remain distinct.
- A canonical GSC Search Analytics, Bing AI Performance, or GA4 source scope cannot be both observed (`verified`/`stale`) and unavailable (`not_connected`/`not_supported`/`not_verified`/`provider_error`) in one logical enrichment snapshot.

## Unsupported / separately authorized future work

1. GSC live retrieval requires an existing owner-authorized Search Console connection and documented API operations. No OAuth client, scope, token, property access or credential is created here.
2. URL Inspection live retrieval likewise requires existing owner authorization; this lane does not alter quotas or connection UI.
3. GA4 live retrieval may later use an owner-authorized reporting/Data API connection or explicit export import. This lane creates no Analytics access or credential.
4. Bing AI Performance remains manual/import evidence unless a separately verified official programmatic route is available and approved.
5. **No dedicated Google Generative-AI visibility/report API is assumed or implemented.** Do not invent undocumented endpoints.

## Serialized integrator hook

For any later authorized payload/import, the integration layer must:

1. normalize with the registered Lane-D adapter;
2. validate the complete set using `validate_connected_evidence_snapshot_bundle(...)`, which composes envelope → source identity → record semantics → coverage semantics → source/property scope → logical record identity for every item and then applies canonical source/snapshot observation identity plus cross-state coherence;
3. only then attach the evidence as optional connected evidence with provenance/coverage intact;
4. keep connected evidence separate from canonical crawl authority;
5. preserve Standard 150 behavior unchanged when connected evidence is absent.

For single-envelope debugging, the underlying validators remain callable individually. Any later influence on page value, repair priority, authority, persistence, customer projection, historical time-series storage, or `run_scan` belongs to the serialized integrator, not this lane.

## Verification

Focused suites on this lane now contain:

- `scanner-api/tests/test_connected_evidence.py`: **23 adapter tests**;
- `scanner-api/tests/test_connected_evidence_contract.py`: **27 generic contract tests**;
- `scanner-api/tests/test_connected_evidence_source_contract.py`: **17 source-profile tests**;
- `scanner-api/tests/test_connected_evidence_timestamp_hardening.py`: **2 timestamp-hardening tests**;
- `scanner-api/tests/test_connected_evidence_record_contract.py`: **17 record-semantics tests**;
- `scanner-api/tests/test_connected_evidence_coverage_contract.py`: **13 coverage-semantics tests**;
- `scanner-api/tests/test_connected_evidence_scope_contract.py`: **19 source/property-scope tests**;
- `scanner-api/tests/test_connected_evidence_record_identity_contract.py`: **12 logical-record-identity tests**;
- `scanner-api/tests/test_connected_evidence_bundle_contract.py`: **24 snapshot-bundle/full-chain tests**;
- `scanner-api/tests/test_connected_evidence_snapshot_observation_identity.py`: **6 snapshot-observation-identity tests**;
- `scanner-api/tests/test_connected_evidence_record_url_identity.py`: **4 URL-record-identity hardening tests**.

Expected focused total: **164 tests**.

Latest verified slice evidence in this runtime:

- a hermetic `connected_evidence_record_identity_v1` package with only the already-tested upstream scope boundary stubbed passed **4/4** cases covering GSC and Bing URL-alias duplicate rejection plus path/query distinctions;
- `python -m py_compile app/connected_evidence_record_identity_contract.py tests/test_connected_evidence_record_url_identity.py` passed in the same hermetic package.

Before serialized integration, run from `scanner-api/` on the exact lane head:

`PYTHONPATH=. pytest -q tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_coverage_contract.py tests/test_connected_evidence_scope_contract.py tests/test_connected_evidence_record_identity_contract.py tests/test_connected_evidence_bundle_contract.py tests/test_connected_evidence_snapshot_observation_identity.py tests/test_connected_evidence_record_url_identity.py`

and:

`python -m py_compile app/connected_evidence.py app/connected_evidence_contract.py app/connected_evidence_source_contract.py app/connected_evidence_record_contract.py app/connected_evidence_coverage_contract.py app/connected_evidence_scope_contract.py app/connected_evidence_record_identity_contract.py app/connected_evidence_bundle_contract.py tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_coverage_contract.py tests/test_connected_evidence_scope_contract.py tests/test_connected_evidence_record_identity_contract.py tests/test_connected_evidence_bundle_contract.py tests/test_connected_evidence_snapshot_observation_identity.py tests/test_connected_evidence_record_url_identity.py`

Do not mark Lane D integration-ready until the exact-head **164-test** run is green and a fresh exact-head review has no unresolved material findings.

The latest full repository-native exact-head 164-test run is **not yet claimed green** in this runtime. The PR intentionally targets `nextgen/integration-20260921`, while the repository's normal pull-request CI is configured for `main`; do not retarget the PR or alter release workflows merely to manufacture a CI result.

## Known risks / truthful unsupported states

- Connected evidence is optional enrichment, not crawl authority.
- Citation share is observational and is not a ranking, quality or probability score.
- Search Console and Analytics freshness depends on provider/report windows; stale evidence remains explicitly labelled.
- Date-less GSC/Bing/GA4 evidence does not become fresh by assumption under the default freshness gate.
- GA4 referral classification cannot measure dark/direct AI traffic or uncited mentions.
- Bing export columns can evolve; unknown/contradictory rows fail closed rather than being guessed.
- Dedicated Google Gen-AI reporting remains unsupported/not verified until an official programmatic surface is established.
- Snapshot bundle identities prevent equivalent source aliases and duplicate source/window observations inside one logical snapshot; they are not a historical storage key.
- Unavailable states deliberately do not retain observation-count/window metadata; if later product requirements need diagnostic rejection counters for unavailable imports, that must be introduced as a separately versioned non-observational diagnostic contract rather than smuggled into `sample`/`coverage`.
- Any future envelope/profile metadata expansion should be versioned rather than silently accepted.

The lane now changes **30 Lane-D-owned files**: seven handoff/hardening docs, eight pure app modules, eleven focused test modules, and four sanitized fixtures. No serialized-integrator-owned surface is modified.

Rollback is lane-local: omit these pure modules/tests/docs from the serialized integration branch. No production state, credentials, schema, durable authority or customer data requires reversal.
