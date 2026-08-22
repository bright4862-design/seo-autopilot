# FixList production acceptance records

## Current status — Standard 150 beta candidate

**Status: CANDIDATE — production acceptance NOT met.**

| | |
|---|---|
| Candidate fingerprint | `d23f6a2ad97da082` |
| Classifier | `archetype_classifier_v9_local_business_hospitality` |
| Freeze source of truth | `data/beta-crawler-revision.json` (`status: "candidate"`) |
| Deployed commit | **not recorded** (`git_commit: ""`) |
| Acceptance report | **not recorded** (`acceptance_report: ""`) |

The v8 record below is **historical** and does **not** cover this candidate. It
accepted fingerprint `430813f2b15afa8f` with classifier
`archetype_classifier_v8_platform_product_routes`. The shipping code is
fingerprint `d23f6a2ad97da082` with classifier
`archetype_classifier_v9_local_business_hospitality`, URL frontier policy
`url_frontier_policy_v1_conservative_trap_guard`, and review calibration
`review_evidence_calibration_v6_health_score_v2`.

The immediately superseded candidate was `d23f6a2ad97da082`. The fingerprint
moved to `e5088c4055cb04e9` when Patch D made mixed-family evidence stay mixed:
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
