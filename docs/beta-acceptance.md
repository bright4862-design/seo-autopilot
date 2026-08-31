# FixList production acceptance records

## Current status — Standard 150 beta candidate

**Status: CANDIDATE — production acceptance NOT met.**

| | |
|---|---|
| Candidate fingerprint | `ad3c2b0a8185ee41` |
| Classifier | `archetype_classifier_v10_structural_finance_member_retail` |
| Freeze source of truth | `data/beta-crawler-revision.json` (`status: "candidate"`) |
| Deployed commit | **not recorded** (`git_commit: ""`) |
| Acceptance report | **not recorded** (`acceptance_report: ""`) |

The v8 record below is **historical** and does **not** cover this candidate. It
accepted fingerprint `430813f2b15afa8f` with classifier
`archetype_classifier_v8_platform_product_routes`. The candidate code is
fingerprint `ad3c2b0a8185ee41` with classifier
`archetype_classifier_v10_structural_finance_member_retail`, URL frontier policy
`url_frontier_policy_v1_conservative_trap_guard`, and review calibration
`review_evidence_calibration_v6_health_score_v2`.

The immediately superseded candidate was `58275d24191cf1cb`; before that
`7b0ec8c46654192b`, `5d94e93c54a9efb6`, `e18b72b2d0e159b8`, `cd31b3c1e5f9dd7c` and
`1ddf8085bc7721c4`.

The current candidate moved the fingerprint to `ad3c2b0a8185ee41`. It keys one
customer action on the scanner's own repair identity. The 35-site production
audit of 2026-08-31 found ten sites rendering nineteen groups where several
top-level FixItems carried a single `repair_fingerprint` — N26 showed one
repeated-title repair as nine separate tasks, Wise showed one as five. A card is
now keyed on that fingerprint wherever the scan recorded one, with each persisted
row kept as a child evidence group carrying its family, count, representative
page and affected URLs. Rows the scan gave no fingerprint keep the previous
rule-and-repair-type key: an absent identity is not evidence that two repairs are
the same one. That is recorded as
`repair_presentation_v3_fingerprint_keyed_actions`.

The same candidate makes count copy agree with its count. The audit found
"1 checked page are affected." on the customer projection: the noun agreed with
the count and the verb did not. The projection now derives both from the count,
the sitemap-orphan explanation stops reading "1 pages were found" where its own
title was already guarded, and the Python review summary singularises a
one-page crawl. That is recorded as `count_copy_v2_agreeing_verbs`.

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
