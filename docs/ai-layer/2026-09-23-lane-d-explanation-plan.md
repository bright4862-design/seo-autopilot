# AI Layer Lane D — deterministic explanation and implementation planning

Status: lane checkpoint only; not integrated, merged, published, or deployed  
Lane branch: `agent/ai-explanation-plan-20260923`  
Baseline refreshed from `main`: `c1080d75f7d1aacd748e74009be7a6c15aa40a93` (V8 runtime cutover merged)  

## Boundaries

This lane is presentation/planning only. It does not change scanner scoring, crawl, admission, authority, persistence, customer projection, Base44 schema, release, deployment, or production routes. Scanner-authored remediation and canonical repair ordering remain authoritative.

The current architecture already requires the frontend to consume canonical backend action priority rather than rebuild a competing priority model. Page/template-family similarity is pattern evidence, not proof that repairs share one implementation root cause. Verified B20 root-cause evidence is versioned as `root_cause_evidence_v1_verified`; this lane consumes it read-only when available.

No dedicated tracked H1-2/H1-3 blueprint file was present on refreshed `main`. The implementation below therefore follows the current lane contract plus `docs/repair-priority-integration-blueprint.md` and the existing deterministic suggestion/presentation libraries.

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

This is a historical production-frequency corpus, not a claim that the same distribution holds for every V8 scan. Current `main` still contains these rule identities in scanner/review/presentation code. In particular, current content-evidence logic distinguishes material `image_alt_text` from uncertain `image_alt_review`, so the role copy for `image_alt_text` describes a material missing text alternative rather than treating it as an uncertain image-purpose review.

## H1-2 role-specific explanation contract

New pure module: `src/lib/repairRoleExplanations.js`.

- Viewer roles are exactly `owner`, `marketing`, `seo`, `developer`.
- Runtime behavior is table lookup only; there is no model call.
- Initial copy coverage is the eight production-frequency rules above: 8 rules x 4 roles = 32 pinned wording snapshots.
- `REPAIR_ROLE_EXPLANATION_VERSION = repair_role_explanation_v1`.
- `REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION = role_explanation_copy_v1_20260923_top8` reconstructs the exact wording shown by this library.
- The module imports `REPAIR_SUGGESTION_FALLBACK` from the existing deterministic suggestion library instead of creating a competing fallback.
- Missing roles and unmapped rules fail closed to that existing fallback; the helper never guesses a viewer role.
- The helper does not read, replace, or mutate scanner remediation. Existing `repairSuggestion()` remains the authority for `suggestedFix`, including its `scanner_evidence` precedence.

Integration recommendation: the serialized integrator may add a per-view role toggle that passes one of the four viewer-role ids into `repairRoleExplanation()`. No schema migration is needed: role selection is presentation state and the wording version is returned by the helper.

## H1-3 `implementation_plan_v1`

New pure module: `src/lib/implementationPlan.js`.

The input array order is treated as canonical repair priority. The module does not recompute canonical priority or use page count to rank work.

### Versioned dependency table

`IMPLEMENTATION_DEPENDENCY_TABLE_VERSION = implementation_dependencies_v1_final_url_first`

Two hand-authored edges are registered:

1. `redirect_chain -> sitemap_redirect`: stabilize the final redirect destination before publishing that destination in the sitemap.
2. `redirect_chain -> internal_link_redirect`: stabilize the final redirect destination before replacing internal links with that destination.

Both edges require the two repairs to carry the same explicit, verified `root_cause_evidence_v1_verified.root_cause_id`. Without that evidence, the edge is not instantiated and canonical order does not move. This prevents a broad rule-level dependency from reordering unrelated repairs.

A lower action-priority repair can move ahead of a higher action-priority repair only when one of those instantiated versioned dependency edges requires it. Stable topological ordering always selects the earliest canonical row otherwise.

### Grouping

Implementation groups are created only from:

- the same explicit verified root-cause id; or
- the same explicit `repair_surface` plus the same explicit `remediation_family`.

`page_template_family` is retained as descriptive metadata only. Two repairs with only the same page family remain separate groups.

### Cycle behavior

If instantiated dependencies contain a cycle, the plan sets `cycleDetected=true`, `fallbackUsed=true`, discards applied dependency output, and returns the canonical input order. It does not attempt a partial reorder.

## Verification

Focused hermetic Node run:

```text
node --test tests/frontend/repairRoleExplanations.test.mjs tests/frontend/implementationPlan.test.mjs
48/48 passed
```

Coverage in that run:

- 32 rule x role wording snapshots;
- role inventory and exact library version;
- unmapped-rule fallback;
- missing/unsupported-role fallback;
- scanner remediation / id / action priority / evidence class / count / authority immutability;
- identical-input explanation stability;
- golden deterministic implementation plan;
- explicit dependency priority crossing;
- no dependency => no canonical reorder;
- page-family-only no-grouping;
- surface + remediation grouping;
- verified root-cause grouping;
- unverified/wrong-version root-cause rejection;
- cycle fallback;
- implementation-plan input immutability;
- identical-input plan stability;
- dependency table size/version.

The focused run uses only pure lane-owned modules; it does not certify the full repository frontend suite. Repository-native CI remains an integration gate after this checkpoint is pushed.

## Integration handoff

The serialized integrator should wire these helpers only after comparing against the then-current `main` repair presentation seam. Recommended UI behavior is a per-view role toggle; do not persist a new customer schema field just to remember the selected role. `implementation_plan_v1` can decorate the existing customer queue with execution grouping/order metadata, but it must not replace persisted canonical action priority or mutate repair rows.
