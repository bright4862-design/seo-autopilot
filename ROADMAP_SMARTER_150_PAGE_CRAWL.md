# Smarter 150-Page Advanced Crawl Roadmap

The current Python advanced crawl budget is intentionally capped at 150 pages. The next crawler improvement should make those 150 pages more representative before increasing the raw cap.

## Product framing

Advanced Scan should be described as:

> FixList checked up to 150 representative pages and grouped repeated template issues.

It should not claim:

> FixList crawled your whole website.

## Current constraints

- `advanced` max pages: 150
- timeout: 90 seconds
- default concurrency: 8
- sitemap discovery can exceed crawl budget, but claimed crawl pages stop at the advanced cap

## Goal

Make the 150 pages include the pages most likely to reveal high-impact SEO and website setup issues.

## Crawl prioritization

The queue should prioritize:

1. Homepage
2. URLs from XML sitemap
3. Known money paths
4. Product/detail/listing/category paths
5. Location pages
6. Trust/legal/contact pages
7. Recently discovered internal links from high-value pages
8. Representative samples from lower-priority sections

## Money-path boost patterns

Examples:

- `/apply`
- `/apply-now`
- `/request-a-payoff`
- `/document-exchange`
- `/checkout`
- `/booking`
- `/reservation`
- `/quote`
- `/devis`
- `/pricing`
- `/demo`
- `/contact-sales`
- `/products/`
- `/collections/`
- `/annonce/`
- `/voir`
- `/loans/`
- `/pret-immobilier/`

## Deprioritize patterns

Examples:

- `/tag/`
- `/author/`
- `/archive/`
- `/page/`
- `/feed/`
- old dated blog/news paths
- duplicate query parameter versions
- obvious asset or encoded crawler artifacts

## Template-balanced sampling

Crawler should avoid spending all 150 pages in one section.

Suggested buckets:

- homepage
- route_boundary
- activity_detail
- product_page
- collection_page
- loan_program
- calculator
- comparison_page
- location_landing
- guide_article
- legal_info
- contact
- standard

Suggested behavior:

- keep at least a small sample per detected family
- raise sample count for money families
- cap low-value archive/tag/blog pagination pages
- preserve failed/blocked pages as evidence even if they are not content-auditable

## New scan coverage fields

Add these fields to the scan response:

```json
{
  "crawl_strategy_version": "advanced_priority_sampler_v1",
  "crawl_budget": {
    "mode": "advanced",
    "max_pages": 150,
    "timeout_seconds": 90,
    "concurrency": 8
  },
  "crawl_coverage": {
    "pages_found": 983,
    "pages_crawled": 150,
    "queued_remaining": 833,
    "template_families_seen": {
      "activity_detail": 70,
      "collection_page": 20,
      "guide_article": 40
    },
    "template_families_sampled": {
      "activity_detail": 50,
      "collection_page": 20,
      "guide_article": 10
    },
    "money_pages_sampled": 42,
    "low_value_pages_sampled": 8
  }
}
```

## UI implications

If `queued_remaining > 0` or `pages_found > pages_crawled`, the frontend should say:

> FixList checked a representative sample of this larger site.

If blocked pages dominate the crawl, the frontend should say:

> Scan incomplete. FixList could not inspect enough pages because access was blocked or rate limited.

## Future scale tiers

After smarter 150-page sampling works:

- Standard advanced: 150 pages
- Pro: 500 pages async
- Agency: 1,000-5,000 pages async
- Enterprise: background crawl with continuation tokens and crawl history

## Acceptance checklist

- 150-page crawl includes money pages when available.
- Large marketplaces do not spend the whole budget on blog/archive pages.
- Large ecommerce sites sample products and collections.
- Finance/lead-gen sites sample loan/application/location/trust pages.
- Scan response exposes coverage, not just page count.
- UI can safely distinguish full crawl vs representative sample.
