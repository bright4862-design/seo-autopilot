# PR4 Evidence Generators Roadmap

This roadmap prepares the next backend PR after PR #3 (`Harden AI review evidence contract`) is reviewed and merged.

PR #4 should add high-signal evidence generators only. It should not rely on AI wording or inferred claims when scanner evidence is absent.

## Guardrails

- Do not invent evidence.
- Do not turn crawler artifacts into customer-facing broken-page claims.
- Do not create content/template fixes for failed, blocked, or HTTP >= 400 pages.
- Every generated fix must include `source_pages` and an evidence-derived `current_value`.
- Technical/template/routing/canonical/schema/blocked-access fixes should be owned by `your_web_person`.
- Keep PR #4 separate from PR #3 so the review-path evidence contract remains easy to verify.

## Generator 1: canonical_to_other_url

Trigger when an indexable 200 page has a canonical URL on the same host but with a different path.

Required evidence:

- affected page path
- canonical target path
- status code 200
- indexable true unless robots metadata explicitly says noindex

Expected fix fields:

- `rule`: `canonical_to_other_url`
- `category`: `canonical`
- `who_can_do_this`: `your_web_person`
- `source_pages`: affected page paths
- `current_value`: examples like `/products/a canonicalizes to /collections/a`

Do not trigger for:

- failed pages
- noindex pages
- self-referencing canonicals
- blank canonicals; those belong to `canonical_missing`

## Generator 2: canonical_to_other_domain

Trigger when an indexable 200 page canonicalizes to another hostname.

Required evidence:

- affected page path
- canonical target hostname
- status code 200
- indexable true unless robots metadata explicitly says noindex

Expected fix fields:

- `rule`: `canonical_to_other_domain`
- `category`: `canonical`
- `priority`: high or critical
- `who_can_do_this`: `your_web_person`
- `source_pages`: affected page paths
- `current_value`: examples like `/services canonicalizes to vendor.example.net/services`

Do not trigger for known intentional cross-domain syndication unless the scanner can prove that intent. For now, emit as a technical verification task, not as a definitive penalty claim.

## Generator 3: missing/wrong schema

Trigger on important page families with no relevant structured data.

Initial page families:

- `activity_detail`
- `product_page`
- `collection_page`
- `loan_program`
- `location_landing`
- `booking_or_checkout`

Expected fix fields:

- `rule`: `missing_schema` or a more specific rule such as `product_schema_missing`
- `category`: `schema`
- `who_can_do_this`: `your_web_person`
- `source_pages`: affected page paths
- `current_value`: examples like `3 activity/detail pages have no detected JSON-LD schema`

Do not trigger for:

- failed pages
- internal/auth route boundaries
- low-value archive/tag pages
- pages where schema was not measurable because the page was blocked

## Generator 4: duplicate_route_casing

Trigger when two or more crawled URLs differ only by casing and both are crawlable/indexable.

Required evidence:

- exact path variants
- status code 200 for each variant
- indexability evidence

Expected fix fields:

- `rule`: `duplicate_route_casing`
- `category`: `canonical`
- `who_can_do_this`: `your_web_person`
- `source_pages`: all casing variants
- `current_value`: examples like `Both /dashboard and /Dashboard were crawlable`

Do not trigger for:

- one variant redirects cleanly to the canonical casing
- one variant is noindex or blocked
- URLs that are crawler artifacts

## Generator 5: money_path_blocked

Trigger when HTTP 429, bot protection, connection verification, or access denial affects a money path.

Money-path examples:

- `/apply-now`
- `/request-a-payoff`
- `/document-exchange`
- `/checkout`
- `/booking`
- `/reservation`
- `/cart`
- `/quote`
- `/devis`
- `/demo`
- `/contact-sales`

Expected fix fields:

- `rule`: `money_path_blocked`
- `category`: `web_dev`
- `primary_defect_class`: `blocked_access`
- `priority`: high or critical
- `who_can_do_this`: `your_web_person`
- `source_pages`: pages linking to the blocked URLs when available
- `current_value`: examples like `/apply-now returned HTTP 429 and was linked from /loans/dscr`

Important copy:

- Say this is crawler-access evidence.
- Ask the web person to verify server/CDN/firewall/bot-protection logs.
- Do not claim customers definitely see the block unless logs confirm it.

## Acceptance checklist

- All new generators skip failed pages unless the generator is specifically about failed/blocked access.
- Every generated fix has `affected_pages`, `source_pages`, and `current_value`.
- Repeated issues are grouped by canonical `page_template_family`.
- Funbooker activity pages group as `activity_detail`.
- Pretto and Center Street finance paths group as `loan_program` or related finance families.
- Technical fixes route to `your_web_person`.
