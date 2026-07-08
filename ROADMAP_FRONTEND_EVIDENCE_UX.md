# Frontend Evidence UX Roadmap

Start this after PR #3 is merged and deployed. PR #3 defines the evidence fields the frontend should trust.

## Goals

FixList should explain what it found, why it matters, who should fix it, and which page evidence supports the recommendation.

## Backend fields to prefer

- `review_evidence_contract_version`
- `review_input_quality`
- `evidence_complete`
- `scan_status`
- `site_fingerprint`
- `pages_found`
- `pages_crawled`
- `queued_remaining`
- `cleaned_fixes[].source_pages`
- `cleaned_fixes[].current_value`
- `cleaned_fixes[].page_template_family`
- `cleaned_fixes[].primary_defect_class`
- `cleaned_fixes[].who_can_do_this`

## EvidenceQualityGate

Show this before the score and recommendations.

States:

1. Complete
2. Representative sample
3. Incomplete evidence
4. Access limited
5. Metadata-only review

Copy examples:

Complete:

> FixList inspected page evidence and produced recommendations from the crawl.

Representative sample:

> FixList checked a representative sample of this larger site. Repeated issues are grouped by page type.

Incomplete:

> Scan incomplete. FixList understood part of the website, but page evidence did not fully reach AI Review. Rerun the scan before making content changes.

Access limited:

> FixList could not inspect enough pages. Ask your web person to check crawler access before changing page content.

## Safe health score display

Do not show a green score when evidence is incomplete or when access limitations dominate the scan. Instead show one of these states:

- Scan incomplete
- Access limited
- Representative sample

## SiteUnderstandingPanel

Use `site_fingerprint` to explain what FixList recognized.

Example:

> FixList recognized this as a booking / experiences marketplace.
> Pages checked: 150.
> Pages found: 983.
> Important page types: activity/detail pages, listing/category pages, booking paths, trust pages.

Show:

- primary archetype
- business model
- size band
- pages crawled/found
- priority page types
- priority issue types
- access warnings

## Fix card requirements

Each fix card should answer:

1. What did FixList notice?
2. Why does it matter?
3. Who should fix it?
4. What is the current evidence?
5. Which source pages support this?
6. What should happen next?

Owner labels:

- You
- Your web person

## Bucket labels

Replace generic status labels with:

- Quick wins you can do
- Prepared fixes
- Send to your web person

## Evidence drawer

Each fix should expose:

- source_pages
- affected_pages
- current_value
- status codes if available
- link text samples if available
- page_template_family
- primary_defect_class
- scanner/backend version

## Debug panel

Show:

- backend versions
- evidence contract version
- pages_crawled/pages_found/pages_received
- scan_status
- fallback status

## Acceptance checklist

- Incomplete review never shows a green health score.
- Access-limited scans never say the site is healthy.
- Large-site sample is labeled as representative, not exhaustive.
- Fix cards show `source_pages` when present.
- Repeated technical/template issues say `Your web person`.
- Existing recommendation cards still render when optional evidence fields are absent.
