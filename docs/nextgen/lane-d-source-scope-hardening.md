# Lane D — connected-evidence source-scope hardening

Branch: `agent/nextgen-evidence-connectors-20260921`  
Draft PR: #332  
Issue: #325

## Purpose

The existing Lane-D stack already proves envelope shape, registered provider/source identity, record semantics, coverage/accounting consistency, and snapshot-level duplicate protection. A remaining integrity gap was source-property scope: a structurally valid evidence record could still name a page outside the declared provider property and survive until a later integration layer.

This slice adds a sixth pure fail-closed boundary:

`connected_evidence_scope_semantics_v1`

implemented by `validate_connected_evidence_scope_semantics(...)` in `scanner-api/app/connected_evidence_scope_contract.py`.

It composes after `validate_connected_evidence_coverage_semantics(...)` and remains pure: no network calls, OAuth/account changes, Base44 schema mutation, persistence, authority, scoring, customer projection, `run_scan`, release/deploy/admission, or production changes.

## Fail-closed invariants

### Google Search Console

- `property_uri` must be either a valid `sc-domain:` DNS-domain property or a safe absolute HTTP(S) URL-prefix property.
- `sc-domain:` properties cannot smuggle paths, query strings, fragments, credentials, ports, or IP-address identities.
- Search Analytics rows carrying the `page` dimension must contain absolute HTTP(S) page URLs inside the declared Search Console property.
- Domain properties accept the exact domain and its subdomains only.
- URL-prefix properties require the page URL to remain inside the declared canonical prefix, so sibling paths and lookalike hosts fail closed.
- URL Inspection `inspection_url` must belong to the declared Search Console property. A valid-looking inspection result for an unrelated property is not accepted as evidence.
- Search Analytics observations without a `page` dimension make no page-scope claim and therefore are not forced through page-URL validation.

### Bing AI Performance imports

- `provenance.site_url` must be a safe absolute HTTP(S) URL without credentials, fragments, or query-scoped property ambiguity.
- Cited-page URLs must remain inside the declared site URL prefix. This strengthens the earlier same-host check when a Bing property is path-scoped.

### GA4 AI-assistant referrals

- `property_id` must be a numeric GA4 property identity, accepting both native `properties/<id>` and bare numeric import-compatible forms.
- `landing_page` evidence, when present, must be a root-relative GA4 landing-page path rather than an arbitrary absolute/external URL.
- GA4's `(not set)` landing-page value remains observationally valid without inventing a URL identity.

## Bundle composition

`connected_evidence_snapshot_bundle_v1` now validates each item through the source-scope boundary before calculating its snapshot identity. The complete lane-local chain is now:

1. generic envelope;
2. registered provider/source identity;
3. provider record semantics;
4. sample/coverage semantics;
5. provider property/source scope semantics;
6. bounded snapshot-bundle duplicate/contradiction semantics.

This remains optional connected evidence only. It does not become crawl authority and does not alter Standard 150 behavior when no connected evidence is present.

## Verification

New deterministic suite:

`scanner-api/tests/test_connected_evidence_scope_contract.py`

contains **18 focused regressions** covering versioning/non-mutation, valid and foreign `sc-domain:` page scope, malformed domain-property syntax, URL-prefix sibling/host-confusion rejection, URL Inspection property binding, query-only Search Analytics behavior, Bing path-scope binding, GA4 property identifiers, root-relative landing pages, and `(not set)` handling.

The existing 13 snapshot-bundle tests were updated so their upstream seam is now the new source-scope validator.

Hermetic pure-function verification in this runtime:

- scope + bundle focused suites: **31/31 passed**;
- `py_compile` for the new scope module, bundle module, scope test, and bundle test: passed.

The scope test uses a pass-through stub for the already-tested coverage validator, so this proves the new sixth-layer logic plus bundle composition in isolation. It is not a substitute for exact-head repository certification.

Expected focused Lane-D total after this slice: **125 tests** (107 previous + 18 new scope regressions).

Before serialized integration, run from `scanner-api/` on the exact lane head:

`PYTHONPATH=. pytest -q tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_coverage_contract.py tests/test_connected_evidence_scope_contract.py tests/test_connected_evidence_bundle_contract.py`

and:

`python -m py_compile app/connected_evidence.py app/connected_evidence_contract.py app/connected_evidence_source_contract.py app/connected_evidence_record_contract.py app/connected_evidence_coverage_contract.py app/connected_evidence_scope_contract.py app/connected_evidence_bundle_contract.py tests/test_connected_evidence.py tests/test_connected_evidence_contract.py tests/test_connected_evidence_source_contract.py tests/test_connected_evidence_timestamp_hardening.py tests/test_connected_evidence_record_contract.py tests/test_connected_evidence_coverage_contract.py tests/test_connected_evidence_scope_contract.py tests/test_connected_evidence_bundle_contract.py`

Do not mark Lane D integration-ready until that exact-head 125-test run is green and a fresh exact-head review has no unresolved material findings.
