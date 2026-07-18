# Metadata and title evidence v9 candidate

## Status

**Candidate only — not frozen and not accepted for production yet.**

The committed candidate record intentionally leaves `git_commit` unset. After focused production acceptance, the release record must be rewritten with the actual deployed merge commit, acceptance timestamp, workflow run IDs and artifact digests before its status becomes `frozen_beta`.

## Scope

This candidate improves evidence accuracy and grouping without changing classifier weights, health-score calibration, crawl caps, deployment settings, or review thresholds.

### Meta-description existence states

The scanner records one explicit state per page record:

- `missing`: a final HTTP 200 HTML response has no standard meta-description element
- `present_empty`: the element exists with an empty or whitespace-only content value
- `present_valid`: at least one usable content value exists
- `malformed`: the element exists without a usable content attribute
- `head_parse_boundary`: raw HTML did not expose a literal `<head>` boundary, so existence is retained as unclassified evidence rather than a problem
- `access_inconclusive`: the record is not a final HTTP 200 HTML response, or access/fetch evidence is unsuitable for a metadata claim
- `raw_html_incomplete`: a successful HTML record did not contain usable raw source

Only `missing` feeds the existing missing-description rule. Empty and malformed markup receive distinct rule identities and remain score-equivalent to the previous combined metadata gap. Redirect, partial-content, blocked, failed and non-HTML records cannot produce description findings.

### Search-title evidence

Duplicate titles are consolidated into distinct contexts:

- localized or market pages
- clean/query-parameter variants
- true template duplicates

Generic CMS fallback titles are owned by the page-level fallback detector and are not emitted a second time by duplicate-title bucketing. Title-width evidence and every contextual duplicate-title finding are informational and explicitly non-scoring in v9.

Locale detection accepts known market segments and language-country pairs such as `fr-fr`; arbitrary two-letter path segments such as `/on/` are not treated as locales. Generic fallback detection keeps known CMS signatures such as `Sites-Sephora_FR-Site` but does not flag a normal `Home | Brand` homepage title.

## Production-derived fixtures

- Funbooker: separates absent meta-description tags from present-but-empty tags.
- Stripe: treats repeated locale product titles as verification evidence rather than automatic rewrite tasks.
- Sephora: separates clean category/query variants, detects `Sites-Sephora_FR-Site` once through the page-level fallback path, and does not treat Demandware `/on/` routes as locales.

## Required deployment sequence

The frontend authority contract intentionally rejects scans when its expected fingerprint and the deployed scanner fingerprint differ. Use this order:

1. Merge the accepted candidate to `main`.
2. Deploy the Cloud Run scanner/review candidate from that merge commit.
3. Verify `/health` and `/revision` return fingerprint `52348dd1f3b77700`, both new evidence-version markers and the deployed commit.
4. Publish the Base44/frontend bundle that expects `52348dd1f3b77700`.
5. Confirm the release-authority gate reports eligible.
6. Run focused Funbooker and Sephora acceptance.
7. Record the accepted commit, timestamp, run IDs and artifact digests; only then change the revision status to `frozen_beta`.

Publishing the frontend before Cloud Run is updated will intentionally make scans non-authoritative until the fingerprints match.

## Acceptance before release

1. All scanner and frontend contracts pass.
2. The candidate fingerprint matches the recorded component set.
3. Funbooker is rerun and corrected missing/empty/malformed/excluded counts are compared with the seven-URL diagnostic ground truth.
4. Sephora confirms query-variant grouping, one fallback-title context and no `/on/` locale misclassification.
5. Stripe confirms localized duplicate-title verification copy and unchanged score.
6. Signal and WPBeginner remain null controls with identical scores and no new findings.
7. Health scores remain byte-identical across the eight-control regression set except no change is permitted from the new non-scoring title evidence.
8. No URL or title key appears under both a legacy duplicate-title rule and a contextual v9 title rule.
