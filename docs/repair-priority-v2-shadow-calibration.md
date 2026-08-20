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

A saved FixList is one durable repair snapshot and therefore has **one presentation authority**. Workflow state such as `Done`, deferred, search, or UI filtering may hide rows, but it must never change whether that saved snapshot is canonical, legacy, mixed, or unsupported.

Row-level `repair_contract_version` is deliberately **insufficient** to activate canonical UI. A future persisted v2 row must also carry snapshot-level proof that the whole durable FixList was written under the same supported contract.

Required activation fields are:

- `repair_contract_version = repair_contract_v2_shadow_calibrated`
- `repair_snapshot_contract_version = repair_contract_v2_shadow_calibrated`
- `repair_snapshot_contract_complete = true`

Current rules:

- no row or snapshot contract → frozen legacy presentation
- supported v2 row contract without complete snapshot attestation → frozen legacy presentation
- incomplete snapshot attestation → frozen legacy presentation
- row/snapshot version mismatch → unsupported / fail closed
- `repair_contract_v1_shadow` → unsupported / fail closed
- unknown future contract → unsupported / fail closed
- matching v2 row + complete matching v2 snapshot attestation → eligible for canonical presentation

The current production `FixItem` schema does not contain these v2 snapshot-attestation fields, so canonical activation remains intentionally dormant.

### Workflow-filter protection

The current frontend prepares the complete saved repair list before applying local `Done` filtering. During preparation it carries an **in-memory, presentation-only snapshot mode marker** onto the prepared rows. This marker is not persisted, signed, or treated as scan/review authority; it only prevents later UI filtering from reclassifying the same snapshot.

Regression coverage proves both paths:

1. Preferred future API: classify the complete snapshot, then pass filtered `visibleItems` for rendering.
2. Current page path: prepare complete snapshot → hide `Done` rows → classify remaining visible rows while preserving the earlier snapshot decision.

A mixed snapshot therefore cannot become canonical merely because the incompatible repair is marked Done.

## Future persistence ownership

The migration should prefer a parent FixList-level snapshot contract as the canonical ownership point, with row-level fields treated as consistent projections if they are needed for rendering or export.

The persistence design must guarantee:

- one exact `scan_id` / FixList snapshot
- one repair contract version for the snapshot
- complete-or-fail semantics; no partially migrated mixed list
- snapshot attestation written under the existing authority/HMAC boundary
- historical lists without the new contract remain readable as legacy
- browser workflow state never writes or changes the contract

Do not activate canonical UI from a subset of individually versioned rows.

## UI preparation that is safe before persistence

Allowed now:

- compact canonical row components
- section presentation
- sample-qualified scope copy
- priority-reason copy
- truthful progress presentation
- verification-state presentation
- frontend contract tests
- in-memory presentation-only snapshot guards

Not allowed without a separate approved migration:

- changing scanner behavior
- changing Python Review runtime ordering
- changing worker/admission behavior
- changing ScanRun terminal authority
- changing authority/HMAC payload semantics
- changing the production `FixItem` or FixList schema
- persisting v2 contract or snapshot-attestation fields
- activating frontend-only recomputed priority

## Activation sequence

1. Keep scanner/review/persistence runtime unchanged.
2. Collect shadow divergence on representative fixtures and saved evidence.
3. Lock v2 technical severity/evidence class rules with regressions.
4. Define additive parent FixList + row projection persistence fields and exact authority ownership.
5. Prove the entire snapshot is written atomically/consistently under one contract or fails closed.
6. Prove old scans remain legacy-readable.
7. Persist the complete versioned contract server-side in one deliberate boundary switch.
8. Run full frontend + scanner + authority + durable-state regressions.
9. Only then allow the canonical frontend gate to activate on newly persisted, snapshot-attested v2 repairs.

Any step that requires weakening scanner, authority, durability, or security contracts stops the integration rather than changing those contracts.
