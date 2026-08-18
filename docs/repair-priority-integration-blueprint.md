# FixList Repair Priority Integration Blueprint

Status: integration-prep only
Branch: `agent/repair-priority-integration-prep`
Crawler architecture: frozen
Production/release state: untouched

## Product objective

Turn scanner findings into a small, trustworthy queue of customer repair actions without hiding evidence, overstating common root cause, or changing the Standard 150 crawler.

Customer model:

`scanner evidence -> pattern/context -> repair action -> supporting finding -> URL evidence`

For larger FixLists, a light work-area/family layer may sit above repair actions, but it must remain navigation only unless common implementation evidence is proven.

## Non-negotiable invariants

1. Do not change Standard 150 crawl topology, page caps, robots policy, SSRF protections, rate-limit cooperation, authority/HMAC, release gates, or persistence authority.
2. `priority` remains the historical technical severity contract during migration.
3. New `base_severity` describes inherent technical seriousness. New `action_priority` describes what the customer should do first on this site.
4. The backend owns canonical action priority. The frontend consumes that decision and must not rebuild a competing priority model from page count.
5. Historical scans remain readable through legacy fallbacks.
6. A page/template-family label is evidence of a pattern, not proof that one implementation change fixes every affected page.
7. Strong repair-leverage copy (`One shared change may improve ...`) requires explicit shared-repair evidence.
8. Coverage claims remain sample-qualified unless full eligible-site coverage is proven. Prefer `18 of 20 searchable product pages checked` over `18 of 20 product pages`.
9. A disappeared URL is not proof of a fix. `verified_fixed` requires re-observation of the relevant evidence population and absence of the same stable repair condition.
10. AI/on-page opportunities never outrank confirmed severe technical failures solely because they are broader or sound more strategic.

## Canonical repair contract v1

Each repair may add the following fields while preserving all scanner evidence:

- `base_severity`: `critical | high | medium | low`
- `evidence_class`: `confirmed_problem | improvement | opportunity`
- `action_priority`: `fix_first | important | improve | review`
- `action_priority_score`: internal ordering helper inside an action-priority band
- `priority_reason`: one plain-language reason that best explains the ordering
- `priority_context`:
  - `affected_checked`
  - `checked_eligible`
  - `checked_coverage`
  - `indexable_affected`
  - `non_indexable_affected`
  - `unknown_indexability_affected`
  - `indexable_checked_eligible`
  - `searchable_coverage`
  - `important_affected`
  - `shared_repair_confirmed`
- `repair_identity` / `repair_fingerprint`
- `repair_identity_state`: `stable | provisional | insufficient`
- `repair_identity_stable`: boolean
- optional explicit repair evidence:
  - `repair_surface`
  - `remediation_family`
  - `shared_repair_confirmed`

## Prioritization sequence

### Stage 1: establish inherent seriousness

Technical rule -> `base_severity`.

Do not allow affected-page volume to redefine a medium defect as a critical technical defect.

### Stage 2: establish evidence class

- deterministic scanner failure -> `confirmed_problem`
- evidence-backed optimization with weaker consequence -> `improvement`
- inferred/topic/keyword/pattern suggestion requiring judgment -> `opportunity`

### Stage 3: calculate site-specific context

Use evidence already collected by Standard 150:

- relevant checked eligible population when defensible
- indexable vs non-indexable affected pages for search-facing checks
- important-page distribution, not one representative-page proxy
- sample-qualified coverage
- evidence confidence
- explicit shared-repair evidence

Do not use the 150-page cap as the denominator unless the rule is genuinely eligible across every checked page.

### Stage 4: assign action band

- `fix_first`: severe confirmed failures that can materially block access/indexing/correctness or hit highly important pages
- `important`: meaningful confirmed repairs that deserve near-term action
- `improve`: lower-severity optimization work
- `review`: opportunities or judgments requiring human review

Use priority floors for severe conditions rather than one unconstrained multiplication formula.

### Stage 5: order within the band

Prefer contextual evidence over raw page count:

1. relevant/searchable coverage when known
2. important-page distribution
3. evidence confidence
4. confirmed repair leverage
5. stable fallback order

## Repair grouping model

Three distinct levels:

1. Evidence group: same technical condition.
2. Pattern group: same condition plus meaningful page/site pattern.
3. Repair action: evidence supports the same implementation change.

Merging policy:

- Merge only genuinely identical customer work.
- Bundle related repairs by work area when useful, without claiming they are the same problem.
- Preserve every underlying finding and URL.
- False merge is worse than an extra repair row.

Strong shared-fix language requires explicit evidence such as a confirmed repair surface/remediation family. `rule + page family + generic recommendation` is not enough.

## Customer copy

Global explanation:

> FixList puts the most important work first. It looks at how serious the problem is, which pages it affects, and how much one fix can improve.

Overview rows show only:

- verb-led repair title
- repair surface/page family when useful
- one scope statement
- one priority reason
- chevron

Examples:

- `Remove an indexing block` — `Homepage` — `Important page may be hidden from Google`
- `Fix product-page canonicals` — `Product pages` — `18 of 20 searchable product pages checked are affected`
- `Fix redirected navigation links` — `Navigation` — `49 pages share the same redirect pattern`
- `Clarify two similar pages` — `2 pages` — `Potential topic overlap · review recommended`

Do not expose formulas or numeric confidence to ordinary customers.

## Mobile information architecture

Default screen:

- `Your FixList`
- `N repairs · M pages checked`
- `Fix first`
- show first 3 rows, then `View X more Fix first repairs` if needed
- `Important`
- `Improve`
- `Review`
- secondary link: `Browse all checked pages ->`

Do not use repeated issue cards, repeated explanatory paragraphs, decorative charts, or repetitive severity badges on the main mobile queue.

Repair detail:

- What to change
- Where to change it
- Why it matters
- What success looks like
- Findings behind this repair
- Affected pages
- Technical evidence
- verification action/state

## Rescan verification contract

States:

- `verified_fixed`: stable repair identity; previously affected evidence was rechecked; condition no longer triggers
- `still_detected`: same stable repair remains
- `came_back`: previously verified repair is detected again
- `could_not_verify`: identity is unstable or required evidence/pages were not re-observed

A user action may mean `Ready to verify`; it must never directly create `Verified fixed`.

## Loading/progress contract

- Unknown denominator: indeterminate progress + truthful page count, e.g. `Finding and checking pages... 42 pages checked`
- Known stable target only: determinate `42 of 84 pages checked`
- synthesis phase: `Building your FixList...`
- do not display provisional repair counts while grouping can still change
- only say `You can leave this page` if durable background execution is proven for that customer path

## Competitor lessons to retain

- Sitebulb: issue importance is contextualized by affected URLs, eligible Coverage and indexability.
- Semrush: Top Issues combine priority and repetition; traffic context can help select important URLs.
- Ahrefs: severity and affected-URL views are distinct; issue importance can be customized.
- Screaming Frog: generic priority is estimated potential impact, not a definitive strategy.
- Conductor Monitoring: Website Health impact explicitly combines number of affected pages with page Importance.
- Lumar: weighted issue reports roll into traffic-funnel/category health; weights are adjustable.
- Botify ActionBoard: URL-level issue scoring is tied to estimated traffic impact and can combine crawl, search/log and analytics context.
- JetOctopus: its 2026 AI SEO Recommender separates breadth (`number of pages`) from impact (`impressions`) and keeps direct drill-down into affected evidence.
- Oncrawl: use-case lenses, business-critical page checks, crawl-over-crawl analysis and configurable alerts reinforce the value of contextual views rather than one universal severity list.

These are design references, not a requirement to add Search Console, log files, analytics, or a new crawler to Standard 150.

## Integration phases

### Phase A — passive contract annotation

Files prepared:

- `scanner-api/app/repair_priority.py`
- `scanner-api/app/repair_identity.py`
- `scanner-api/app/repair_integration.py`

Annotate fixes without changing current ordering, health score, authority payload eligibility, or persistence behavior. Produce a shadow order/divergence report for tests and evaluation.

Gate:

- existing scanner/review suites unchanged
- new repair tests green
- serialized authority contract reviewed for additive-field compatibility

### Phase B — canonical backend action priority

After shadow evaluation:

- backend emits `action_priority`, `priority_reason`, `priority_context`
- preserve existing `priority`
- compare old and proposed order on representative real scan fixtures
- validate no severe confirmed issue is demoted below an opportunity

Do not switch customer order yet if divergence is unexplained.

### Phase C — frontend consumption

- `src/lib/fixRanking.js` consumes canonical backend action priority
- `src/lib/repairPresentation.js` builds mobile sections and safe display copy
- legacy scans fall back to historical severity behavior
- remove raw-page-count re-ranking when canonical action priority is present

### Phase D — compact FixList UI

Migrate `src/pages/FixList.jsx` to compact rows and action-priority sections. Keep detail/evidence expansion intact. Do not alter durable scan loading or authority checks.

### Phase E — repair lifecycle/rescan

Wire stable repair fingerprints only after persistence lineage is verified. Never infer `fixed` from absence alone.

### Phase F — optional future enrichment

Only after Standard 150 is stable and product demand justifies it, external Search Console/analytics/log signals may become optional page-value enrichments. They are not part of this integration and must not be required for valid prioritization.

## Tomorrow's integration order

1. Rebase/compare branch against current `main`; stop if scanner/review contracts moved materially.
2. Run focused Python repair tests and frontend presentation tests.
3. Run full Python scanner suite and frontend contract suite before wiring.
4. Wire passive backend annotation only; verify serialized output and authority compatibility.
5. Evaluate order divergence on known scan fixtures.
6. Wire frontend to canonical action priority behind legacy fallback.
7. Implement compact mobile sections.
8. Run full tests/build/typecheck/lint.
9. Review diff for any crawler/security/release-gate mutation; there should be none.
10. Only after explicit approval: decide whether to open/advance an integration PR. No deploy as part of this blueprint.

## Stop conditions

Stop integration and investigate if any change:

- changes page discovery/sampling/crawl budgets
- weakens evidence/release gates
- changes authority sealing/persistence unexpectedly
- produces a critical regression in existing customer scan recovery
- claims sitewide coverage from a sample without evidence
- treats missing URLs as verified fixes
- merges distinct root causes into one customer repair
- allows opportunity-class work to outrank severe confirmed failures without a documented rule
