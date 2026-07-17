# Metadata and title evidence v9 candidate

## Scope

This candidate improves evidence accuracy and grouping without changing classifier weights, health-score calibration, crawl caps, deployment settings, or review thresholds.

### Meta-description existence states

The scanner now records one explicit state per HTML page:

- `missing`: no standard meta-description element exists
- `present_empty`: the element exists with an empty content value
- `present_valid`: at least one usable content value exists
- `malformed`: the element exists without a usable content attribute
- `head_parse_boundary`: the response did not expose a normal raw `<head>` boundary
- `access_inconclusive`: HTTP/access/content-type evidence is not suitable for a metadata claim
- `raw_html_incomplete`: successful response evidence was empty or incomplete

Only `missing` feeds the existing missing-description rule. Empty and malformed markup receive distinct rule identities and remain score-equivalent to the previous combined metadata gap.

### Search-title evidence

Duplicate titles are consolidated into distinct contexts:

- localized or market pages
- clean/query-parameter variants
- repeated generic CMS fallback titles
- true template duplicates

Title-width evidence uses a deterministic estimated pixel width and is informational. Generic fallback-title and title-width findings are explicitly non-scoring.

## Production-derived fixtures

- Funbooker: separates absent meta-description tags from present-but-empty tags.
- Stripe: treats repeated locale product titles as verification evidence rather than automatic rewrite tasks.
- Sephora: separates clean category/query variants and detects `Sites-Sephora_FR-Site` as a generic fallback title.

## Acceptance before release

1. All scanner and frontend contracts pass.
2. The candidate fingerprint matches the recorded component set.
3. Funbooker is rerun and corrected missing/empty/malformed counts are preserved.
4. Sephora confirms query-variant and fallback-title grouping.
5. Health-score calibration remains unchanged.
