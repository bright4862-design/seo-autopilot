# Full scanner blueprint: evidence, prioritization, coverage and release

Status: written design approved by the user on 2026-09-19 with the explicit instruction "Approved—start implementation". Implementation is in progress; no deployment is claimed by this document.

## Authority and outcome

Implement and deploy the complete applicable **FixList Scanner Gap Analysis & Blueprint**, dated 18 September 2026, not only the GEO subset. The supplied 18-page PDF has SHA256 `c76efed66f373e2455c326b2804a8148489509f8625f84377b9f21bef4f1f6f9`. Its reported live-site findings are hypotheses to reproduce, not current facts to manufacture in tests or reports.

User-approved direction: implement in stages within the existing scanner, preserve old reports and current crawl/security limits, and deploy only after full blueprint acceptance checks pass. This design extends the approved GEO design; it does not remove its privacy, entitlement, evidence or authority requirements.

The goal remains the full blueprint. Completing a stage, passing existing tests, merging a PR, synchronizing Base44 or staging a worker does not establish completion.

## Current evidence

The clean starting commit and GitHub main are `7a744a501416b1b9feac462511071fc9f08e1ba1`. That release contains GEO readiness, published-request URL preservation at fetch time and absent-versus-empty image-alt extraction. Read-only audits found additional gaps in downstream URL identity, visible template detection, indexability gating, scoring/grouping, probe coverage and handoff v2.

The live Base44 editor has shown both an ongoing sync indicator and an explicit GitHub fetch failure. Its read-only development snapshot and the deployed runtime are separate surfaces; neither may be assumed to match GitHub. The existing release scripts verify the site and active function build identities. No change to that deployment wrapper is justified solely by the editor's sync error.

## Architecture and alternatives

Use the existing Python Standard 150 crawl and accepted-evidence gate, followed by deterministic extractors and analyzers, the existing durable authority path, and compatible customer projections. Add one shared bounded probe scheduler for checks requiring new requests. Introduce explicit new evidence/assessment revisions for changed semantics; keep legacy reconstruction intact for historical reports.

This approach is preferred to either a second independent scanner (duplicate crawl, security and lifecycle ownership) or a wholesale rewrite of report production (larger compatibility and rollback risk). Neither alternative is needed to satisfy the blueprint.

The implementation is divided into four dependent subprojects, each with its own executable plan and regression evidence:

1. Evidence correctness: identity, template and image evidence, search-facing applicability and the synthetic acceptance corpus.
2. Coverage: shared probes, sitemap/link integrity, content/graph/local/freshness/weight evidence, optional connected enrichment.
3. Decisions and delivery: four-factor ranking, explicit root causes, honest counts, score caps, preview selection and handoff v2.
4. Compatibility and deployment: seal/projection integration, complete acceptance, exact-source release and live verification.

Independent read-only reviews and independent test runs can proceed in parallel. One owner writes each shared interface; integration of producer, verifier and reader changes is serialized.

## Invariants

- Standard 150 retains its 150 assessed-page limit. Other scan modes retain their existing assessed-page limits.
- All network checks use the existing safe request/DNS/SSRF controls, robots policy, body ceilings, redirect checks, rate-limit handling and overall scan deadline.
- No automatic sibling-subdomain crawl. Apex/www equivalence requires the already-supported verified landing redirect; changing one scope does not authorize the other site.
- No Googlebot or browser impersonation, CAPTCHA handling, proxy bypass or access-protection evasion. Use transparent FixList identity.
- The new probe pool shares a finite request budget with crawl claims and must report attempted, completed, skipped and exhausted counts. Redirect hops and retries consume that budget. Budget exhaustion is unknown coverage, not a successful check.
- Existing durable admission, owner binding, cancellation, privacy and V6 public routes remain intact unless a reviewed compatibility change requires otherwise.
- Old signed reports are verified with their original reconstruction rules. Do not rewrite stored reports or calculate new scores while reading old reports.
- Every new assessment field affecting displayed evidence, counts, priority or scores is authenticated. Free preview cannot expose hidden findings through new fields or exports.
- No broad entity push, signing-key rotation, repository disconnection, forced reconciliation, pricing change or unrelated UI redesign.

## Requirement register and acceptance

| ID | Required behavior | Evidence that proves it |
| --- | --- | --- |
| B01 | Preserve published/request/final URL provenance; keep identity separate from family classification and request scheduling | Three accepted 200 responses at `/x`, `/x/`, `/X` remain three affected pages through extraction, review, persistence and export; actual verified redirect aliases can share one final-page identity while retaining source observations; remove the trailing-slash ranking workaround only after published-redirect evidence regressions prove it unnecessary |
| B02 | Preserve reserved escapes, meaningful query differences and verified host/scheme distinctions in page identity | Shared Python/JavaScript fixtures distinguish encoded delimiters, query variants and unrelated origins; the observed request identity retains its query, while tracking-parameter scheduling policy remains separate and documented; family labels may remain normalized without changing page counts |
| B03 | Distinguish absent alt from explicit empty alt, with conservative applicability | Empty/whitespace alt does not produce a missing-attribute repair; absent alt remains observable; material-image applicability uses evidence beyond merely being inside `main`; uncertain images are review evidence, not confidently labelled decorative or harmful |
| B04 | Detect unresolved visible templates generally, not only location tokens | Fixtures cover `{{…}}`, `{%…%}`, `#TOKEN#`, `%%…%%`, `${…}`, `[object Object]`, `undefined`, `NaN`, lorem ipsum and empty/Coming Soon shells; retain title/H1/meta/main placement and bounded snippets; ignore script, style, hidden and code-example content |
| B05 | Apply search-facing checks only where relevant | Intentional utility noindex and canonicalized-away variants receive no independent search-metadata repair; sitemap/search-intent conflicts produce one index-or-drop decision; accessibility evidence is not blanket-suppressed |
| B06 | Status-check unsampled same-site link targets within a declared bound | Test a broken linked target beyond the assessed-page sample, retained source links and source page; no claim to have checked all links when the shared pool is exhausted |
| B07 | Active soft-404 detection | Deterministic non-existent path probes at root and up to three per observed path family establish a baseline; compare complete accepted responses and intent, retain provenance, and reject access challenges as error-page baselines |
| B08 | Validate redirect destination meaning | Retain the existing observed hop/status/canonical/noindex evidence; distinguish a verified wrong/catch-all destination from a legitimate move to a homepage or hub |
| B09 | Audit robots-declared sitemap integrity | Report declared source/root/child retrieval failures and sampled or probed target status/noindex/redirect/app-shell conflicts; missing relevant content is qualified by actual discovery evidence; failed or challenged sitemap checks remain unverified |
| B10 | Near-duplicate main-content clusters | Normalize accepted main text, create bounded shingle/signature similarity and clusters with representative evidence; do not use common navigation/template similarity as proof of duplicated substantive content |
| B11 | Money-page reachability | Calculate observed depth/inlinks/navigation presence for classified money pages; retain sample scope and distinguish an observed weak route from proof of sitewide orphaning |
| B12 | Raw/rendered hub link comparison | Compare retained link sets from paired successful raw/rendered evidence for up to five eligible hubs, bounded by the overall deadline and explicit rendering resource policy; disclose selected, completed, failed and unassessed hubs |
| B13 | Local entity completeness and shells | Extract applicable address, phone, geographic/store details, regular hours and contextual open/closed/Coming Soon signals; optional holiday hours, photos, sameAs or parent entities are not universal defects |
| B14 | Cross-page store/NAP consistency | Compare normalized, provenance-bearing entity observations from location pages, store finder/forms, sitemap references and supplied structured data; ambiguous shared numbers or entity matches remain unverified |
| B15 | Contextual freshness | Require current-content intent plus contradictory temporal evidence; an archived article or historical year alone does not yield a stale-content defect |
| B16 | URL variant probes | Bounded case/slash/scheme/apex-www/meaningful-parameter checks under verified scope and security rules; synthetic probes remain labelled and cannot become claims about a published redirect |
| B17 | Distinct page-weight evidence and optional CrUX | Retain transfer bytes only when actually measured, decoded bytes separately, and inline script/style sizes; distinguish unknown wire length from zero; optional field performance is labelled by provider, scope and time, never inferred from HTML size |
| B18 | Optional connected GSC weighting/index evidence | Use owner-authorized current GSC page metrics and index evidence when connected; disconnected, stale or unavailable data stays explicit and does not block an otherwise valid scan or fabricate traffic/indexing status |
| B19 | Impact × reach × page value × confidence priority | Version the four factors, persist explanations and test cross-rule ordering. Base impacts: access/correctness 5, uniqueness 4, discovery 3, description/weight/freshness 2, alt/title length/social 1, decorative 0. Base page values: money 1, hub 0.8, blog 0.5, utility 0.1. Confidence: verified 1, heuristic 0.7, unverified 0.4. Reach uses a matching observed/indexable family denominator with a truthful unknown state; GSC affects value only with valid connected evidence |
| B20 | Root-cause grouping across families and SEO/GEO | Produce one repair for the same evidenced cause, keep family partitions and contributing observations; merge affected URL sets instead of adding overlapping group totals; suppressions retain reason and provenance |
| B21 | Honest counts and ranking before truncation | Distinguish unique affected pages, observation count, known population and displayed samples; disclose truncation. Rank eligible candidates before presentation limits so the legacy 36-item cap cannot discard a higher-impact candidate first |
| B22 | Evidence-led preview | Prefer individually verified impact-4/5 findings, otherwise the best verified finding; a good-shape message is permitted only with the stated coverage qualification; preserve existing entitlements and no-leak rules |
| B23 | Health scoring with explicit root-cause caps | Score each confirmed root cause within documented caps, preventing cross-rule/SEO-GEO duplication; preserve existing access/sample/incomplete ceilings and expose unknown coverage rather than inventing observed failures |
| B24 | Handoff v2 | Export root-cause/family identities, published/request/final URL provenance, user agent, indexable/affected/observation counts, four priority factors, evidence references, verification steps, dependency and vendor/owner information. Include suppressed findings/reasons only in an authorized operator/debug handoff, never customer output. Retain historical v1 export/read behavior |
| B25 | Exact blueprint corpus and 30-site regression gate | Provide labelled deterministic scenarios for Pretto, Center Street, both Ike's hosts and getfixlist, plus Ironwood access-limited negative cases. Create `scripts/assertCorpusRun.mjs` for the blueprint must/must-not assertions and wire it into CI; the named runner is absent at the starting commit. Establish a provenance-labelled 30-site baseline/candidate comparison and investigate every new artifact. Real-site conditions require separate dated runtime observations |
| B26 | Own-site blueprint findings | Reproduce getfixlist metadata/sitemap/soft-404 claims against the intended release, fix demonstrated serving defects, and verify the deployed source. Do not change pricing or claim a current defect solely from the PDF |
| B27 | Existing GEO and historical compatibility | Keep GEO coverage/null semantics and accepted-HTML gate; old HMAC fixtures verify unchanged, new-field tampering is rejected, and saved/reloaded/history/export/preview paths agree |
| B28 | Actual deployment | Exact merged-SHA CI, named schema parity, Base44 site and six V6 runtime identities, staged worker identity, guarded promotion/rollback readiness and fresh authorized scan acceptance all match the released source |

## Evidence and revision boundary

Page identity is an observation identity, not a URL prettification function. Family classification remains a separate function. New report production must retain path case, slash and reserved-escape distinctions throughout counting and grouping. Coalescing final pages requires actual observed redirect/alias evidence; a blanket lowercase rule cannot establish equivalence.

Introduce `evidence_url_identity_v2_published_route` at the producer boundary, with coverage version `repair_coverage_v5_published_route_identity` and invariant version `repair_invariant_v2_published_route_identity`. Python and JavaScript consume shared literal fixtures for this revision. Existing historical normalizers remain available only for legacy reconstruction and read compatibility; missing revision means legacy, not permission to recalculate historical output using new rules.

Use the internal seal `standard_review_snapshot_hmac_identity_v1` and retain public V6 routes. The seal version selects reconstruction semantics; an unverified marker injected into a row cannot select them. The signed repair evidence requires `evidence_url_identity_version` for the new seal and rejects unknown versions. Preserve all legacy branches, including `standard_review_snapshot_hmac_geo_v1`, without adding fields to their reconstructed bytes. New-version reader, Grok and preview capability checks must retain GEO rather than accidentally dropping it through equality checks against the older GEO seal.

The writer's aggregate/singleton suppression is also versioned: covering `/x` cannot suppress `/x/`. Priority joins and cross-run verification use observed identity, not family paths. Cross-version ambiguous comparisons cannot produce `verified_fixed`. Keeping the signed marker inside existing repair evidence avoids an unnecessary top-level entity migration.

## Detection and probe policy

New observations share a small typed envelope: rule/version, state (`pass`, `fail`, `not_applicable`, `not_verified`), applicability reason, observed URL identity, source/provenance, evidence reference, bounded excerpt and verification confidence. A detector cannot promote an unknown or access-challenged response into a confirmed site defect.

Reuse safe accepted-response extraction for main content, local details, dates, raw links, byte measurements and image applicability. Deterministic analyzers operate on those retained fields, not a second hidden fetch or LLM assertion. Rendering stays paired and labelled; a failed render does not prove missing links.

A shared scheduler avoids separate unlimited pools for link checks, soft-404s, sitemap targets and URL variants. It deduplicates actual request identities, reuses accepted observations, charges redirect hops/retries, observes the existing finite frontier claim ceiling and deadline, and exposes per-purpose coverage. It prioritizes published broken-link candidates and sitemap conflicts, then representative synthetic probes. Lower-priority checks may be unverified but may not silently disappear from coverage.

No credentials, scopes or provider access are granted as an implementation side effect. GSC and CrUX adapters accept authorized configuration and report unavailable states when absent. Enabling a new external account connection remains an owner action.

## Ranking, scope and customer output

Compute applicability and four-factor priority before the presentation cap. Count affected pages with the new observation identity, while reporting observed family denominators separately from inferred site populations. Do not turn missing reach into zero affected pages or assume the sample is the entire site.

Apply the blueprint's rule-specific impact distinctions: H1/description/canonical gaps start at 2, canonical gaps with observed live duplicate routes rise to 3, sitemap/noindex conflicts start at 3 and verified noindex on money pages rises to 5. Verified broken access and incorrect/unresolved visible content use 5. Optional schema/holiday-hours absence is not automatically a defect despite the source PDF's broader examples.

Root causes are explicit stable identifiers derived from actual rule/evidence relationships. Grouping cannot collapse unrelated defects solely because they share an impact class or generic text. One shared SEO/GEO repair retains both sets of evidence without duplicate penalties.

Keep the existing full-access/free-preview policy. Only authenticated allowed fields reach customer output. Handoff v2 is derived from the verified canonical report; it is not an alternative route to hidden fixes. Suppressed artifacts and their reasons belong to operator-authorized diagnostics, not customer downloads. Unavailable historical fields remain unavailable rather than being reconstructed from current websites.

## Verification and release

Each implementation task starts with a failing behavioral regression at the real seam, then a minimal coherent change, focused tests, diff review and proportionate integration checks. Existing passing suites are a baseline, not proof of new blueprint behavior.

The acceptance record maps every B01–B28 item to fresh test/runtime evidence and marks it confirmed, partial, unverified or failed. Optional providers require both disconnected behavior tests and controlled connected-response tests; account-specific live connection is claimed only if actually verified.

Before release, run the exact five-site corpus (both Ike's hosts counted separately) and Ironwood negatives through `assertCorpusRun.mjs`, the 30-site corpus no-new-artifact gate, full Python and frontend suites, lint/type/build, generated-release-contract and Base44 package checks, historical HMAC/tamper/privacy/admission/security regressions and the repository release gates. Diagnose environmental failures without masking them or weakening production invariants.

The 30-site gate requires an explicit site manifest, scan-policy/source identifiers, dated baseline and candidate outputs, and per-difference adjudication. An aggregate historical audit count is not a substitute for those inputs. Label synthetic versus captured responses and never manufacture a passing live baseline from the PDF's reported numbers.

Deploy only through the repository's guarded exact-main workflow: update only reviewed named schema differences, activate and verify the six V6 functions before the site, publish the exact-source site, restore and verify the expected function inventory, verify the public source, then promote the same staged worker with a known rollback target. Do not equate a CLI success message, editor preview or green staging job with production activation.

Retain the Base44 GitHub connection and existing user work. If synchronization or owner authentication remains unavailable, continue safe local implementation and verification, but report deployment as blocked rather than publishing an unverified snapshot.

## Completion rule

The full goal is complete only when all applicable blueprint requirements have direct fresh evidence and the matching release is live. No deferred row in the earlier GEO checklist is silently dropped. Any owner-dependent external acceptance that remains unavailable is disclosed and keeps the affected requirement unverified.
