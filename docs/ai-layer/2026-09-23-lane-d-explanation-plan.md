# AI Layer Lane D — deterministic explanation and implementation planning

Status: lane checkpoint only; not integrated, merged, published, or deployed  
Lane branch: `agent/ai-explanation-plan-20260923`  
Baseline refreshed from `main`: `3609acc1be5beda86b77e95115342798f043841f` (PR #360 merged; not fresh publication acceptance)
Focused-green code checkpoint: `cd2db36319c1e991ca25b8bb708af1ec69ba46b2`

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
- lane-only `REPAIR_ROLE_EXPLANATION_LIBRARY_VERSION = role_explanation_copy_v2_20260923_top8_missing_h1_actions`
- `REPAIR_ROLE_PRESENTATION_VERSION = repair_role_presentation_v1`

### Current-main reconciliation and `missing_h1` action slice

Current `main` already carries the newer
`role_explanation_copy_v3_20260923_top11` library, covering eleven rule
families and every current Funbooker repair. This lane still contains the older
eight-rule table, so neither its complete role-copy file nor its lane-only v2
version string may replace current main.

Checkpoint `cd2db36319c1e991ca25b8bb708af1ec69ba46b2` changes only the four
`missing_h1` role variants plus the lane-local library version and pinned tests.
Each variant now gives one distinct next action inside the existing repair card:

- Owner delegates a check of the visible headline before anyone adds another.
- Marketing decides whether the existing headline wording is usable or needs
  rewriting.
- SEO validates topic alignment and H1 markup before recommending new copy.
- Developer inspects the rendered DOM and source/template, then marks up the
  approved headline or adds it once and verifies final HTML.

The wording continues to say that the scan did not find an H1; it does not
claim that no visible headline exists. The scanner-authored recommendation,
evidence, priority, repair identity and canonical order remain untouched. The
serialized integrator should port only these four strings and the focused
behavioral assertion onto main's top-11 table, then bump main's copy version to
a new top-11 revision. Do not transplant this lane's top-8 version string or
remove the three newer main-only rule families.

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

Focused Lane-D inventory at code checkpoint `cd2db36319c1e991ca25b8bb708af1ec69ba46b2`:

- role-explanation tests: 44
- role-presentation tests: 6
- implementation-plan core tests: 13
- implementation-plan authority-boundary tests: 8
- implementation-plan input-hardening tests: 15
- implementation-plan dependency-alias tests: 4
- total: 90

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
- four distinct, exact `missing_h1` next actions that first check for an
  existing visible headline instead of recommending a duplicate;
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

Fresh focused verification at code checkpoint `cd2db36319c1e991ca25b8bb708af1ec69ba46b2` passed all 90 Lane-D tests with `node --test` across the six role/presentation/implementation-plan suites. The last complete repository-wide lane checkpoint remains exact-head FixList CI #2961 / run `35845241862` on `ca159fdc4730192c4ae754d86f2748171a62698e`; it passed lint, typecheck, generated release-contract verification, all frontend contract tests, frontend build, root scanner regressions, the full scanner-api test suite, labelled corpus verification, frozen beta-revision verification, and production scanner-image build. The new checkpoint changes only deterministic `missing_h1` copy and its pinned tests; repository-wide CI must still run on the final pushed SHA.

Earlier material review identified unrelated canonical-row drift, coercive role/rule identifiers, inherited object-property lookups, invalid `evidence_refs` filtering, and scan-alias disagreement masking; those were fixed at prior checkpoints. The current checkpoint additionally closes dependency-edge alias ambiguity without changing customer copy, the two dependency rules, grouping semantics, or scanner authority.

## Integration handoff

The serialized integrator should wire these helpers only after comparing against the then-current `main` repair-presentation seam. The lane's stale top-8 table must not replace main's top-11 library. For the new `missing_h1` slice, port the four exact role strings and focused assertion onto the current table and use a new top-11 library version. Recommended UI behavior remains the existing per-view role toggle; do not persist a new customer schema field just to remember the selected role.

`implementation_plan_v1` may decorate the existing customer queue with execution grouping/order metadata, but it must not replace persisted canonical action priority or mutate repair rows. `trustedScanId` must come only from the existing exact-owner V8 authority reader; never derive it from repair copy or arbitrary client input.

Shared `FixList.jsx` wiring, authority/persistence/customer projection, release, deployment and production changes remain serialized-integrator-owned and are outside this lane.
