# Complete Small-Site Inventory Authority v1

## Problem

Normalized final-URL deduplication can correctly reduce a genuinely small site below the review layer's four-usable-page confidence threshold. Lamanna Bakery exposed this interaction: four discovered URL identities resolved to three unique retained HTML pages because the bare hostname and trailing-slash homepage were the same final page.

The crawl itself was complete and healthy:

- the queue was exhausted;
- no crawl deadline was reached;
- no fetches failed;
- no URLs remained queued;
- every crawled page was usable HTML; and
- every discovered identity was accounted for by either a retained page or a normalized final-URL duplicate.

Treating that result as insufficient evidence made the release gate reject a complete small-site inventory.

## Correction

Review quality gate `review_quality_gate_v2_complete_small_site_inventory` preserves the normal four-page minimum but recognizes a bounded complete-small-site exception when all of the following are true:

1. The review received one to three usable HTML pages.
2. Every crawled page is usable HTML.
3. `pages_found` is no greater than retained crawled pages plus normalized final-URL duplicates.
4. The crawl queue was exhausted.
5. The crawl deadline was not reached.
6. The failed-fetch count is zero.
7. No URLs remain queued.

When these conditions hold, classification evidence sufficiency is recorded as `complete_small_site_inventory`, the result can receive a health score, and the release gate may be authoritative. Classification confidence remains capped at 0.65 because the inventory is complete but small.

## Safety controls

The global evidence threshold is not lowered. A one-to-three-page crawl remains inconclusive when any inventory-accounting proof is missing, when discovery exceeds retained pages plus deduplicated identities, when the queue is not exhausted, when a deadline is hit, when a fetch fails, or when queued URLs remain.

Blocked, rate-limited, incomplete, provisional, fallback, stale-fingerprint, and evidence-quality-blocked scans remain ineligible.

## Acceptance scope

- Re-run Lamanna Bakery only after deployment.
- Verify one normalized homepage deduplication.
- Verify `/author/admin` remains a legitimate WordPress author archive and produces no admin/login route-boundary false positives.
- Verify Python scanner and Python review, both fallbacks false, non-provisional status, authoritative FixList, and release-gate eligibility.
- Keep the 18-site audit paused.
