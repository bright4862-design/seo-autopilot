# GEO readiness within Standard 150

Status: product direction approved; experimental evaluator, accepted-HTML adapter, sealed runtime integration and customer presentation implemented and independently reviewed. Scanner blueprint corrections and full release gates remain in progress; no production deployment is claimed. See ../../geo-release-acceptance.md for verification and ../../geo-architecture-research.md for research and measurement limits.

## Approved outcome

Add a separate GEO readiness score from 0 to 100, evidence coverage, and actionable findings. Actual AI answer citations and brand visibility monitoring are deferred. This is a FixList diagnostic model, not a ranking formula endorsed by a search or AI provider, nor a prediction of citations.

Preserve the Standard 150 page cap, V6 routes, owner robots rules, SSRF enforcement, authority integrity, admission lifecycle and deployment gates. GEO does not add network requests in its first release. It consumes accepted evidence from the same crawl. No UA impersonation or challenge bypass.

## Evidence and dependencies

The supplied Scanner Gap Analysis & Blueprint is a source of test hypotheses, not independently verified live truth. Local inspection confirmed non-seed URLs use normalize_url(), which strips trailing slashes, and extract.py combines missing and empty alt attributes. Reconcile with the scanner agent's latest branch before implementation; do not duplicate its corrections.

Customer release depends on verified published-request URL handling, challenge exclusion, observed indexability, consistent evidence counts and authority-preserving projection. GEO rule development and fixture tests can proceed independently of those integrations.

Ironwood's reported diagnostic returned six SiteGround challenges for both UAs. It establishes neither production IP equivalence nor AI-provider access. Challenged responses are never content evidence. Ironwood receives score=null with reason=access_limited, not zero or 100.

## Architecture

Existing crawler and evidence gate -> typed GEO evidence adapter -> deterministic GEO evaluator -> existing authority persistence -> customer projection and report.

The evaluator is a pure Python module proposed at scanner-api/app/geo_readiness.py. It accepts evidence records, declared scope and versioned applicability rules. It performs no fetching, model calls, persistence, admission operations or mutation of SEO results.

The adapter distinguishes absent extractor capabilities from observed absence in complete accepted HTML. Incomplete HTML, failed rendering and missing retained fields yield not_verified, not fail. Raw and rendered observations retain separate provenance; disagreements are not silently resolved by taking whichever passes.

Use the existing extract.py/review.py integration points after inspecting their current interfaces. Integrate the optional result through the V6 authority snapshot and customer projection. Existing projection allowlists and historical HMAC reconstruction require explicit compatibility work; adding an unsealed JSON field is not sufficient.

Do not modify historical snapshots or recompute old scores on read. Old scans display GEO not assessed. New snapshots include the GEO payload, its ruleset version and evidence references in the authenticated payload under an explicit compatible snapshot revision. An internal snapshot revision does not require V7 function routes. Update all active producers, verifiers and readers through the repository's existing propagation process.

## Assessment model

Every page/check observation has one state: pass, fail, not_applicable, not_verified. Applicability requires an explicit rule and reason. Uncertain page classification means not_verified. Presence of a signal is not proof that its substantive claims are true.

Initial dimensions have equal weight, 25 each. These are transparent product weights, subject to fixture calibration before release, not empirically established AI-ranking weights.

| Dimension | Initial checks | Interpretation |
| --- | --- | --- |
| Access and discovery | Search robots policy; observed indexability/snippet controls; discovery within the sampled link graph | Policy eligibility and local observations, not proof a provider fetched or indexed a page |
| Content clarity | Extractable main text; descriptive page identification/headings; unresolved visible template tokens | No blanket word-count, FAQ, or list-format requirements |
| Entity consistency | Identifiable subject/business; applicable visible entity details; agreement with structured data when supplied | No mandatory schema type; missing structured data alone is not a failure |
| Supporting evidence | Applicable authorship/accountability; useful date context; identifiable supporting sources where claims require attribution | No requirement that every commercial page have citations, an author, or a recent year |

Each check has equal weight within its dimension. For each check, assess only sampled pages that fall in the declared search-facing scope. Divide passed and verified counts by applicable-plus-unknown pages, excluding all-N/A checks. Average those fractions across eligible checks per dimension, then across four equally weighted dimensions to obtain P and V. Coverage is V and the assessed-evidence score is round_half_up(100 * P / V). Missing dimensions prevent scoring. The unresolved-outcome range is [100P, 100(P + 1 - V)], not a statistical confidence interval. Exact rational arithmetic controls gates; rounding is for display only. Numeric fixtures lock this contract; interpretation and weights remain subject to calibration before runtime integration.

Coverage is a separate weighted ratio: verified applicable observations / all applicable or unresolved observations. not_applicable observations are excluded from both, with their reason retained. not_verified observations never earn points. Report page coverage and per-dimension check coverage as separate measures; neither claims complete coverage of an entire site.

Proposed display gates: authoritative parent scan; accepted entry page; at least 80% weighted check coverage overall; at least 50% coverage in every dimension; and at least one verified applicable check in each dimension. These thresholds are initial product safeguards requiring fixture validation. They are not provider requirements. Below a gate, score=null and show insufficient_evidence with the unmet checks. All-not-applicable yields no score.

Display assessed-sample score only after the gates pass, alongside coverage, assessed page count, timestamp and methodology version. Unknown evidence can change a later score in either direction; never describe missing observations as clean. No score cap or penalty may disguise missing evidence as an observed defect.

Indexability is evaluated as a decision, not blanket failure: intentional utility/auth noindex pages are excluded from search-facing content checks. Sitemap inclusion or stated search intent can support an actionable conflict. Canonicalized-away pages are tracked as variants and not counted as independent content copies without evidence. Policy choice to prohibit AI training is not a GEO defect.

Robots interpretation distinguishes OAI-SearchBot search access from GPTBot training access and Google Search controls from other AI uses. Read those policies as data; never send requests pretending to be those agents. Owner permission for FixList to ignore robots does not imply permission for any external crawler.

## Result contract

Proposed fields:

- geo_readiness_version and evidence_adapter_version.
- assessment_status: assessed, insufficient_evidence, access_limited, not_assessed, evaluation_error.
- score: integer 0..100 or null; null mandatory unless assessed.
- coverage: weighted overall and dimension coverage, assessed pages, scope and reasons for exclusions.
- dimensions: stable IDs, measured scores or null, check results and denominators.
- findings: stable rule ID, root-cause ID, unique affected-page count, bounded evidence samples, sample_truncated, suggested action and verification step.
- provenance: scan ID, source release, observation time, evidence references and raw/rendered origin. Reuse existing safe URL/evidence sanitization.

All result arrays remain bounded by assessed pages and a fixed rule registry. Store evidence references rather than duplicate HTML. All arithmetic is server-derived and validated before sealing. LLM prose, if later introduced, must not create evidence or determine the numeric score.

## Findings and UI

Show SEO health and GEO readiness separately. Use the actual Standard 150 report in src/pages/FixList.jsx. Reports.jsx is a separate Search Console/backlink connector screen and remains outside this work. Missing historical fields display a neutral not-assessed state; never coerce null to zero.

One root cause can affect SEO and GEO. Merge its action into one FixList item with both labels, retaining separate assessment evidence. Do not add a second repair or duplicate SEO penalties. Prioritise verified customer consequence; lack of schema, citation count or decorative alt text cannot automatically outrank broken critical pages.

Keep existing full-access/free-preview policy unchanged. Customer projections expose only the score summary and findings allowed by that policy. Full evidence and hidden fixes must not leak through a GEO field.

GEO evaluation failure does not fabricate a score. Preserve the valid SEO result only if its own authority checks pass and a valid, explicit evaluation_error GEO state can be sealed. Malformed GEO payloads must be rejected by validation, not silently accepted.

## Delivery sequence

1. Freeze rules, applicability, exact arithmetic, sample semantics and numeric fixture expectations in the implementation contract.
2. Build the pure evaluator and evidence adapter behind a disabled customer-display flag; no production writes in development tests.
3. Integrate accepted extraction evidence after the scanner corrections pass. Compare outputs against labelled fixture expectations.
4. Add authenticated snapshot versioning and compatible projections; test old and new scans, history, reload and preview permissions.
5. Add score/coverage/finding presentation and complete end-to-end acceptance.
6. Review, exact-SHA CI, staged release and existing controlled production acceptance. No release based on a promising score alone.

## Required regression evidence

- Published /x/ returning 200 causes no synthetic redirect finding; actual published /x redirect remains observed evidence.
- SiteGround 202, Cloudflare challenges, rate limits and denied fetches produce no GEO score or real-site noindex finding.
- Same accepted evidence and ruleset produce identical score and ordering.
- Missing fields, all-unknown input, all-not-applicable input, threshold boundaries and partial rendering behave as specified.
- Intentionally noindexed utility pages are not rewarded or punished as target search content.
- Blocking GPTBot while allowing OAI-SearchBot creates no training-related deduction.
- Absent schema is not an automatic failure; contradictory supplied schema can yield a cited finding.
- Historical content with an old date is not automatically stale; commercial pages are not universally required to name an author.
- Visible template placeholders are detected without treating script templates or code examples as defects.
- Root-cause grouping does not duplicate fixes; affected counts use distinct evidence-backed pages and disclose truncated samples.
- Old authority seals verify unchanged; new GEO score/evidence tampering fails verification.
- GEO evaluator errors preserve independently valid SEO behavior only through a validated error payload.
- Full-access, preview, exports, reload and historical results respect authority and entitlement gates.
- No new network calls and no change to the Standard 150 cap, robots override eligibility or SSRF protections.

Use Pretto, Center Street, both Ike's hosts and getfixlist.com as reported regression scenarios, plus Ironwood as the access-limited negative case. Capture reproducible fixtures and verify their labels; do not turn unverified report counts into mandatory live expectations.

## Sources and exclusions

- User-supplied FixList Scanner Gap Analysis & Blueprint, 18 September 2026.
- Google AI features guidance: https://developers.google.com/search/docs/appearance/ai-features . No special AI markup/files required; inclusion is not guaranteed.
- OpenAI crawler documentation: https://developers.openai.com/api/docs/bots . Search and training crawler purposes are distinct.

Excluded: actual AI citation tracking, browser/Googlebot impersonation, residential proxies, CAPTCHA handling, expanded crawl scope, unlimited link checks, pricing changes and unrelated frontend redesign.
