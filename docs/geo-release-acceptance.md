# GEO readiness and scanner evidence release acceptance

Status: implementation, task reviews and combined local source gates pass. Final whole-branch review, exact-SHA CI and production release verification remain pending. No production activation is claimed by this document. Full source gates, exact-SHA CI, deployed source checks and production acceptance remain required.

## Scope

The release adds an experimental, deterministic GEO readiness assessment to the existing Standard 150 result. It consumes retained accepted raw HTML, performs no extra requests and changes neither SEO scoring nor the 150-page cap. It does not measure AI citations, external indexing, provider ranking or factual accuracy. Numeric scores require an authoritative parent, an accepted exact entry resource and explicit coverage gates. Missing evidence remains unknown.

The scanner blueprint contributes three release prerequisites: preserving the published request path, excluding out-of-origin sitemap locations without rewriting their host/scheme, and distinguishing absent alt attributes from explicit empty alt. The broader blueprint backlog is tracked in `geo-blueprint-release-checklist.md`; its supplied live-site counts are not acceptance observations.

## Reviewed interfaces

- The bounded raw-HTML adapter has independent negative fixtures for challenge responses, hidden content, malformed policy, author-token matching and extraction failure isolation.
- The optional runtime result is refreshed after existing evidence/coverage gates using the full retained crawl. Redirect-source entry evidence remains conservatively unverified; there is no inferred equivalence between distinct slash resources.
- New snapshots use internal marker `standard_review_snapshot_hmac_geo_v1`; public routes remain V6. Independently frozen pre-GEO snapshots and HMACs preserve versions 1–6. Historical GEO injection cannot change the authenticated result.
- New preview marker `standard_customer_preview_hmac_v2_geo_readiness` retains the original v1 verification domain and bytes. Free responses contain only the eight approved summary fields; paid evidence requires the existing verified result path.
- The server independently recomputes scores, coverage, bounds, counts, gates and finding membership from bounded observations. It does not re-fetch HTML. Python/JavaScript numeric parity includes a binary half-even display-rounding fixture.
- A GEO evaluator error produces a fixed null/error envelope without exception text or content; independently valid SEO survives. Arbitrary malformed GEO fails authority validation.

Task 2 independent review: 58 focused Node tests and 56 Python tests passed. The frozen preview version case was deliberately deferred with release generation; this is not an unskipped full-release verdict. Root separately reran all 11 dedicated GEO authority cases successfully.

## Schema and rollout preparation

Read-only production schema comparison found one additive `ScanRun.geo_readiness` property. All existing ScanRun properties, required fields and access rules matched; FixList and FixItem matched. This must be refreshed at cutover. Use the named schema connector; `base44 entities push` is prohibited by the deployment contract.

Authenticated Base44 app access is available. Merge and deployment are user-authorized, subject to the existing gates. Release order is exact reviewed source and CI, zero-traffic worker staging, named schema update and verified Base44 publishing, then verified worker promotion with rollback. Source SHA, fingerprint, all six V6 build/activation identities, queue and private service checks must agree. Follow the repository's production acceptance contract rather than treating a successful build as a successful scan.

## Measurement limitations

Weights and thresholds are transparent product assumptions, not empirically validated provider formulas. The sample is bounded and is not a random estimate of the whole site. Structural presence does not establish substantive quality. An assessed score of 100 with incomplete coverage is possible, so the UI must show coverage and the unresolved-outcome range alongside it. Narrow semantic applicability can leave ordinary pages unscored. External citation monitoring and broader domain-stratified customer calibration remain separate work; no claims of commercial uplift are authorized by these fixtures.

Ironwood remains access-limited. Its reported six HTTP 202 SiteGround challenges show that changing the two tested transparent UAs did not restore access. They do not isolate IP, header, cadence or TLS causes. GEO does not change that conclusion or turn challenge noindex headers into site defects.


## Template sampling sensitivity check

Root ran the actual accepted-HTML adapter on two independently labelled variants of the complete schema-free article fixture: one contains ordinary text `Published in 1998`, the other a visible `Published in {{year}}` token. Both retain an explicit main subject, address, author link, labelled historical date, linked quotation source, observed internal discovery and allowed OAI search policy. Expected difference: only template_integrity fails on the token variant; an old valid date is not a failure. No live website is represented.

| Retained sample | Score | Coverage | Unrounded outcome range | Verified token pages |
| --- | --- | --- | --- | --- |
| 90 ordinary + 10 token pages, equal page weight | 99 | 100% | 99.166667–99.166667 | 10 |
| One representative of each template, equal template weight | 96 | 100% | 95.833333–95.833333 | 1 |

Actual adapter output matched the independently calculated masses: one of 12 checks fails on 10% versus 50% of its sampled pages. Integer score rounding explains the difference from the unrounded range. This demonstrates that repeated templates influence the aggregate even with complete evidence. Freeze this version as equal-page within each check, disclose sampled pages, and keep affected-page counts/actions visible. These synthetic results do not validate equal-page weighting as the best business-impact metric and do not replace a domain-stratified product study.


## Combined candidate

Candidate component fingerprint: `47793ce37ca20523`. Scanner P0 commit: `15cd1ef65b9e3505bfd601ef02bc6e27313fbc93`. Generated release contracts have been refreshed through the canonical generator; public routes remain V6.

Task 3 passed independent rendered React checks and 41 focused UI/export tests after fixing the actual location-template repair alias. Task 4 passed independent 120-test scanner review. Before generation, the full scanner suite passed 1,573 cases with 18 skips and only the known frozen-revision drift; those are interim results, not the final combined verdict.


## Final local source gate

The combined `scripts/release_gate.sh` run on source commit `9f6aa715d633c725a6dd2b256abd1646f1e91fe5` reports **SOURCE READY**. Lint, typecheck, all 1,376 frontend tests (zero skips), production build, Base44 package integrity, root Python tests, scanner API tests, frozen component comparison and manifest determinism passed. The prior stale reader-version assertions and acceptance-document fingerprint were corrected without relaxing their gates.

The same command reports **DEPLOYMENT ENVIRONMENT BLOCKED** locally because gcloud, Docker and cloud deployment parameters/credentials are absent. Do not interpret that as a source failure or invent local credentials. The existing owner-triggered GitHub workflow provides the established keyless cloud lane; it still must succeed on the merged exact SHA. Base44 CLI identity and the intended app's function inventory have been verified read-only. No production mutation is covered by this local gate.

A live result reload requires an authenticated customer browser session. The available browser currently loads the public site without such a session. A local Base44 CLI exec identity probe could not complete because Deno's npm SDK download connection was refused; it was cancelled without mutation. These limitations must be resolved through the existing authenticated paths before claiming live acceptance.
