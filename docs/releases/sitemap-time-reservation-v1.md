# Sitemap time reservation v1

## Scope

- Sitemap discovery receives a bounded sub-deadline.
- At least 65% of the backend request budget remains reserved for page crawling.
- A final response reserve remains after worker crawling.
- Partial sitemap discoveries still seed the crawl queue.
- Timing, queue and failure diagnostics are persisted and included in debug exports.

## Production acceptance

1. IKEA France must crawl pages instead of returning 149 discovered and 0 crawled solely from sitemap time exhaustion.
2. Nordic Nest must progress beyond the previous five-page result when access permits.
3. Funbooker must remain complete at the 150-page cap.
