# FixList Repair Contract v2 — Additive Persistence Blueprint

Status: **design only**  
Production schema mutation: **not authorized / not performed**  
Runtime wiring: **not authorized / not performed**  
Scanner / worker / admission topology: **unchanged**

## Objective

Persist the calibrated repair-priority, identity, verification, and explicit-rule-evaluation contracts without changing the Standard 150 crawler pipeline and without invalidating any historical authority seal.

The core rule is:

> One authoritative FixList snapshot has one repair contract and one canonical customer order.

Browser workflow state (`Done`, deferred, filters, search) may change visibility only. It must never choose or change snapshot authority.

## Existing durable ownership

The current durable model already gives us the right hierarchy:

`ScanRun 1 -> 1 FixList 1 -> many FixItems`

Therefore:

- **FixList owns snapshot-level repair contract authority.**
- **FixItem carries the signed per-repair projection.**
- **ScanRun stays the scan lifecycle/release authority and does not become a second repair-order owner.**

Do not infer snapshot contract from whichever FixItems happen to be returned or visible.

## Authority/HMAC compatibility constraint

Current authority sealing signs a structured snapshot, persists rows derived from that snapshot, then `getCustomerScanResult` reconstructs the same snapshot from rows and verifies the existing HMAC proof.

This creates a strict backward-compatibility requirement:

1. Historical rows must reconstruct to the **exact historical payload shape**.
2. New repair fields must not be inserted as empty strings, `false`, empty arrays, or default objects when verifying an old scan.
3. New signed fields must be **conditionally present only when the persisted snapshot contract says they exist**.
4. The same conditional field set and normalization must exist in both the trusted snapshot builder and the row-to-snapshot reconstruction path.
5. Any mismatch must fail closed; do not ignore a repair field merely to make the HMAC verify.

The preferred migration keeps the existing outer authority mechanism and stable serializer intact while adding a versioned repair sub-contract conditionally for new scans. If implementation proves that cannot preserve byte-for-byte historical reconstruction, introduce a new authority-envelope version deliberately rather than silently changing v1 semantics.

## Snapshot-level FixList fields

Proposed additive fields on `FixList`:

```text
repair_contract_version: string
repair_snapshot_contract_version: string
repair_snapshot_contract_complete: boolean
repair_priority_model_version: string
repair_identity_version: string
repair_verification_version: string
canonical_action_fix_ids: string[]
rule_evaluation_contract_version: string
rule_evaluations: object[]
```

Activation values for the current calibrated design:

```text
repair_contract_version = repair_contract_v2_shadow_calibrated
repair_snapshot_contract_version = repair_contract_v2_shadow_calibrated
repair_snapshot_contract_complete = true
repair_priority_model_version = repair_priority_v2_technical_severity
```

`repair_snapshot_contract_complete=true` may be written only when every persisted FixItem for the snapshot has the matching required per-item contract and the row count exactly matches the signed recommendation count.

### `canonical_action_fix_ids`

This is the authoritative customer repair order, not merely a “top three” convenience field.

Important: do **not** repurpose the existing `top_action_fix_ids` field. Today the authority snapshot sorts recommendations by `fix_id` for deterministic sealing before deriving that legacy field. It is therefore not a safe v2 customer-priority authority.

For v2:

1. Canonical priority/order is produced before deterministic HMAC ordering.
2. Save the ordered repair IDs separately in `canonical_action_fix_ids`.
3. Recommendations may still be sorted by stable `fix_id` inside the signed snapshot for deterministic serialization.
4. UI sections consume the persisted canonical order; the frontend does not independently score/rerank repairs.

The list must contain every v2 repair exactly once. Duplicates, missing IDs, unknown IDs, or length mismatch make `repair_snapshot_contract_complete=false` / persistence ineligible.

## Per-repair FixItem fields

Proposed additive signed fields on `FixItem`:

```text
repair_contract_version: string
base_severity: critical | high | medium | low
evidence_class: confirmed_problem | improvement | opportunity
action_priority: fix_first | important | improve | review
canonical_action_rank: number
action_priority_score: number
priority_reason: string
priority_context: object
repair_identity_version: string
repair_fingerprint: string
repair_surface: string
remediation_family: string
shared_repair_confirmed: boolean
rule_definition_version: string
comparison_profile_version: string
repair_verification_version: string
repair_verification_state: string
```

The existing legacy `priority` field remains untouched for historical compatibility. It must not be renamed or silently redefined as v2 `base_severity`.

`action_priority_score` is internal evidence for deterministic ordering within a band. Customer UI should normally show the action band plus `priority_reason`, not a numeric score.

`canonical_action_rank` and the parent `canonical_action_fix_ids` must agree exactly.

## Stable repair identity

V2 identity must use durable technical identity, not presentation metadata.

Required identity inputs should remain bounded to the stable repair contract, for example:

- canonical rule ID
- explicit repair surface
- explicit remediation family

Do not include mutable display/grouping fields such as category labels or page-template-family labels in the stable fingerprint merely because they are convenient for presentation.

Affected URLs remain evidence/comparability inputs, not the entire identity definition.

## Verification fields

A persisted verification result must never be inferred from “the repair disappeared.”

A v2 historical transition requires:

- stable repair identity
- comparable `rule_definition_version`
- comparable `comparison_profile_version`
- prior affected URLs re-observed where required
- continued rule eligibility
- predicate actually re-evaluated

If any required comparability evidence is missing, the state is `could_not_verify` / `could_not_compare`, not `verified_fixed`.

## Explicit passed-check evaluation ledger

The “Already good” UI must not infer success from absence of a repair.

Proposed FixList-level evaluation contract:

```text
rule_evaluation_contract_version = rule_evaluation_v1_explicit
rule_evaluations = [
  {
    rule: string,
    rule_definition_version: string,
    evaluated: boolean,
    applicable: boolean,
    passed: boolean,
    eligible_checked_count: number,
    evaluated_page_count: number,
    limitation_code: string
  }
]
```

Customer reassurance is allowed only for entries with:

```text
evaluated === true
applicable === true
passed === true
```

No evaluation row means **unknown**, not pass.

A skipped rule, unsupported page type, access limitation, evidence failure, suppression decision, or synthesis omission must never become a passed claim.

The evaluation ledger must come from a trusted server-owned evaluation stage. It must not be reconstructed from the final recommendation list.

## Trusted snapshot-builder insertion point

Do not attach v2 fields after the HMAC has already been verified.

The future runtime switch belongs at the trusted authority snapshot construction boundary:

1. Python Review remains canonical review/evidence owner.
2. The approved v2 repair synthesis produces complete annotations + canonical order.
3. The authority snapshot builder validates the entire v2 contract.
4. It writes the snapshot-level contract into `snapshot.fix_list` and per-repair contract into `snapshot.recommendations` **before signing**.
5. Existing persistence maps the signed snapshot into `FixList`/`FixItem` rows.
6. Row reconstruction includes those fields only for a complete v2 snapshot and verifies the same HMAC.
7. Customer projection exposes only the whitelisted v2 fields after authority verification.

Do not modify scanner discovery, crawl scheduling, page sampling, page caps, rate-limit behavior, worker admission, or browser lifecycle to support this migration.

## Complete-or-fail persistence validation

Before `repair_snapshot_contract_complete=true`, verify all of the following server-side:

- parent FixList contract version supported
- all expected FixItems persisted
- persisted FixItem count equals signed recommendation count
- every FixItem carries matching `repair_contract_version`
- every FixItem has a non-empty stable repair fingerprint/version where required
- every FixItem action priority is valid
- every FixItem canonical rank is unique and in range
- `canonical_action_fix_ids` length equals recommendation count
- `canonical_action_fix_ids` contains exactly the persisted fix IDs
- parent order and item ranks agree
- authority proof matches ScanRun + FixList + every FixItem

Any failure leaves the scan non-canonical/fails persistence rather than publishing a partial v2 list.

## Historical compatibility

Historical scans have none of these fields.

Required behavior:

- missing repair contract => legacy presentation
- old HMAC payload reconstructs without new keys
- old `priority`, `top_action_fix_ids`, and historical FixItems remain readable as-is
- no backfill is required merely to render old scans
- no browser-side migration of saved records
- reopening an old scan can never recompute it under the newest prioritizer

## Customer projection

The paid customer projection will eventually need to whitelist the approved v2 fields explicitly. Do not return raw authority internals or use `raw_finding` as an escape hatch for the contract.

Parent projection should include the snapshot version/completeness, canonical order, and explicit rule-evaluation ledger. Item projection should include only the customer-safe repair fields needed for presentation/history.

## Rollout sequence

1. Keep the current shadow model runtime-off.
2. Lock the exact schema proposal and canonical ordering invariants with tests.
3. Add schemas in an isolated migration candidate; no production cutover.
4. Add conditional signed snapshot serialization for v2 while preserving historical v1 reconstruction byte-for-byte.
5. Add row reconstruction + HMAC regressions for both historical and v2 fixtures.
6. Add complete-or-fail persistence validation.
7. Add paid projection whitelist fields.
8. Run full frontend, scanner, durable-state, authority/HMAC, admission, page-cap, robots/SSRF, and historical-read regression suites.
9. Canary a newly generated v2 scan while old saved scans remain legacy.
10. Only after evidence is green allow snapshot-attested v2 rows to activate canonical UI.

## Explicit non-goals

This migration does **not** require:

- crawler topology changes
- sampling changes
- Standard 150 cap changes
- rate-limit strategy changes
- robots/SSRF changes
- Deno fallback changes
- browser-owned terminal state
- a second frontend prioritizer
- historical data rewrites

If implementation requires any of those, stop and redesign the migration rather than altering the proven scanner architecture.
