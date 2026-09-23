# AI Layer Lane D — deterministic explanation and implementation planning

Status: lane checkpoint only; not integrated, merged, published, or deployed  
Lane branch: `agent/ai-explanation-plan-20260923`  
Baseline refreshed from `main`: `c1080d75f7d1aacd748e74009be7a6c15aa40a93` (V8 runtime cutover merged)  
Verified code checkpoint: `7243a0538a72150636d7e57241cc0b35474556fc`  

## Boundaries

This lane is presentation/planning only. It does not change scanner scoring, crawl, admission, authority, persistence, customer projection, Base44 schema, release, deployment, or production routes. Scanner-authored remediation and canonical repair ordering remain authoritative.

The current architecture requires the frontend to consume canonical backend action priority rather than rebuild a competing priority model. Page/template-family similarity is pattern evidence, not proof that repairs share one implementation root cause. Verified B20 root-cause evidence is versioned as `root_cause_evidence_v1_verified`; this lane consumes it read-only when available and only inside the exact scan boundary already authenticated by the owner-bound V8 reader.

No dedicated tracked H1-2/H1-3 blueprint file was present on refreshed `main`. This implementation follows the current lane contract, `docs/repair-priority-integration-blueprint.md`, `src/lib/repairSuggestions.js`, and the existing deterministic repair-presentation contracts.

## Production frequency refresh

Source: `docs/audit/2026-08-21-production-50-site/results.jsonl`, counting every entry in each authoritative result's `top_rules` list. The eight most frequent rules in that production audit are:

| Rank | Rule | Observations |
| --- | --- | ---: |
| 1 | `sitemap_redirect` | 82 |
| 2 | `image_alt_text` | 54 |
| 3 | `missing_h1` | 30 |
| 4 | `canonical_missing` | 22 |
| 5 | `potential_orphan_pages` | 20 |
| 6 | `internal_link_redirect` | 18 |
| 7 | `failed_page` | 16 |
| 8 | `duplicate_title_template` | 13 |

This is a historical production-frequency corpus, not a claim that the same distribution holds for every V8 scan. Current `main` still contains these rule identities in scanner/review/presentation code. Current content-evidence logic distinguishes material `image_alt_text` from uncertain `image_alt_review`, so role copy for `image_alt_text` describes a material missing text alternative rather than treating it as an uncertain image-purpose review.

## H1-2 role-specific explanation contract

Pure modules:

- `src/lib/repairRoleExplanations.js`
- `src/lib/repairRolePresentation.js`

Viewer roles are exactly `owner`, `marketing`, `seo`, `developer`. Runtime behavior is table lookup only; there is no runtime model call. Initial copy coverage is the eight production-frequency rules above: 8 rules × 4 roles = 32 pinned wording snapshots.

Versioning:

- `REPAIR_ROLE_EXPLANATION_VERSION = repair_role_explanation_v1`
- `REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION = role_explanation_copy_v1_20260923_top8`
- `REPAIR_ROLE_PRESENTATION_VERSION = repair_role_presentation_v1`

The role module imports `REPAIR_SUGGESTION_FALLBACK` from the existing deterministic suggestion library instead of creating a competing fallback. Missing roles and unmapped rules fail closed to that existing fallback; the helper never guesses a viewer role. Identifiers are string-only, so array/object coercion cannot turn malformed input into a supported role or rule. Direct rule-entry lookup is restricted to own registered keys, so inherited object properties cannot masquerade as mapped rules.

`repairRolePresentation()` returns the existing `repairSuggestion()` result intact and adds role explanation as separate presentation context. Scanner-authored remediation therefore retains its existing precedence and source metadata. No repair row is mutated.

Integration recommendation: the serialized integrator may add a per-view role toggle that passes one of the four viewer-role ids into `repairRolePresentation()`. No schema migration is required: role selection is presentation state and the wording version is returned by the helper.

## H1-3 `implementation_plan_v1`

Pure module: `src/lib/implementationPlan.js`.

The input array order is the canonical repair-priority baseline. The module does not recompute canonical priority or use page count to rank work.

### Versioned dependency table

`IMPLEMENTATION_DEPENDENCY_TABLE_VERSION = implementation_dependencies_v1_final_url_first`

Two hand-authored edges are registered:

1. `redirect_chain -> sitemap_redirect`: stabilize the final redirect destination before publishing that destination in the sitemap.
2. `redirect_chain -> internal_link_redirect`: stabilize the final redirect destination before replacing internal links with that destination.

Both edges require the two repairs to carry the same explicit verified `root_cause_evidence_v1_verified.root_cause_id`, non-empty contributing `evidence_refs`, and exact trusted scan binding. `evidence_refs` is all-or-nothing: it must be a non-empty list and every entry must be a non-empty string. Mixed-type or blank-entry lists fail closed and cannot instantiate grouping or dependency authority. Missing trusted scan identity fails closed. Repair-local `scan_id` / `scan_run_id`, when present, are consistency assertions and must match the trusted scan id exactly.

Control identifiers that can affect ordering or grouping are string-only. Malformed array/object values cannot be coerced into a valid scanner rule, verified evidence state, repair surface, remediation family, dependency-table version, or dependency-edge field. Invalid shapes therefore fail closed to canonical ordering and/or singleton grouping rather than creating implementation authority.

A lower action-priority repair can move ahead of a higher action-priority repair only as a prerequisite needed by a versioned dependency edge. Ordering walks canonical rows in order and recursively emits each row's prerequisites first. This matters for a three-row case such as `sitemap(fix_first), h1(important), redirect(improve)`: when verified evidence instantiates `redirect -> sitemap`, the deterministic order is `redirect, sitemap, h1`, not `h1, redirect, sitemap`. Unrelated work is not allowed to drift ahead merely because a canonical row is waiting on its prerequisite.

The priority-inversion verifier treats such collateral prerequisite movement as explicit only when the moved prerequisite reaches a dependency target whose canonical position is at or before the row it crossed.

### Grouping

Implementation groups are created only from:

- the same explicit verified root-cause id under the trusted scan boundary; or
- the same explicit `repair_surface` plus the same explicit `remediation_family`, also under the trusted scan boundary.

`page_template_family` is retained as descriptive metadata only. Two repairs with only the same page family remain separate groups. Surface/remediation grouping is presentation-only and never creates root-cause authority.

### Cycle behavior

If instantiated dependencies contain a cycle, the plan sets `cycleDetected=true`, `fallbackUsed=true`, discards applied dependency output, and returns the canonical input order. It does not attempt a partial reorder.

## Verification

Focused Lane-D inventory at code checkpoint `7243a0538a72150636d7e57241cc0b35474556fc`:

- role-explanation tests: 39
- role-presentation tests: 6
- implementation-plan core tests: 13
- implementation-plan authority-boundary tests: 6
- implementation-plan input-hardening tests: 7
- total: 71

Coverage includes:

- 32 rule × role wording snapshots;
- role inventory and exact library version;
- unmapped-rule fallback;
- missing/unsupported-role fallback;
- malformed array-shaped role/rule fail-closed behavior;
- inherited object-property rule names rejected;
- scanner remediation / id / action priority / evidence class / count / authority immutability;
- identical-input explanation and presentation stability;
- golden deterministic implementation plan;
- explicit dependency priority crossing;
- three-row prerequisite ordering that preserves unrelated canonical work;
- no dependency => no canonical reorder;
- unversioned or mismatched dependency edges cannot reorder;
- malformed array-shaped repair-rule identifiers cannot instantiate dependencies;
- malformed verified-state identifiers cannot grant root-cause authority;
- malformed repair-surface/remediation-family identifiers cannot create a shared group;
- malformed dependency-edge/table-version identifiers fail closed;
- mixed-type root-cause `evidence_refs` fail closed;
- blank root-cause `evidence_refs` fail closed;
- page-family-only no-grouping;
- scan-bound surface + remediation grouping;
- verified scan-bound root-cause grouping;
- missing trust / missing evidence refs / local scan mismatch fail closed;
- unverified/wrong-version root-cause rejection;
- cycle fallback;
- implementation-plan input immutability;
- identical-input plan stability;
- dependency table size/version.

Repository-native exact-head FixList CI #2907 / run `35823316618` passed on `7243a0538a72150636d7e57241cc0b35474556fc`. That run passed lint, typecheck, generated release-contract verification, all frontend contract tests, frontend build, root scanner regressions, the full scanner-api test suite, labelled corpus verification, frozen beta-revision verification, and production scanner-image build.

Earlier material review identified unrelated canonical-row drift, coercive role/rule identifiers, and inherited object-property lookups; those were fixed at prior checkpoints. The latest material review identified one remaining strictness gap: invalid `evidence_refs` entries were being filtered out instead of invalidating the entire verified-root-cause claim. The current code checkpoint now rejects mixed-type and blank-entry lists atomically, with two adversarial regressions, without changing the two production dependency edges or any scanner/customer authority path.

## Integration handoff

The serialized integrator should wire these helpers only after comparing against the then-current `main` repair-presentation seam. Recommended UI behavior is a per-view role toggle; do not persist a new customer schema field just to remember the selected role.

`implementation_plan_v1` may decorate the existing customer queue with execution grouping/order metadata, but it must not replace persisted canonical action priority or mutate repair rows. `trustedScanId` must come only from the existing exact-owner V8 authority reader; never derive it from repair copy or arbitrary client input.

Shared `FixList.jsx` wiring, authority/persistence/customer projection, release, deployment and production changes remain serialized-integrator-owned and are outside this lane.
