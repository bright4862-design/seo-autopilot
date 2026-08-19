# FixList Repair Priority v2 — Shadow Calibration Gate

Status: integration-prep only  
Runtime activation: **disabled**  
Production schema migration: **not performed**  
Crawler / worker / authority architecture: **unchanged**

## Why v2 exists

The historical Python Review `priority` field is not a pure technical-severity value. Its current score already includes contextual signals such as evidence confidence, representative-page value, raw affected-page reach, and structural/trust boosts.

That makes it useful as a legacy customer ordering signal, but unsafe as the new `base_severity`. Reusing it would allow a broad metadata family to inherit `critical` technical severity simply because many URLs are affected.

The calibrated v2 shadow model therefore separates four concepts:

1. `base_severity` — inherent technical seriousness.
2. `evidence_class` — confirmed problem, improvement, or opportunity.
3. `action_priority` — Fix first, Important, Improve, or Review.
4. contextual evidence — eligible checked coverage, indexability, important-page distribution, confidence, and explicitly confirmed repair leverage.

Legacy `priority` remains untouched during migration.

## Current v2 contracts

- priority model: `repair_priority_v2_technical_severity`
- shadow presentation contract: `repair_contract_v2_shadow_calibrated`
- repair identity: versioned technical identity from `repair_identity.py`
- verification: contract-comparable and eligibility-aware

`repair_contract_v1_shadow` is intentionally unsupported by the frontend activation gate because its base-severity fallback could inherit reach-inflated legacy priority.

## Runtime boundary

The following production/runtime surfaces must not import or call the shadow/calibrated modules before an explicit migration decision:

- `scanner-api/app/scanner.py`
- `scanner-api/app/main.py`
- `scanner-api/app/review.py`
- `base44/functions/aiReviewScan/entry.ts`
- `base44/functions/persistScanAuthority/index.ts`

Regression tests enforce this boundary.

The shadow adapters consume a **finished** review result, deep-copy it, annotate it, calculate a proposed order, and report divergence. They do not write back into the review result.

## Calibration principles

### Technical/base severity

High is reserved for defects whose inherent consequence can materially block access, crawl/index correctness, or structural routing, for example:

- broken/server-blocked pages
- meaningful rate-limit/access failures
- redirect chains / failed destinations
- route-boundary pages exposed to indexing
- sitemap/indexability conflicts

Medium covers meaningful but normally non-catastrophic configuration/content defects, for example:

- missing canonicals
- internal redirect cleanup
- metadata gaps
- H1 gaps
- structured-data gaps

Low covers lower-inherent-impact optimization or investigative work, for example:

- image-alt gaps
- overlong/repeated titles
- repeated meta descriptions
- potential orphan pages
- potential topic overlap

Explicit future `base_severity` / `technical_severity` from a canonical producer overrides the taxonomy.

### Evidence class

`confirmed_problem` means the condition is sufficiently established and its consequence is operational/technical rather than merely optimization advice.

`improvement` includes deterministic optimization findings whose existence is confirmed but whose consequence does not justify presenting them as a structural failure, such as broad metadata, H1, schema, image-alt, or repeated-title work.

`opportunity` covers inferred/investigative work such as potential orphan or topic-overlap findings.

`needs_verification`, `inconclusive`, `provisional`, and similar evidence states cannot silently become confirmed problems.

### Action priority

- confirmed high/critical technical problem → `fix_first`
- confirmed medium problem → `important`
- lower-severity or optimization work → `improve`
- inferred/opportunity work → `review`

Within a band, context may refine ordering without redefining technical severity.

## Indexability consistency

Priority and repair verification must interpret the same existing page evidence consistently.

The v2 shadow priority normalization recognizes `noindex` across:

- explicit scanner-owned `indexable=false`
- `robots`
- `robots_meta`
- `meta_robots`

An explicit scanner-owned boolean wins. The shadow layer does not mutate crawler evidence; it normalizes a copied page object only for priority analysis.

For search-facing rules, pages that become non-indexable must not inflate searchable coverage and cannot automatically support a `Verified fixed` claim.

## Verification boundary

`Verified fixed` requires all of the following:

- stable technical repair identity
- comparable rule-definition / comparison-profile contract when required
- prior affected URLs re-observed
- continued eligibility for the same check
- same repair condition no longer detected

Missing URLs, redirects/errors/blocks, search-facing pages becoming noindex, or changed comparison contracts fail closed to `Could not verify`.

## Real-evidence shadow checks

Read-only authoritative FixLists were inspected to challenge the model, including:

- Funbooker
- Center Street Lending
- Airbnb

These checks exposed cases where broad metadata/image-alt/title families received high/critical legacy priority through reach, validating the need for the technical-severity split.

No live entity or schema was modified.

## Frontend activation gate

Canonical `Fix first / Important / Improve / Review` sections render only when the entire displayed repair list carries a supported persisted contract.

Current rules:

- no contract → frozen legacy presentation
- `repair_contract_v1_shadow` → unsupported / fail closed
- unknown future contract → unsupported / fail closed
- `repair_contract_v2_shadow_calibrated` → eligible for canonical presentation **only if actually persisted**

The current production `FixItem` schema does not yet contain the required v2 fields, so canonical activation remains intentionally dormant.

## UI preparation that is safe before persistence

Allowed now:

- compact canonical row components
- section presentation
- sample-qualified scope copy
- priority-reason copy
- truthful progress presentation
- verification-state presentation
- frontend contract tests

Not allowed without a separate approved migration:

- changing scanner behavior
- changing Python Review runtime ordering
- changing worker/admission behavior
- changing ScanRun terminal authority
- changing authority/HMAC payload semantics
- changing the production `FixItem` schema
- persisting v2 contract fields
- activating frontend-only recomputed priority

## Activation sequence

1. Keep scanner/review/persistence runtime unchanged.
2. Collect shadow divergence on representative fixtures and saved evidence.
3. Lock v2 technical severity/evidence class rules with regressions.
4. Define the additive persistence schema and exact authority ownership.
5. Prove old scans remain legacy-readable.
6. Persist the complete versioned contract server-side in one deliberate boundary switch.
7. Run full frontend + scanner + authority + durable-state regressions.
8. Only then allow the canonical frontend gate to activate on newly persisted v2 rows.

Any step that requires weakening scanner, authority, durability, or security contracts stops the integration rather than changing those contracts.
