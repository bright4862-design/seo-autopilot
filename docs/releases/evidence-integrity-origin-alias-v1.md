# Evidence integrity and origin-alias candidate

Date: 2026-07-20

## Production trigger

The 18-site Phase 1 validation exposed two evidence-integrity failures:

1. Hartzler Dairy retained direct image resources under `/wp-content/uploads/` as page evidence.
2. Apex URLs submitted for sites whose canonical host is `www` caused every sampled sitemap URL to be requested as a redirect source, marking valid final HTML pages non-indexable and producing mass redirect findings.

## Candidate behavior

### Non-HTML resource paths

The queue and sitemap artifact guard now recognizes common image, document, script, stylesheet, font, archive, audio, and video suffixes before they can consume a page slot.

- These resources remain available as bounded artifact evidence.
- XML and XML.GZ are deliberately not filtered because they may be sitemap indexes or URL sets.
- Extensionless responses still rely on the shared response content-type/page-evidence gate.

### Apex/www identity redirects

A one-hop redirect is treated as an origin alias only when all of the following are true:

- source and destination use the same scheme;
- hosts differ only by a leading `www.`;
- ports match;
- path and query are identical after harmless trailing-slash normalization;
- the redirect reaches a final response in one hop.

The final HTML keeps its destination indexability. The transport alias is preserved separately through `origin_alias_redirect`, hop, chain, destination, and summary fields. HTTP-to-HTTPS redirects, path changes, trailing-slash redirects on the same host, chains, loops, failed destinations, noindex destinations, and robots-blocked destinations keep the existing redirect contract.

## Frozen component markers

- `artifact_filter_version`: `artifact_filter_v3_non_html_resources`
- `redirect_evidence_version`: `redirect_evidence_v3_origin_alias_identity`
- candidate fingerprint: `1f69eef0e2cd418b`

## Focused regressions

- common non-HTML suffixes are artifacts;
- sitemap XML/XML.GZ remains eligible for sitemap processing;
- explicit artifact reason is `non_html_resource_path`;
- ordinary path-changing redirects remain non-indexable redirect sources;
- same-host trailing-slash redirects remain redirect evidence;
- apex/www path-identity redirects preserve final HTML indexability and do not produce sitemap/internal-link redirect findings;
- redirect summaries report origin aliases separately.

## Production acceptance after merge and deployment

1. Hartzler Dairy: no PNG/GIF/JPG URL appears in `pages` or affects scoring/classification.
2. Lamanna Bakery or The Citizenry: apex/www aliases do not mark every final page non-indexable.
3. Funbooker: 150-page known-good control remains complete and authoritative.
4. Current scanner/review versions, 150-page hard cap, sampled disclosure, and both fallback flags remain unchanged.
