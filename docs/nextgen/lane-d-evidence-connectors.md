# Agent D — Evidence Connectors handoff

Issue: #325  
Draft PR: #332  
Integration base: `nextgen/integration-20260921`  
Lane branch: `agent/nextgen-evidence-connectors-20260921`

## Lane boundary

This lane owns only pure, provider-neutral connected-evidence contracts, import/normalization helpers, sanitized fixtures, tests, and lane-local handoff documentation. It performs no network I/O, OAuth/account mutation, credential creation, Base44 schema change, authority/persistence write, customer projection, repair-priority change, `run_scan` orchestration, release, deployment, admission, or production mutation.

The common envelope is versioned as `connected_evidence_v1`. Every envelope carries provider, surface, method, source kind, retrieval/observation timestamps, sample/coverage disclosure, evidence-quality confidence, provenance, an explicit evidence state, and bounded records. States are `verified`, `stale`, `not_connected`, `not_supported`, `not_verified`, and `provider_error`. Connected evidence remains optional enrichment and never becomes canonical crawl authority.

This file is the **authoritative Lane-D integration handoff**. Per-slice hardening notes under `docs/nextgen/lane-d-*-hardening.md` are historical design/regression records only; they are not standalone integration gates or exact-head test manifests.

## Validation stack

Lane D exposes seven pure fail-closed validation boundaries.

1. `validate_connected_evidence(...)` / `connected_evidence_v1`
   - strict envelope shape, timestamps, state semantics, JSON bounds, evidence-quality confidence, and unavailable/stale invariants;
   - unavailable states cannot carry records, `observed_at`, observational sample metadata, or coverage metadata.
2. `validate_connected_evidence_source_identity(...)` / `connected_evidence_source_profile_v1`
   - registered provider/source/surface/method/transport profiles and connector provenance;
   - provenance keys are allowlisted per registered provider/source profile so unversioned OAuth/API/credential claims cannot be smuggled into an otherwise valid envelope;
   - URL Inspection and Bing URL identities force valid HTTP(S) ports;
   - boolean provenance is type-strict;
   - ambiguous path-scoped GSC URL-prefix and Bing branch identities fail closed unless their non-root path uses the provider-style trailing `/` directory boundary. This prevents `/docs` from later being mistaken for the scope of `/docs-foreign/...`.
3. `validate_connected_evidence_record_semantics(...)` / `connected_evidence_record_semantics_v1`
   - provider-specific record meaning: GSC metric relationships, URL Inspection URL/timestamp semantics, Bing kind/citation semantics, GA4 assistant/source spoof resistance, and GA4 metric relationships.
4. `validate_connected_evidence_coverage_semantics(...)` / `connected_evidence_coverage_semantics_v1`
   - binds sample/coverage metadata to transported records and rejects forged counts, inconsistent import accounting, dimension drift, period contradictions, and record dates later than observation.
5. `validate_connected_evidence_scope_semantics(...)` / `connected_evidence_scope_semantics_v1`
   - binds observed pages/landing paths to declared GSC, Bing, and GA4 source/property scopes;
   - GSC/Bing HTTP paths and GA4 landing-page paths fail closed on raw or percent-encoded dot-segment traversal, encoded `/` or `\\` separators, malformed percent escapes, control characters, raw backslashes, and semicolon path parameters. Semicolons are rejected anywhere in the path, not only in the terminal URL segment.
6. `validate_connected_evidence_record_identity_semantics(...)` / `connected_evidence_record_identity_v1`
   - rejects duplicate logical provider rows even when transport row numbers or metrics differ;
   - accepted GA4 assistant aliases are canonicalized for identity;
   - GSC `page` dimensions and Bing cited-page URLs canonicalize harmless HTTP(S) representation aliases (scheme/host case, host trailing dot/IDNA form, default ports, omitted root slash) before duplicate detection while preserving path/query identity.
7. `validate_connected_evidence_snapshot_bundle(...)` / `connected_evidence_snapshot_bundle_v1`
   - validates the bounded optional evidence set for one logical enrichment snapshot;
   - composes the full prior chain for every item, canonicalizes source and observation/window identities, rejects duplicate/contradictory source-window observations, and rejects simultaneous observed/unavailable claims for one canonical source scope.

The producer fails closed before constructing an envelope when `retrieved_at` is not parseable. Bing and GA4 observation dates are accumulated only after row acceptance, so rejected rows cannot advance freshness.

## Safe-now adapters

- **Google Search Console Search Analytics:** `normalize_gsc_search_analytics(...)` accepts already-authorized `searchanalytics.query` response payloads and preserves dimensions, metrics, period coverage, and property provenance.
- **Google Search Console URL Inspection:** `normalize_google_url_inspection(...)` accepts already-authorized `urlInspection.index.inspect` payloads and preserves verdict/indexing/fetch/canonical/last-crawl/referrer/sitemap evidence without treating it as a guarantee of current search visibility.
- **Bing Webmaster Tools AI Performance:** `normalize_bing_ai_performance_rows(...)` and the CSV wrapper accept manual CSV/Excel-derived rows only. `api_used` is explicitly false; this lane does not claim that an AI Performance API exists.
- **GA4 AI-assistant referrals:** `normalize_ga4_ai_referral_rows(...)` and the CSV wrapper normalize aggregate referral rows for recognized assistant hosts. Referral evidence proves observed traffic only; it does not prove all AI mentions/citations.
- **CSV import boundary:** bounded UTF-8 CSV parsing rejects oversized inputs, row sets, and duplicate normalized headers.

Freshness fails closed when freshness checking is enabled but the observation time cannot be established, parsed, or is later than retrieval. `stale_after_days=None` is the explicit opt-out from a freshness claim.

Sanitized fixtures live under `scanner-api/tests/fixtures_connected_evidence/`. Deterministic tests perform no live provider calls.

## Source, record and snapshot integrity notes

- Search Console `sc-domain:` properties accept their DNS domain/subdomains; malformed path/port/IP domain-property identities fail closed.
- Search Console URL-prefix and Bing path-scoped property identities use a trailing `/` directory boundary for non-root paths. The source-profile gate rejects an ambiguous `/docs` identity rather than allowing a later raw prefix check to interpret `/docs-foreign` as a descendant.
- Registered provenance is closed-world per provider/source profile. Current optional provenance is only `import_name` for Bing manual exports and GA4 provided rows; new metadata requires an intentional profile/version change instead of being silently accepted.
- Scope membership refuses ambiguous URL path forms whose meaning can change after ordinary URL normalization: raw/encoded dot segments, encoded path separators, raw backslashes, malformed escapes, controls, and semicolon path parameters. The semicolon rule applies to every path segment because `urllib.parse` exposes only terminal-segment parameters separately.
- Search Analytics page-scope validation applies only when `page` is an observed dimension.
- URL Inspection `inspection_url` must belong to its declared Search Console property.
- Bing cited-page URLs must remain inside the declared site scope.
- GA4 property identities must be numeric (`properties/<id>` or bare numeric import form), and landing-page evidence must be root-relative and unambiguous under the same path-safety rules; `(not set)` remains explicit unknown identity.
- Provider row numbers are transport positions, not semantic identities. Metrics are measurements, not identity fields.
- GSC page/Bing URL identity canonicalization is intentionally narrow: it does not lowercase paths, drop queries, resolve redirects, or invent provider canonicals.
- Snapshot source identities canonicalize supported source aliases; snapshot observation identities canonicalize dimension order and equivalent temporal representations. Dated Bing/GA4 evidence without an explicit start derives a conservative start only from accepted carried record dates.

## Unsupported / separately authorized future work

1. GSC live retrieval requires an existing owner-authorized Search Console connection and documented API operations. No OAuth client, scope, token, property access, or credential is created here.
2. URL Inspection live retrieval likewise requires existing owner authorization; this lane does not alter quotas or connection UI.
3. GA4 live retrieval may later use an owner-authorized reporting/Data API connection or explicit export import. This lane creates no Analytics access or credential.
4. Bing AI Performance remains manual/import evidence unless a separately verified official programmatic route is available and approved.
5. **No dedicated Google Generative-AI visibility/report API is assumed or implemented.** Do not invent undocumented endpoints.

## Serialized integrator hook

For any later authorized payload/import, the serialized integration layer must:

1. normalize with the registered Lane-D adapter;
2. validate the complete logical enrichment set using `validate_connected_evidence_snapshot_bundle(...)`, which composes envelope → source identity → record semantics → coverage semantics → source/property scope → logical record identity, then applies canonical snapshot source/window identity and cross-state coherence;
3. only then attach evidence as optional connected evidence with provenance/coverage intact;
4. keep connected evidence separate from canonical crawl authority;
5. preserve Standard 150 behavior unchanged when connected evidence is absent.

Any later influence on page value, repair priority, authority, persistence, historical storage, customer projection, or `run_scan` belongs to the serialized integrator, not this lane.

## Verification

Focused suites on this lane now contain:

- `scanner-api/tests/test_connected_evidence.py`: **23 adapter tests**;
- `scanner-api/tests/test_connected_evidence_contract.py`: **27 generic contract tests**;
- `scanner-api/tests/test_connected_evidence_source_contract.py`: **17 source-profile tests**;
- `scanner-api/tests/test_connected_evidence_timestamp_hardening.py`: **2 timestamp-hardening tests**;
- `scanner-api/tests/test_connected_evidence_record_contract.py`: **17 record-semantics tests**;
- `scanner-api/tests/test_connected_evidence_coverage_contract.py`: **13 coverage-semantics tests**;
- `scanner-api/tests/test_connected_evidence_scope_contract.py`: **25 source/property-scope tests**;
- `scanner-api/tests/test_connected_evidence_record_identity_contract.py`: **12 logical-record-identity tests**;
- `scanner-api/tests/test_connected_evidence_bundle_contract.py`: **24 snapshot-bundle/full-chain tests**;
- `scanner-api/tests/test_connected_evidence_snapshot_observation_identity.py`: **6 snapshot-observation-identity tests**;
- `scanner-api/tests/test_connected_evidence_record_url_identity.py`: **4 URL-record-identity tests**;
- `scanner-api/tests/test_connected_evidence_prefix_provenance.py`: **4 path-prefix-provenance tests**;
- `scanner-api/tests/test_connected_evidence_provenance_shape.py`: **6 closed-world provenance-profile tests**;
- `scanner-api/tests/test_connected_evidence_ga4_landing_path_hardening.py`: **8 GA4 landing-path ambiguity tests**.

Expected focused total: **188 tests**.

Latest verified slice evidence in this runtime:

- closed-world provenance + GA4 landing-path hardening passed **14/14** in a hermetic package; only the already-tested generic-envelope and coverage boundaries were stubbed so the changed source/scope logic was exercised directly;
- `python -m py_compile app/connected_evidence_source_contract.py app/connected_evidence_scope_contract.py tests/test_connected_evidence_provenance_shape.py tests/test_connected_evidence_ga4_landing_path_hardening.py` passed for the changed candidate;
- the first candidate exposed a real semicolon gap: `/docs;param/x` is not represented by `urlparse(...).params`; the final guard therefore rejects semicolons directly in the raw path before canonicalization;
- immediately prior, ambiguous scope-path hardening passed **6/6** in a hermetic package with only the already-tested coverage boundary stubbed;
- prior path-prefix-provenance candidate logic passed **4/4** in a hermetic package with only the already-tested generic envelope boundary stubbed, and its changed source-contract/test passed `py_compile`;
- prior URL-record identity hardening passed **4/4** in a hermetic package with only the already-tested scope boundary stubbed, and its changed module/test passed `py_compile`.

Before serialized integration, run from `scanner-api/` on the exact lane head:

`PYTHONPATH=. pytest -q tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_coverage_contract.py tests/test_connected_evidence_scope_contract.py tests/test_connected_evidence_record_identity_contract.py tests/test_connected_evidence_bundle_contract.py tests/test_connected_evidence_snapshot_observation_identity.py tests/test_connected_evidence_record_url_identity.py tests/test_connected_evidence_prefix_provenance.py tests/test_connected_evidence_provenance_shape.py tests/test_connected_evidence_ga4_landing_path_hardening.py`

and:

`python -m py_compile app/connected_evidence.py app/connected_evidence_contract.py app/connected_evidence_source_contract.py app/connected_evidence_record_contract.py app/connected_evidence_coverage_contract.py app/connected_evidence_scope_contract.py app/connected_evidence_record_identity_contract.py app/connected_evidence_bundle_contract.py tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_coverage_contract.py tests/test_connected_evidence_scope_contract.py tests/test_connected_evidence_record_identity_contract.py tests/test_connected_evidence_bundle_contract.py tests/test_connected_evidence_snapshot_observation_identity.py tests/test_connected_evidence_record_url_identity.py tests/test_connected_evidence_prefix_provenance.py tests/test_connected_evidence_provenance_shape.py tests/test_connected_evidence_ga4_landing_path_hardening.py`

Do not mark Lane D integration-ready until the exact-head **188-test** repository-native run is green and a fresh exact-head review has no unresolved material findings.

The full repository-native exact-head 188-test run is **not yet claimed green** in this runtime. PR #332 intentionally targets `nextgen/integration-20260921`; do not retarget the PR or alter release workflows merely to manufacture CI.

## Known risks / truthful unsupported states

- Connected evidence is optional enrichment, not crawl authority.
- Citation share is observational and is not a ranking, quality, or probability score.
- Search Console and Analytics freshness depends on provider/report windows; stale evidence remains explicitly labelled.
- Date-less GSC/Bing/GA4 evidence does not become fresh by assumption under the default freshness gate.
- GA4 referral classification cannot measure dark/direct AI traffic or uncited mentions.
- Bing export columns can evolve; unknown/contradictory rows fail closed rather than being guessed.
- Dedicated Google Gen-AI reporting remains unsupported/not verified until an official programmatic surface is established.
- Snapshot identities prevent duplicate observations inside one logical snapshot; they are not historical storage keys.
- Unavailable states deliberately do not retain observational count/window metadata.
- Any future envelope/profile metadata expansion should be versioned rather than silently accepted.

The lane changes **33 Lane-D-owned files**: seven handoff/hardening docs, eight pure app modules, fourteen focused test modules, and four sanitized fixtures. No serialized-integrator-owned surface is modified.

Rollback is lane-local: omit these pure modules/tests/docs from the serialized integration branch. No production state, credentials, schema, durable authority, or customer data requires reversal.