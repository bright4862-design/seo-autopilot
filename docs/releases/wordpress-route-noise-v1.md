# WordPress route-noise filtering

## Root cause

WordPress themes, starter content, feeds, login links, Jetpack, and REST endpoints can expose technical or default URLs as crawl candidates. These routes were being treated as normal HTML pages, consuming scan slots and producing customer-facing canonical, redirect, metadata, and content recommendations.

The Lamanna Bakery regression included:

- `/wp-login.php` and login query variants;
- `/feed` and `/comments/feed`;
- `/hello-world`;
- `/category/uncategorized`.

## Patch

`artifact_filter_v4_wordpress_route_noise` adds one shared, early filter used by both sitemap ingestion and the live scanner queue.

It suppresses only high-confidence WordPress noise:

- WordPress login, admin, REST, XML-RPC, cron, signup, activation, and comment-post endpoints;
- feed and trackback endpoints;
- REST, reply-to-comment, and feed query routes;
- exact WordPress starter routes: `/hello-world`, `/sample-page`, and `/category/uncategorized`.

Suppressed URLs remain in bounded artifact evidence with `wordpress_route_noise`, but cannot consume a page slot or generate page-level SEO findings.

## Safety boundaries

The filter deliberately keeps normal WordPress content crawlable, including:

- non-default category pages;
- tag and author archives;
- posts and pages;
- product and collection routes;
- WordPress sitemap XML;
- URLs that merely contain similar words.

## Regression coverage

Tests lock:

- the Lamanna route set and common query variants;
- preservation of legitimate WordPress public routes;
- explicit artifact provenance;
- suppression during sitemap ingestion;
- the shared filter identity used by sitemap and scanner queue paths.

## Candidate revision

The frozen candidate fingerprint advances to `a375c7d739ba9adc`.
