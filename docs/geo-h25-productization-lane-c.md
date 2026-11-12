# H2-5 GEO readiness productization — Lane C checkpoint

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Starting main: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`

## Boundaries

This lane owns deterministic GEO evidence/applicability helpers, tests and handoff documentation only. It does not change Standard 150 crawl/robots/SSRF budgets, admission, deployment, release, authority persistence/customer projection, repair priority, or production. It makes no LLM/model/provider calls. `authority_verified` remains false in the evaluator result until an integrator explicitly seals and verifies a compatible authority snapshot end-to-end.

FixList GEO readiness is a structural diagnostic. It does **not** measure or predict citations, inclusion, appearance, ranking, visibility, or traffic in ChatGPT, Perplexity, AI Overviews, Gemini, Claude, or another AI/search provider.

## Production evidence refresh status

The repository and GitHub issue/search surfaces were refreshed first. Current `main` is `c1080d75...` and the repository release metadata still names `geo_evidence_v1` / `geo_readiness_v1_experimental`. The production scan payload for Funbooker scan `6ab314008da962a9f8c58929` is not stored in the repository or searchable issue surface, and this lane has no production datastore/log connector. Therefore the reported production baseline cannot be independently re-read in this run.

The externally supplied baseline remains a comparison point only: 139 Funbooker pages, `assessment_status=insufficient_evidence`, overall coverage about 45.68%, access about 82.97% / score 100, clarity about 99.76% / score 100, entity 0%, support 0%, numeric score correctly withheld. No threshold is changed to make that scan score.

## Reproduction: why six semantic/support cells stayed unknown

The current-main adapter can deterministically reproduce the failure mode with a marketplace page using Product JSON-LD rather than microdata/native article markup:

- `subject_identity`: current v1 recognizes main `aria-labelledby` or schema.org microdata name matching H1. A Product JSON-LD object does not satisfy that path.
- `entity_details`: current v1 recognizes a visible `<address>` or microdata `itemprop=address`; JSON-LD PostalAddress is not considered.
- `schema_agreement`: current v1 only inspects top-level JSON-LD objects whose `url` exactly equals the page URL. `@graph`, `@id`, fragment IDs and `mainEntityOfPage` are ignored.
- `accountability`, `date_context`, `source_attribution`: current v1 only recognizes explicit `<article>` markup with rel=author, labelled `<time>`, and blockquote/source-link evidence. Non-article commercial pages therefore remain unknown forever even when their structured type deterministically proves that article-only checks do not apply.

A Funbooker-like synthetic Product page matching those characteristics reproduces all six as unverified under the old rules. The new regression locks the intended transition without asserting anything about the actual production HTML beyond the reported result.

## Evidence/applicability changes in this checkpoint

### Deterministic non-article applicability

Article-only support checks become `not_applicable` only when accepted raw HTML contains an explicit, bounded structured subject whose type is one of Product, Offer, Event, LocalBusiness, Organization, Place, Service, ItemList, or CollectionPage, whose name exactly matches the H1, and no article element/Article-family structured entity is present. A single exact structured subject may establish subject applicability; arbitrary nested objects are not recursively traversed. Unknown remains the default otherwise.

This is intentionally conservative. A plain page with no `<article>` remains unknown because absence of an article element is not enough to prove non-article applicability.

### Bounded JSON-LD positive evidence

The adapter now reads at most 25 JSON-LD scripts, 100 kB each, and at most 50 top-level / one-level `@graph` objects total. No arbitrary recursive graph walk is allowed.

Positive structural evidence can come from:

- exact H1/name agreement on an explicit structured subject;
- page binding via `url`, `@id`, or `mainEntityOfPage`, including fragment IDs that resolve to the same page;
- structured PostalAddress fields for an exact trusted subject;
- Article-family author objects with a nonempty name plus public HTTP(S) `url`/`@id`;
- valid ISO `datePublished` / `dateModified`;
- public HTTP(S) `citation` identities.

These signals establish only retained structure. They do not certify factual accuracy, source quality, freshness, provider ingestion, or AI visibility.

### Compatibility

`geo_readiness.py` arithmetic, thresholds, dimensions and authority gate are unchanged. `geo_evidence_v1` remains the transported adapter version on this isolated lane to avoid touching shared seal/projection contracts before compatibility review. Because the semantics expand, the integrator must decide whether the eventual sealed candidate needs a version bump (`geo_readiness_v2` / evidence adapter companion) before production transport. This checkpoint must not be deployed as an unversioned authority change.

## Coverage implications

For a marketplace Product page with exact structured name/page identity but no contact address, the entity dimension can move from 0/3 verified checks to 2/3 verified checks (`subject_identity`, `schema_agreement`), while `entity_details` remains unknown. The three article-only support checks become N/A rather than unknown when non-article applicability is proven.

Under the existing v1 evaluator, an all-N/A support dimension still has zero verified mass and therefore still blocks a numeric score. This is deliberate: this checkpoint improves truthfulness of applicability and entity coverage but does not weaken the 80% overall / 50% per-dimension scoring gates. A future v2 candidate may only change dimension semantics after explicit compatibility fixtures and product approval.

## Claim-boundary lint

`scanner-api/app/geo_claim_boundary.py` adds a pure text guard that rejects customer copy which combines named AI providers with positive ranking/appearance/citation/visibility/traffic/inclusion claims unless the sentence is explicitly negated/disclaimed. Tests include prohibited examples and the existing readiness disclaimer pattern. The regression scans the dedicated GEO presentation files when run in the full repository; it deliberately excludes unrelated UI copy such as the feature for downloading a FixList to ChatGPT/Claude.

## Verification

Hermetic focused + arithmetic compatibility run in this checkpoint:

- `scanner-api/tests/test_geo_h25_productization.py`: 12 tests
- current-main `scanner-api/tests/test_geo_readiness.py` contract replicated for local compatibility: 20 tests
- total executed locally: **32 passed**
- `py_compile`: `geo_evidence.py`, `geo_claim_boundary.py`, `geo_readiness.py` passed

The local harness uses a minimal page-evidence stub because this automation environment cannot clone/materialize the complete GitHub repository directly. Therefore this is not a claim that the full scanner suite is green. Exact-branch CI / full-repo relevant tests remain required after push.

## Next ordered work

1. Refresh exact branch CI and any review findings for this checkpoint.
2. Add per-bot robots evidence only for named crawlers whose directives are already truthfully observable, without UA impersonation or new requests.
3. Add bounded `llms.txt` presence/validity structural evidence only if existing retained/fetched evidence exposes it without changing crawl budgets; otherwise prepare an integrator-owned observation seam rather than adding a request here.
4. Run compatibility fixtures before defining `geo_readiness_v2` observation scope/dimension semantics.
5. Prepare authority-sealing/V8 transport handoff; keep `authority_verified=false` until sealed inclusion and end-to-end verification are proven.
