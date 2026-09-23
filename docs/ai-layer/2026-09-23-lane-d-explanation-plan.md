# AI Layer Lane D — deterministic explanation and implementation planning

Status: lane checkpoint only; not integrated, merged, published, or deployed  
Lane branch: `agent/ai-explanation-plan-20260923`  
Baseline refreshed from `main`: `c1080d75f7d1aacd748e74009be7a6c15aa40a93` (V8 runtime cutover merged)  
Verified code checkpoint: `2c66f0fe5855b4c1eab0a85fd38fb911ea882030`  

## Boundaries

This lane is presentation/planning only. It does not change scanner scoring, crawl, admission, authority, persistence, customer projection, Base44 schema, release, deployment, or production routes. Scanner-authored remediation and canonical repair ordering remain authoritative.

The current architecture requires the frontend to consume canonical backend action priority rather than rebuild a competing priority model. Page/template-family similarity is pattern evidence, not proof that repairs share one implementation root cause. Verified B20 root-cause evidence is versioned as `root_cause_evidence_v1_verified`; this lane consumes it read-only when available and only inside the exact scan boundary already authenticated by the owner-bound V8 reader.

No dedicated tracked H1-2/H1-3 blueprint file was present on refreshed `main`. This implementation follows the current lane contract, `docs/repair-priority-integration-blueprint.md`, `src/lib/repairSuggestions.js`, and the existing deterministic repair-presentation contracts.

## Production frequency refresh

Source: `docs/audit/2026-08-21-production-50-site/results.jsonl`, counting every entry in each authoritative result's `top_rules` list. The source file and refreshed `main` are unchanged from the prior lane checkpoint. The eight most frequent rules in that production audit remain:

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

Published scanner-rule aliases now fail closed atomically before explanation lookup. `rule`, `rule_id`, and `ruleId` (plus retained original rule aliases) must agree if more than one is present; a blank, malformed, or conflicting sibling alias cannot be hidden by a preferred field. `issue_type` remains a deterministic fallback only when no published rule alias is present. Matching aliases remain accepted and normal valid-row wording is unchanged, so the pinned copy-library version remains reconstructable without a wording bump.

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

Both edges require the two repairs to carry the same explicit verified `root_cause_evidence_v1_verified.root_cause_id`, non-empty contributing `evidence_refs`, and exact trusted scan binding. `evidence_refs` is all-or-nothing: it must be a non-empty list and every entry must be a non-empty string. Mixed-type or blank-entry lists fail closed and cannot instantiate grouping or dependency authority. Missing trusted scan identity fails closed.

Every published repair-local scan identity alias — `scan_id`, `scanId`, `scan_run_id`, and `scanRunId`, including aliases retained under `original` — is treated as a consistency assertion when present. Every present alias must be a non-empty string and must match the exact trusted scan id. A matching alias cannot hide a conflicting, non-string, or blank parallel alias; any such malformed sibling fails closed before root-cause dependency authority or surface/remediation grouping is granted.

Control identifiers that can affect ordering or grouping are string-only. Malformed array/object values cannot be coerced into a valid scanner rule, verified evidence state, repair surface, remediation family, dependency-table version, dependency-edge field, or scan identity assertion. Published `rule` / `rule_id` aliases, `repair_surface` aliases, `remediation_family` aliases, and accepted root-cause-evidence aliases must also agree when repeated across the normalized row/original payload. Conflicting or malformed siblings fail closed to canonical ordering and/or singleton grouping instead of creating implementation authority.

Dependency-edge aliases are now atomic consistency assertions too. If both `tableVersion` / `table_version`, `beforeRule` / `before_rule`, or `afterRule` / `after_rule` are published, both aliases must be non-empty strings and normalize to the same value. A conflicting or blank sibling invalidates that edge, so ambiguous dependency metadata cannot authorize a canonical-priority crossing. Matching camel/snake aliases preserve the same deterministic ordering.

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

Focused Lane-D inventory at exact code checkpoint `2c66f0fe5855b4c1eab0a85fd38fb911ea882030`:

- role-explanation tests: 43
- role-presentation tests: 6
- implementation-plan core tests: 13
- implementation-plan authority-boundary tests: 8
- implementation-plan input-hardening tests: 15
- implementation-plan dependency-alias tests: 4
- total: 89

Coverage includes:

- 32 rule × role wording snapshots;
- role inventory and exact library version;
- unmapped-rule fallback;
- missing/unsupported-role fallback;
- malformed array-shaped role/rule fail-closed behavior;
- conflicting and blank published role-explanation rule aliases fail closed;
- matching rule aliases preserve mapped deterministic copy;
- `issue_type` fallback remains available only when published rule aliases are absent;
- inherited object-property rule names rejected;
- scanner remediation / id / action priority / evidence class / count / authority immutability;
- identical-input explanation and presentation stability;
- golden deterministic implementation plan;
- explicit dependency priority crossing;
- three-row prerequisite ordering that preserves unrelated canonical work;
- no dependency => no canonical reorder;
- unversioned or mismatched dependency edges cannot reorder;
- conflicting dependency-table aliases fail closed;
- blank dependency-table sibling aliases fail closed;
- conflicting dependency-rule aliases fail closed;
- matching camel/snake dependency aliases preserve explicit versioned ordering;
- malformed array-shaped repair-rule identifiers cannot instantiate dependencies;
- conflicting published repair-rule aliases cannot instantiate dependencies;
- malformed verified-state identifiers cannot grant root-cause authority;
- conflicting accepted root-cause-evidence aliases fail closed;
- malformed retained root-cause evidence cannot be hidden by a valid preferred alias;
- malformed repair-surface/remediation-family identifiers cannot create a shared group;
- conflicting repair-surface/remediation-family aliases cannot create a shared group;
- malformed dependency-edge/table-version identifiers fail closed;
- mixed-type root-cause `evidence_refs` fail closed;
- blank root-cause `evidence_refs` fail closed;
- conflicting scan-identity aliases cannot be hidden by a matching preferred alias;
- conflicting scan identity retained in `original` prevents surface/remediation grouping;
- non-string scan-identity aliases fail closed;
- blank top-level scan-identity aliases fail closed even beside a matching alias;
- blank scan identity retained under `original` fails closed even beside a matching top-level alias;
- page-family-only no-grouping;
- scan-bound surface + remediation grouping;
- verified scan-bound root-cause grouping;
- missing trust / missing evidence refs / local scan mismatch fail closed;
- unverified/wrong-version root-cause rejection;
- cycle fallback;
- implementation-plan input immutability;
- identical-input plan stability;
- dependency table size/version.

Repository-native exact-head FixList CI #2959 / run `35844960021` passed on `2c66f0fe5855b4c1eab0a85fd38fb911ea882030`. That run passed lint, typecheck, generated release-contract verification, all frontend contract tests (including the new dependency-alias regressions), frontend build, root scanner regressions, the full scanner-api test suite, labelled corpus verification, frozen beta-revision verification, and production scanner-image build. CodeRabbit commit status is also green on that exact head.

Earlier material review identified unrelated canonical-row drift, coercive role/rule identifiers, inherited object-property lookups, invalid `evidence_refs` filtering, and scan-alias disagreement masking; those were fixed at prior checkpoints. The current checkpoint additionally closes dependency-edge alias ambiguity without changing customer copy, the two dependency rules, grouping semantics, or scanner authority.

## Integration handoff

The serialized integrator should wire these helpers only after comparing against the then-current `main` repair-presentation seam. Recommended UI behavior is a per-view role toggle; do not persist a new customer schema field just to remember the selected role.

`implementation_plan_v1` may decorate the existing customer queue with execution grouping/order metadata, but it must not replace persisted canonical action priority or mutate repair rows. `trustedScanId` must come only from the existing exact-owner V8 authority reader; never derive it from repair copy or arbitrary client input.

Shared `FixList.jsx` wiring, authority/persistence/customer projection, release, deployment and production changes remain serialized-integrator-owned and are outside this lane.
