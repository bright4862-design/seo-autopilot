# FixList production acceptance records

## Current status — Standard 150 beta candidate

**Status: CANDIDATE — production acceptance NOT met.**

| | |
|---|---|
| Candidate fingerprint | `053180f4bdc70857` |
| Classifier | `archetype_classifier_v12_locale_normalized_structural_routes` |
| Freeze source of truth | `data/beta-crawler-revision.json` (`status: "candidate"`) |
| Deployed commit | **not recorded** (`git_commit: ""`) |
| Acceptance report | **not recorded** (`acceptance_report: ""`) |

The v8 record below is **historical** and does **not** cover this candidate. It
accepted fingerprint `430813f2b15afa8f` with classifier
`archetype_classifier_v8_platform_product_routes`. The candidate code is
fingerprint `053180f4bdc70857` with classifier
`archetype_classifier_v12_locale_normalized_structural_routes`, URL frontier policy
`url_frontier_policy_v1_conservative_trap_guard`, and review calibration
`review_evidence_calibration_v6_health_score_v2`.

The immediately superseded candidate was `821d211419fd327e`; before that `cc385c397c97d579`, `b3345916049979a1`, `77588ce93276d608`, `68a16802a9c7a543`, `a43a71c61f32d9fb`, `2f4238b4989f3fd9`, `0544ce395811cbd5`,
`0fa7d98734efb3f2`, `7a95768cc8ee2076`, `58275d24191cf1cb`,
`7b0ec8c46654192b`, `5d94e93c54a9efb6`, `e18b72b2d0e159b8`, `cd31b3c1e5f9dd7c` and
`1ddf8085bc7721c4`.

The current candidate moved the fingerprint to `053180f4bdc70857` by finishing the job the
selected-versus-checked split started. The section rows were corrected first;
the sample-coverage disclosure beside them was not, and it is fed by exactly the
same pre-crawl selection fields -- it said "represented in the sample" and
"sampled" about numbers that describe an intention. There is no outcome to
substitute, because the crawl records checked coverage per path prefix and not
per market or page family, so `sampling_disclosure_v5_selection_language` says
"chosen for this scan" and "not chosen", which is what the producer actually
recorded.

The preceding `821d211419fd327e` candidate told a running
scan's owner what it is doing. Every active run said "This scan is still
working" whether it was queued, crawling or reviewing, while
`scanProgressModel()` sat unused beside it -- already careful that
`pages_found`, the Standard 150 cap and queue length are not progress
denominators. The result page now reads its phase, count and percentage from
that model, promises background durability only where the backend confirms it,
and calls a run slow only on its own persisted timestamps with a fresh
heartbeat (`customer_projection_v7_progress_heartbeat` carries that heartbeat
to the browser). The score number no longer counts up from zero: the digits are
the score from the first paint and only the ring stroke sweeps.

The preceding `cc385c397c97d579` candidate persisted where the
health score's points went. `compute_health_score_breakdown()` has always known
which area cost what and which ceilings bound the result, and none of it left
the scanner: the page showed a number and a grade, and the number is the first
thing an owner argues with. `health_score_explanation_v1` records the breakdown
alongside the score, sealed with it under
`standard_review_snapshot_hmac_v5_score_explanation` so the displayed
arithmetic cannot drift from the signed result. Rows sealed under v1 through v4
rebuild exactly as they were sealed and keep verifying.

The preceding `b3345916049979a1` candidate made a scan that produced no result
say which reason it stopped for. Every limited or
failed run previously rendered the same paragraph and the same advice, so a site
rate-limiting the scanner and a site whose sitemap never answered were
indistinguishable, and the owner of the first was told to retry into the same
block. `failure_state_presentation_v2_structured_limitation_reasons` reads the
producer's own structured codes into a closed taxonomy and publishes copy
written per reason, with the scanner's limitation sentence passed through a gate
rather than trusted.

The preceding `77588ce93276d608` candidate separated the URLs a scan *selects*
from the pages it actually *checks*. Sampling evidence previously reported only
pre-crawl selection, and the FixList labelled those counts "sampled" and
"represented"; on the September 6 matrix that made four sites show section rows
totalling 148 pages covered against 39 or 40 crawled. The crawler now records
outcome counts after the page cap, and coverage percentages are shown only where
an outcome exists.

The preceding `68a16802a9c7a543` candidate completed P1-B1 focused same-origin
path scans on top of the reviewed `0fa7d98734efb3f2` Standard 150 candidate. A focused child is explicitly confirmed, bound to a
discovered path prefix on the exact parent origin, admitted under a scope-aware
request fingerprint, and persisted as its own ScanRun/FixList with its own
150-page budget. Scope lineage is HMAC-bound under
`standard_review_snapshot_hmac_v4_focused_scope` for authoritative results and
`standard_limited_result_integrity_v4_focused_scope_effective_path` for limited results.
Limited focused results also bind the worker-observed
`effective_path_prefix` separately from the requested prefix, so a verified
same-origin market redirect cannot be lost or rewritten after sealing. The
customer reader reconstructs this as
`customer_result_reader_v5_acceptance_projection_parity` while keeping
historical limited v1/v2/v3 proof shapes readable. History exposes only the
bounded parent/path lineage needed to reopen the child. Subdomains remain
disabled. Path-prefix discovery now preserves the original
first-segment case so /Products and /products remain distinct on
case-sensitive sites, and server admission rejects traversal-like path segments
before URL parsing can normalize them away. This is versioned as
`focused_scan_scope_v3_fullsite_scope_type_case_preserved_candidates`,
`balanced_sitemap_buckets_v5_locale_collapsed_identity_scope_discovery_bounded_prefixes`,
`sampling_disclosure_v4_bounded_prefix_inventory_compatible`,
`scan_history_v3_focused_parent_children`, and
`customer_projection_v6_effective_scope_visible`. **Production acceptance has
not been run for this candidate.**

The immediately preceding `0fa7d98734efb3f2` candidate changed structural
classifier evidence so locale and market prefixes collapse before route counts
are evaluated, while raw page text remains unchanged. Repeated `/en/`, `/fr/`,
or country-prefixed copies of one route can no longer manufacture independent
structural evidence; distinct business routes remain distinct. This is recorded
as `archetype_classifier_v12_locale_normalized_structural_routes`.

The same candidate groups production repair rows on every valid, non-empty
`repair_fingerprint`, including rows whose identity is not marked stable. It
preserves the strictest priority, owner and effort, unions affected URLs, and
keeps the original family/locale evidence as child groups. Missing fingerprints
stay separate. This is recorded as
`repair_persistence_grouping_v2_valid_fingerprint_actions`.

The customer FixList now renders those child groups explicitly, links one safe
representative HTML page per group, and labels a locale only when the affected
URLs support it. PDF/export output is derived from the same canonical repair-card
model and reports the same action count as the customer FixList. This is recorded
as `repair_presentation_v5_evidence_groups_canonical_export`.

The `7a95768cc8ee2076` candidate keyed one
customer action on the scanner's own repair identity. The 35-site production
audit of 2026-08-31 found ten sites rendering nineteen groups where several
top-level FixItems carried a single `repair_fingerprint` — N26 showed one
repeated-title repair as nine separate tasks, Wise showed one as five. New
canonical scans now collapse stable, non-empty fingerprints before authority
signing and persist one top-level action. The original repair rows are retained
inside the signed finding evidence as child groups carrying family, locale,
representative URL, affected URLs, count and evidence state. Historical rows
remain readable through the bounded read-time projection path. Missing or
unstable fingerprints were not persistence-merged. Those semantics were recorded
as `repair_persistence_grouping_v1_stable_fingerprint_actions` and
`repair_presentation_v4_linked_evidence_pages`.

Sampling evidence from `balanced_sitemap_buckets_v2_locale_collapsed_identity_reserve`
is now disclosed to the customer without changing the 150-page contract. The FixList
shows route-pattern coverage, business-critical identity-page coverage, represented
markets/languages and page families, plus any explicitly recorded unsampled markets
or families. This customer-facing disclosure is versioned as
`sampling_disclosure_v1_customer_coverage`.

The same candidate makes count copy agree with its count. The audit found
"1 checked page are affected." on the customer projection: the noun agreed with
the count and the verb did not. The projection now derives both from the count,
the sitemap-orphan explanation stops reading "1 pages were found" where its own
title was already guarded, and the Python review summary singularises a
one-page crawl. That is recorded as `count_copy_v2_agreeing_verbs`.

The earlier v11 classifier candidate made booking a structural competitor. `structural_competitor`
capped content_blog when SaaS, retail, finance, nonprofit or local identity was
present, and booking was the one structural archetype missing from that list, so
a marketplace whose sample skewed editorial lost on article volume alone. That is
recorded as `archetype_classifier_v11_booking_competitor_finance_playbooks`.

This does not by itself resolve the audit's Musement and Tiqets cases. Booking
dominance requires a listing or ticket route in the sample; where the 150-page
sample surfaces none, the cap never applies. Those two need representative
sampling, and the classifier fixture records that limit explicitly.

The same candidate splits the finance playbook. One archetype covered businesses
that share none of each other's work, so the audit found N26, a digital bank, and
Alan, a health insurer, both told to start with loan program pages. A digital-bank
and an insurance sub-playbook now refine the advice inside the archetype on
homepage identity or more than one structural route; a correctly classified lender
keeps the lending default. The decision travels on the site fingerprint because the
review pipeline rebuilds the playbook from the archetype key alone.

The same candidate spends the 150-page budget on the business rather than on its
translation count. Translated copies of one route counted as independent members
of a family, so Wise spent slots on one plug-types page in three languages and one
about page in two markets; routes now collapse on their market prefix before the
budget is allocated. Commercial identity was never reserved, so a large site could
spend everything on whichever surface published the most URLs, which is why IKEA
was sampled as corporate pages and Musement and Tiqets as city and editorial
pages. Up to 24 identity and commercial routes are now reserved before
proportional fill, and coverage is reported by route signature and market as well
as by URL. That is recorded as
`balanced_sitemap_buckets_v2_locale_collapsed_identity_reserve`. The 150-page cap
is unchanged and still hard.

That reserve needed a prerequisite the audit did not name. The bookable-inventory
routes the archetype classifier already trusts -- tickets, attractions, tours,
venues, workshops, listings -- were not recognised by the page-template
classifier, so a ticketing route was a plain standard page. Neither family
allocation nor an identity reserve could tell it from any other page, and the
surface that proves a business is a marketplace was invisible to sampling. That is
recorded as `page_template_classifier_v4_bookable_inventory_routes`.

The same candidate makes affected pages reachable. Evidence URLs were plain text
and the site root read as a bare slash, so a customer could not tell which page
was affected or open it. One shared contract now decides how a page reads, whether
it may be a link, and what a screen reader announces; the root reads
"Homepage · /". A single protocol allowlist on the parsed URL decides linkability,
so a javascript: or data: value in evidence can never become an anchor href, and a
relative path with no trustworthy scanned origin is shown rather than resolved
against the app's own host. That earlier behavior was recorded as
`repair_presentation_v4_linked_evidence_pages`; the current customer/export
contract is `repair_presentation_v5_evidence_groups_canonical_export`.

The `58275d24191cf1cb` candidate had moved the fingerprint by grouping a
repair on the artifact the customer actually edits rather than on the page family
that happened to surface it. Ike's scan `6a9548bd0d7384cc66988ae4` persisted one
sitemap edit as five cards, because its redirecting URLs spanned legal, standard,
guide, contact and unclassified pages. A repair whose remediation surface is a
single shared artifact — the XML sitemap, the redirect map, canonical targets,
internal links — is now one card, with the page-family spread kept as evidence
inside it. Template repairs, where different templates genuinely need different
edits, still separate by family. That is recorded as
`repair_surface_grouping_v1_shared_artifact`.

The `7b0ec8c46654192b` candidate had moved the fingerprint by filling the page
family of affected URLs the crawl never recorded as pages, so that one uncrawled
redirect destination can no longer collapse an otherwise uniform group to `mixed`.
That is recorded as `repair_coverage_v4_corroborated_family_gap_fill`.

The `5d94e93c54a9efb6` candidate had moved the fingerprint by suppressing page-scope repair rows
whose URLs a validated group card of the same rule already lists — the duplicate
card defect seen on the Ike scan, where one `redirect_destination_noindex` family
card shipped alongside ~27 page-scope copies of itself. That is recorded as
`failure_evidence_dedup_v2_group_covered_page_rows`.

The `e18b72b2d0e159b8` candidate had moved the fingerprint by making acceptance
evidence fail closed when coverage,
classification, or measured worker memory is incomplete; measuring aggregate
parent + active-review-child RSS per review instead of reusing process-lifetime
child peaks; preserving historical limited-v1 signed reconstruction; and
preserving the acceptance report when a terminal-transition checkpoint write
fails. The customer projection is versioned as
`customer_projection_v4_acceptance_evidence_fail_closed`, acceptance evidence
as `standard150_acceptance_evidence_v2_aggregate_rss_fail_closed`, the
authoritative review attestation remains
`standard_review_snapshot_hmac_v3_acceptance_evidence`, and the limited-result
integrity contract remains
`standard_limited_result_integrity_v2_acceptance_evidence`. Production
acceptance has not been run. Earlier candidates `c0815d78c19d50db`,
`0b609da10fca57c7`, `3c9bd231295bc328`, and `3fccb57bd367dcfb` are historical.

The earlier Patch E candidate was `6e0368d4ac5d2a6b`. The stacked candidate
moved the fingerprint to `400f68e10999fc59` by adding
bounded multilingual page-family semantics, structural finance/member-retail
classification, terminal failure-evidence deduplication, action-band-consistent
summary copy, durable failure-state explanations, account-wide scan history,
and shared count grammar. Patch E had added
`admission_reconciliation_v1_exact_generation_barrier`: terminal admissions are
reconciled by exact request, scan, barrier generation and claim sequence; a
signed global claim barrier and independent intake/connectivity controls make
cutover drain state auditable. These operational authority changes require a
new production acceptance gate.

Patch D had previously made mixed-family evidence stay mixed:
a repair spanning several page families is partitioned instead of being labelled
with one family, and a coverage ratio is shown only when its numerator and
denominator are counted over the same URL set. That changes customer-visible
repair scope and coverage wording, so it requires a new production acceptance
gate.

The candidate before that was `fdd5906461a468d3`, superseded when Patch C made
the shared coverage decision
authoritative: a materially thin sample (38/3,689, 40/1,374) or an
inventory-unproven crawl is now provisional and release-ineligible instead of
sealing as complete. This is a customer-visible scoring and authority change, so
the freeze rule requires a new production acceptance gate before it can be
anything other than a candidate.

The candidate before that was `fbb06c2634b74ca6`, superseded when the authority
snapshot attestation moved to
`standard_review_snapshot_hmac_v2_coverage`. Patch B had added coverage fields
to the v1 HMAC payload, which changes the payload for rows sealed before those
fields existed and would have made every already-sealed result fail
re-verification. Reconstruction is now version-dispatched on the seal version
stored on each row, so v1 rows stay verifiable and only new rows seal under v2.

The candidate before that was `1f730bb039aef84e`, superseded when Patch B added the
`coverage_authority_evidence_v1` contract, so a change to how crawl coverage is
assessed and recorded moves release identity like any other component. Patch B
is diagnostic only: it changes no scan status, provisional state, release
eligibility, or score.

The candidate before that was `03dbfa67f4b708cf`, superseded when Patch A made
the cross-runtime Base44/frontend component markers participate in the same
release fingerprint, so a Base44 or UI behaviour change can no longer ship under
an unchanged release identity. Before that was `5caec7fdcabceee7`, superseded when Health Score v2
changed the authoritative review calibration. That is a customer-visible scoring/review behaviour change, so the
freeze rule requires a regenerated fingerprint and a new production acceptance
gate. The earlier move from `51c813a6219b4e70` to `5caec7fdcabceee7` was the URL
frontier trap-guard change; both prior fingerprints are historical for this
candidate.

By the freeze rule this document already states, that difference requires a
regenerated fingerprint, regression coverage, and **a new production acceptance
gate**. The fingerprint was regenerated and regression coverage exists; the
production acceptance gate has not been run. Presenting the v8 evidence as the
current baseline would assert a 20-site production validation of a build that
was never validated.

Issue #107 requires exact Git, scanner, backend, frontend and release
identifiers in one evidence pack. For the Standard 150 beta that pack is
incomplete: no deployed commit, no acceptance report, no production scan.
**Standard 150 beta acceptance is therefore No-Go on evidence.**

`data/beta-crawler-revision.json` is authoritative and is already truthful about
this — it records `status: "candidate"` and notes that production acceptance,
deployed commit, workflow runs and artifact digests are pending. This document
now agrees with it.

---

# FixList v8 production acceptance (historical)

## Decision

**Status: historical record — superseded by the v9 candidate above.**

This record froze the deployed FixList scanner and review behavior represented by fingerprint `430813f2b15afa8f`. Any change to a component version listed in `data/beta-crawler-revision.json` requires a new fingerprint and a new acceptance record.

## Release authority

- Deployed product commit: `6904c6376f8bcffeafb3fe87e72ce03a3d6c6be9`
- Release fingerprint: `430813f2b15afa8f`
- Classifier: `archetype_classifier_v8_platform_product_routes`
- Scanner: `python_scanner_v3_bounded_request`
- Review: `python_review_v2_structural_marketplace`
- Advanced crawl cap: 150 pages
- Production-validation trigger commit: `833774216636d350f66cf6a5ec4d3f88346b31e5`

Production authority was confirmed through `/health` and the optional `/revision` endpoint before the validation scans began.

## Accepted production evidence

- GitHub issue: https://github.com/bright4862-design/seo-autopilot/issues/71
- Independent validation comment: https://github.com/bright4862-design/seo-autopilot/issues/71#issuecomment-5007652581
- Corrected workflow run: https://github.com/bright4862-design/seo-autopilot/actions/runs/29613925642
- Run ID: `29613925642`
- Artifact ID: `8420116219`
- Artifact name: `deployed-production-20-site-validation-29613925642`
- Artifact size: `4517764` bytes
- Artifact created: `2026-07-17T21:30:01Z`
- Artifact expiry: `2026-08-16T21:29:59Z`
- Artifact digest: `sha256:1447e30f0099f118385635cbb1fb6267a4d15b741a81ebd2e0a55139df2ca547`

The artifact was downloaded independently and its SHA-256 digest matched GitHub's recorded digest.

## Production results

- 20/20 scan and review records completed
- 0 transport failures
- 0 fallback usage
- 0 page-cap violations
- 0 non-HTML FixItem evidence
- 0 detected secret leakage
- 19/20 expected archetypes matched
- Every site remained at or below the 150-page advanced crawl cap

Access-limited states remained distinct from classifier failures. Shopify was complete and non-provisional with `incidental_access_limited`; Allbirds correctly reported blocked/incomplete access and a provisional score.

## Focused regression outcomes

- Center Street Lending's sitewide canonical representative did not use `/contact`.
- Funbooker's grouped rate-limit finding retained its rule-specific 429 meaning.
- No image, Markdown, PDF, script, stylesheet, document, or other non-HTML URL appeared in FixItem evidence.
- Pretto returned findings in the larger production sample, so the bounded zero-fix state was not applicable.

## Known follow-ups

These items do not block the frozen v8 baseline:

1. Investigate the preserved IKEA evidence before changing classifier behavior. IKEA's global root classified as `content_blog` instead of the expected `ecommerce_specialty_retail`; locale routing, access evidence, and representative sampling must be examined first.
2. Improve consolidation of repeated redirect and sitemap recommendations across page and template families.
3. Keep score calibration deferred.
4. Keep renderer infrastructure, large asynchronous crawl modes, and performance auditing as separate roadmap decisions.

## Validation-reporting note

The temporary production runner reported `stale_or_missing_authority` for all 20 site summaries because it expected `archetype_classifier_version` inside each raw `/scan` response. This was a runner-only reporting false positive. `/health`, `/revision`, and every `/review` record carried the accepted v8 authority markers. The temporary runner and workflows were removed through cleanup PR #75.

## Freeze rule

The frozen baseline must not be changed by adjusting classifier weights, review grouping, scoring, thresholds, crawl limits, or evidence filters under the same fingerprint. A behavioral change requires a version-marker update, a regenerated fingerprint, regression coverage, and a new production acceptance gate.
