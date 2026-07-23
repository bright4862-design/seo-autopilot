# WordPress author archive and final-URL dedup release

## Scope

This candidate addresses two production acceptance follow-ups:

1. Preserve legitimate WordPress author archives such as `/author/admin` as public archive content instead of classifying the embedded author slug `admin` as an admin/login route boundary.
2. Deduplicate requested URLs after normalized final-URL identity so slash and non-slash seeds resolving to the same page retain one page record and do not consume unique crawl capacity.

True WordPress route noise remains suppressed before crawl admission, including `/wp-login.php`, `/wp-admin`, feed endpoints, XML-RPC/REST utility routes, and exact starter-content routes covered by the prior release.

## Version markers

- Route-boundary classifier: `route_boundary_classifier_v2_wordpress_author_archives`
- Final-URL deduplication: `final_url_dedup_v1_normalized_identity`
- Candidate fingerprint: `ab4f34bb0477c989`

## Local validation

- Focused Python regressions: 30 passed.
- Full Python suite: 432 passed.
- Frontend contract suite: 87 passed.
- ESLint: passed.
- TypeScript check: passed.
- Vite production build: passed.

## Production acceptance

Production acceptance remains pending until the merged Cloud Run and matching Base44 frontend are deployed. The required controls are:

- Lamanna Bakery Full Site: `/author/admin` must remain an archive and must not generate admin/login route-boundary FixItems; homepage final-URL identity must appear once; true WordPress route noise must remain absent from crawled pages and FixItems.
- Funbooker advanced control: 150 pages, complete, non-provisional, Python scanner and review, no fallbacks, authoritative persistence.

The wider 18-site audit remains paused until both controls pass.
