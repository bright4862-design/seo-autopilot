# Lane D — connected-evidence source-scope hardening

Branch: `agent/nextgen-evidence-connectors-20260921`  
Draft PR: #332  
Issue: #325

> **Historical slice note:** this file records the source/property-scope boundary as it was introduced. It is not the current integration gate. The authoritative final validation sequence, exact-head pytest/`py_compile` commands, and current focused-test total live in `docs/nextgen/lane-d-evidence-connectors.md`. A serialized integrator must not stop at the boundary documented here.

## Purpose

The existing Lane-D stack already proves envelope shape, registered provider/source identity, record semantics and coverage/accounting consistency. A remaining integrity gap was source-property scope: a structurally valid evidence record could still name a page outside the declared provider property and survive until a later integration layer.

This slice adds the pure fail-closed boundary:

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

## Current bundle composition

This boundary is composed by `validate_connected_evidence_snapshot_bundle(...)` before snapshot identity is calculated. The current full Lane-D chain is documented only in `docs/nextgen/lane-d-evidence-connectors.md`; later boundaries add logical-record identity plus canonical source/snapshot identity and cross-state coherence after this scope proof.

This remains optional connected evidence only. It does not become crawl authority and does not alter Standard 150 behavior when no connected evidence is present.

## Historical slice verification

`scanner-api/tests/test_connected_evidence_scope_contract.py` contains the deterministic source/property-scope regressions for this boundary. The slice and bundle-composition tests were verified independently when introduced. Those historical results remain useful regression evidence but are not the current exact-head integration gate.

For the authoritative exact-head pytest/`py_compile` gate and current focused-test count, use `docs/nextgen/lane-d-evidence-connectors.md` only.

## Current serialized-integrator requirement

Normalize each already-authorized provider payload/import and validate the **complete logical enrichment set** with `validate_connected_evidence_snapshot_bundle(...)`. Only after that final bundle guard succeeds may serialized integration attach the optional connected evidence.

Do not wire this scope helper directly into authority/persistence/customer projection, repair priority, `run_scan`, Base44 schema, release/deployment, admission, or production from the lane branch.
