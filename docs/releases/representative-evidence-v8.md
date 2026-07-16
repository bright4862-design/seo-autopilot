# Representative evidence v8 candidate

This candidate ranks FixList representative URLs by archetype and route-family business importance while demoting utility, authentication, legal, cart, checkout, and reservation-management routes.

It also restricts generic page-level findings such as `broken_page` to HTML documents, closing the non-orphan asset-evidence gap found during the 20-site production audit.

Release markers:

- Representative page: `business_representative_page_v2_archetype_route_families`
- Page-level asset evidence: `page_level_asset_evidence_v2_html_only`
- Classifier remains: `archetype_classifier_v7_html_route_app_distribution`
- Candidate fingerprint: `561db6e131da53a9`
- Crawl cap remains 150 pages

Focused production acceptance is required before this candidate is frozen.
