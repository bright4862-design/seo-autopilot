# Task 1: GEO evidence adapter

Implementation: `scanner-api/app/geo_evidence.py`; additive hook in `extract.py` after `usable_html` gate; additive actual OAI-SearchBot policy field in `robots_policy.py`. No fetching, evaluator arithmetic changes, SEO findings, ownership overrides or rendering calls.

## Exact result contract

`extract_geo_evidence(html: str, page: dict) -> dict`:

- `version`: `geo_evidence_v1`
- `origin`: `raw_html` (rendered evidence is not claimed or merged)
- `accepted`: boolean
- `content_digest`: lowercase SHA256 (64 characters) of accepted HTML; empty when rejected
- `signals`: empty when rejected; when accepted exactly nine keys: `main_text`, `page_identity`, `template_integrity`, `subject_identity`, `entity_details`, `schema_agreement`, `accountability`, `date_context`, `source_attribution`. Values boolean, except template_integrity may be null where no main landmark exists, and schema_agreement is null when complete accepted HTML contains no supplied JSON-LD/microdata/RDFa markers (explicit not_applicable at assessment). A false structural capability is not generally a failed GEO check: absent semantic/applicability support remains unknown.

`extract_page` attaches this object as `page.geo_evidence` only after shared gate acceptance. Later uncertainty invalidates it at assessment. `annotate_robots_evidence` adds `robots_txt_oai_searchbot_allowed`: boolean or null, using existing parsed robots policy without ownership override.

`assess_geo_pages(pages, *, parent_authoritative=False, entry_verified=False, access_limited=False) -> dict` preserves every current `evaluate_geo` output field and value contract:

- `geo_readiness_version`: `geo_readiness_v1_experimental`
- `assessment_status`: assessed / insufficient_evidence / access_limited
- `score`: integer or null (only assessed is numeric)
- `coverage`: 0..1 number
- `score_bounds`: `{lower, upper}` numbers or null
- `bounds_kind`: `unknown_outcome_range_not_statistical_confidence`
- `sample_pages`: integer 0..150
- `dimensions`: mapping of access, clarity, entity, support (empty access_limited); each `{coverage, score, checks}`; each check `{counts: {pass, fail, not_applicable, not_verified}, applicable_or_unknown}`
- `reasons`: evaluator gate reason strings
- `authority_verified`: false (only authority integration may determine authority)

Adds:

- `evidence_adapter_version`: `geo_evidence_v1`
- `observations`: at most 1800 records, sorted by page ID then fixed CHECKS registry order. Each exactly `{page_id, check_id, state, evidence_ref, reason}`. Unknown/N/A refs empty. Verified reference format `geo_evidence_v1:raw_html:p_<24 hex>:<check_id>:<24 hex of HTML digest>`. Page ID hashes bounded page_id input, otherwise original requested URL; no URL/query content is exposed by identifiers.
- `findings`: at most three grouped check failures, sorted by check ID. Each `{rule_id, root_cause_id, check_id, label, affected_page_count, page_ids, evidence_samples, sample_truncated, suggested_action, verification_step}`. Rule/root IDs both `geo_<check_id>`. Unique page IDs bounded to 150. Samples bounded to 5. Samples have the five observation fields plus `page_url`, sanitized HTTP(S) final/requested URL without credentials/query/fragment, or empty if invalid/over 2048 characters. No raw HTML or arbitrary page strings are included.

Current failed checks can only be `search_policy`, `indexability` (explicit noindex conflicting with sitemap/declared intent), and `template_integrity`. These are diagnostics only; they do not add SEO repair records or penalties. Integration must decide root-cause merging with SEO, since existing SEO root IDs are not part of this adapter's input.

Malformed retained GEO schema, non-boolean policy, malformed retained directives/discovery, duplicate IDs, or >150 pages raise ValueError. Missing retained evidence yields unknown, not an exception or clean pass. All access_limited observations become unknown, findings empty and score null. Caller catches genuine evaluation failures at the validated authority boundary.

## Applicability and limits

- Unknown is mandatory for missing fields and unsupported meaning. No universal author/date/schema/citation requirements and no age penalty.
- Main text requires an explicit main/role=main/article landmark; title/primary-heading check requires both nonempty. No word-count threshold.
- Template check observes narrow `{{token}}`, `[[token]]`, and `#location#`/city/state/country/business_name syntax, excluding script/style/template/noscript/code/pre, explicit hidden/aria-hidden and inline display:none/visibility:hidden elements. External CSS/computed visibility and human intent are not established; finding action asks review of unintended placeholders.
- Subject name is narrowly verified from an explicit main aria-labelledby reference to the main H1, or supported schema.org microdata entity name matching main H1. Native address or structured address verifies only semantic contact address presence, not accuracy/completeness.
- Structured agreement verifies only a JSON-LD object's exact page URL and name/H1 equality; does not certify other schema properties. Absent supplied JSON-LD/microdata/RDFa is explicitly N/A; supplied but mismatched/unparseable schema stays unknown. Mere absence of schema never prevents numeric eligibility: a separate schema-free fixture verifies all gates.
- An explicit article can verify author link presence, valid ISO machine-readable date with datePublished/dateModified or explicit publication/update aria-label, or quotation with matching source link. This does not certify authorship, freshness, source credibility, or coverage of all claims. Historical dates pass.
- Ordinary missing applicability remains unknown. The complete labelled fixture proves the score gates can be met, but many normal commercial sites will correctly have null scores. No recommendation to add Organization/address/article markup simply to unlock scoring. Coverage/rules require release calibration across real fixture archetypes before customer display.
- Explicit `geo_scope=intentional_utility` plus nonempty `geo_scope_reason` and observed noindex permits N/A exclusion, unless sitemap/explicit search intent contradicts it. Path classifier alone cannot exclude a page. Noindex with unresolved intent and canonical variants have unknown content checks.
- Raw/rendered comparison is unsupported; client-rendering suspicion or retained render error invalidates content evidence. No mixing origins.
- OAI-SearchBot uses existing robotparser interpretation (inherited parser limitations); GPTBot training opt-out ignored. Policy observation does not establish provider access.

## Bounds/performance

Maximum 150 pages, 12 fixed checks/page, 3 finding groups, 5 samples/group. Adapter declines HTML over 2,000,000 characters rather than truncate and infer absence. JSON-LD parsing limited to 25 scripts of 100,000 characters, and first 25 top-level entries, no recursive graph traversal. Dates/quotes limited to 25 each. Evidence references and reasons bounded, HTML retained only as digest/booleans. Independent BeautifulSoup parsing deliberately avoids mutation of existing SEO soup; this is added CPU for accepted <=2M-character pages, no network overhead. No measured live latency claims.

## Verification

Focused adapter + arithmetic suite: **41 passed** (2026-09-18). Includes challenge/202/truncation/render uncertainty; missing evidence/null; malformed/duplicate/over-cap; immutability/order; training opt-out/owner override; code/script/hidden token examples; utility scope; canonical variant; historical date and narrow complete numeric fixture; grouped samples/access-limited suppression; bounded HTML; sanitized URL/digest refs.

Full scanner suite: **1552 passed, 18 skipped, 642 warnings in 34.00s**. Warnings are existing BeautifulSoup/lxml strip_cdata deprecations; skipped tests remain skipped. First run lost its tool session to a network-approval cancellation, so a complete rerun was used. Final focused tests rerun after strict date/null validation refinements. `git diff --check` clean.

## Review correction round 1

Implementation commit: `18fc95d7b2ac3649cf9f70701eec6815e5165360` (base `f199f2b1`). Fixed both Important findings and the policy validation discrepancy, with no unrelated changes.

- Inline-style hidden nodes are removed from descendants to ancestors, avoiding access to already decomposed child attributes. Public `extract_page` nested parent/child regression passes and keeps accepted SEO and GEO evidence.
- Optional GEO extraction exceptions are isolated at the additive `extract_page` boundary. The existing rejected retained schema is emitted (`accepted=false`, empty signals/digest), plus page-level `geo_evidence_error="extraction_error"`. Existing SEO fields/gate remain usable. Assessment returns all unknown observations with reason `GEO extraction failed; content not verified`, no findings and null score for the isolated failed-page fixture. Exception text is not retained. This adds no field to the exact assessed result contract or retained GEO object schema.
- Article author relations require an exact whitespace-delimited `author` token (case-insensitive). Multi-token `nofollow author external` verifies; `notauthor` and `authorish external` do not.
- Retained OAI policy type validation runs before applicability/acceptance branching, consistently rejecting malformed values on accepted, truncated, intentional-utility-excluded and access-limited inputs.

Regression-first run: 7 expected failing cases reproduced before changes, 24 passed. After correction:

`/workspace/scratch/9bc979dba4d1/fixlist-test-venv/bin/python -m pytest scanner-api/tests/test_geo_evidence.py scanner-api/tests/test_geo_readiness.py scanner-api/tests/test_page_evidence_gate_v1.py -q`

**58 passed, 89 existing BeautifulSoup/lxml warnings, 0.20s.** `git diff --check` clean. Full suite was not repeated for this narrowly scoped review round; prior full-suite result remains above and coordinator owns release exact-SHA gates.
