# Stage 3 B19/B20 isolated lane handoff — 2026-09-19

Branch: `agent/stage3-b19-b20-decisions-20260919`

Lane base: Stage-2 PR #303 head `b05fe3993422357959c7755a2eda47a2e635943f`.

This lane owns only independent B19 four-factor priority evidence and B20 explicit root-cause grouping helpers plus regressions. It intentionally does **not** edit `run_scan`, the shared coverage scheduler, B08 redirect meaning, B09/B16 coverage modules, current Review priority implementation, authority/persistence writers, customer projections, `main`, deployment, or live data.

## Exact verified code/test checkpoint before this documentation commit

- Code/test head: `0cfe4f394324bf12379b9fb141bd6d21bc67d1d4`
- FixList CI: https://github.com/bright4862-design/seo-autopilot/actions/runs/35463721721 — **SUCCESS**
- Immutable checkout: passed on the exact head.
- Root scanner regression job: passed.
- Full `scanner-api` test job: passed, including **19 new B19/B20 behavioral regressions**.
- Labelled Stage-1 synthetic corpus verification: passed; this does not change the genuine full-blueprint 30-site gate from `not_assessed`.
- Frozen scanner revision verification: passed.
- Production scanner-image build: passed.
- Lint, typecheck, generated release contracts, frontend contracts and frontend build: passed.

## Changed files relative to the Stage-2 lane base

- `scanner-api/app/stage3_priority_factors.py`
- `scanner-api/app/stage3_root_causes.py`
- `scanner-api/tests/test_stage3_priority_factors.py`
- `scanner-api/tests/test_stage3_root_causes.py`
- this handoff document

No pre-existing production/shared module was modified by this lane.

## B19 — four-factor priority evidence

`stage3_priority_factors.py` implements the approved versioned factor envelope:

- **Impact**: access/correctness 5, uniqueness 4, discovery 3, description/weight/freshness 2, low-impact alt/title/social optimization 1, decorative 0, plus conservative technical-severity fallback for unmapped rules.
- Rule-specific distinctions preserve the blueprint semantics: canonical gaps start at 2 and rise to 3 only with verified live duplicate-route evidence; noindex/indexability conflicts start at 3 and rise to 5 only for verified money-page evidence.
- **Reach**: affected observed/indexable pages divided only by the matching observed/indexable page-family denominator. Missing/cross-family evidence or a missing denominator is `unknown`, never zero. An observed same-family non-indexable affected page can truthfully produce known zero reach.
- **Page value**: money 1.0, hub 0.8, blog 0.5, utility 0.1. Repeated commercial leaves do not sum page value and therefore saturate instead of dominating by volume.
- **GSC weighting**: optional normalized page value is consumed only from the explicit `gsc_page_value_v1_normalized` envelope with provider `gsc`, current/fresh state and verified/connected-valid state. Disconnected, stale, unknown-version or invalid values do not affect weighting.
- **Confidence**: verified 1.0, heuristic 0.7, unverified 0.4. Mixed evidence markers fail toward the weaker state; a simultaneous unknown/access-limited marker cannot be overridden by a verified marker.
- Factor score is `impact × reach × page_value × confidence` only when reach and page value are known. Unknown factors remain unknown instead of being coerced to zero.
- Every envelope carries explanatory text stating the factor evidence and explicitly records that technical/base severity remains authoritative.
- `annotate_four_factor_priority` does **not** write or replace `priority`, `action_priority`, `action_priority_score`, existing base severity, or current Python Review ranking. Python Review remains the canonical ranking authority until serialized integration deliberately composes the new evidence.

Adversarial regressions cover unknown denominator, known-zero reach, high-severity leaf vs low-impact structural page, repeated leaf saturation, verified-vs-heuristic canonical duplicates, verified noindex money pages, GSC disconnected/connected behavior, exact confidence levels, and mixed-state fail-closed confidence.

## B20 — evidenced root causes

`stage3_root_causes.py` groups repairs only from explicit, versioned `root_cause_evidence_v1_verified` evidence.

A verified group requires:

- exact evidence version;
- verified/confirmed state;
- stable `root_cause_id`;
- at least one contributing evidence reference;
- exact scan identity;
- matching repair-surface identity when a surface is supplied.

Page-family similarity, generic impact class, similar wording, or repeated volume are never sufficient grouping evidence.

Verified groups may span SEO and GEO findings and multiple page/template families while retaining:

- SEO/GEO domain partitions;
- page-family partitions;
- exact first-seen affected-URL union without slash/case normalization;
- contributing evidence references;
- contributing observation IDs;
- suppression entries with reason, root cause, repair surface and evidence provenance.

Conflicted, unversioned, missing-reference or missing-scan-identity evidence fails closed to singleton `not_verified`/`conflicted` groups. Groups cannot cross scan identity or different repair surfaces.

Grouping preserves the first member's input/ranking position: if a later member joins an earlier verified root cause, the group remains at the earlier member's position instead of moving behind later singleton repairs.

Regressions cover same-family/no-evidence separation, mixed SEO/GEO verified grouping, exact URL unions, conflict fail-closed behavior, missing evidence references, cross-scan isolation, missing scan identity, differing repair surfaces and first-seen ordering.

## Review-hardening performed in this lane

Fresh self-review found and corrected three material risks before handoff:

1. Mixed `verified` + `unknown` evidence markers originally could inherit verified confidence. Confidence now fails toward the weaker evidence state.
2. Reach originally treated an observed same-family non-indexable affected page as an unknown denominator mismatch. Reach now distinguishes this truthful known-zero case from genuinely missing/cross-family evidence.
3. Root-cause groups originally could be appended after later singleton repairs, changing rank order. Groups are now anchored at their first member and later members mutate that group in place.
4. Exact scan identity is now mandatory for any verified root-cause merge, preventing accidental cross-run grouping when callers omit scan context.

CodeRabbit independent review was requested on draft PR #316 but the service reported its review quota/rate limit was exhausted at this checkpoint. That is recorded as **independent review unavailable**, not as a review pass.

## Shared integration still required

This lane is **integration-ready but not source-complete**. The serialized Stage-3/4 integration owner must complete the following after Stage 2 is source-complete and green:

1. Invoke B19 only on canonical Python Review repairs and decide the deliberate ranking composition. Do not let an unknown reach/page-value factor silently become zero, and do not replace technical/base severity.
2. Feed B19 only authenticated producer evidence for live duplicate routes, page roles/page family, indexability and optional GSC value. Align any GSC adapter with the final B18 connected/stale/unavailable contract rather than inventing provider data.
3. Persist/sign/authenticate any new customer-visible B19 factor fields and explanations through the canonical authority path without changing historical seal reconstruction.
4. Produce `root_cause_evidence_v1_verified` only from actual detector/shared-surface evidence. Do not infer a root cause from page family, repeated count, recommendation wording or impact similarity.
5. Run B20 after canonical ranking and before presentation caps/truncation so ranking remains evidence-led and exact affected unions are retained.
6. Carry exact `scan_id`, family/domain partitions, root-cause IDs, repair-surface IDs, contributing observations/evidence refs and suppression provenance through any authenticated handoff/customer representation. Suppressed-member debug artifacts should remain non-customer-facing unless the approved B24 contract explicitly permits them.
7. Add real canonical Review → signed authority → persisted rows → verified customer/handoff/export regressions before any new B19/B20 evidence is displayed to customers.
8. Run combined exact-head Stage-3 CI after integration against the final Stage-2 state; this isolated lane cannot certify shared integration compatibility in advance.

## Release boundary

Nothing in this lane is merged to `main`, deployed, staged, live-scanned or written to customer data. It changes no crawl/admission/scheduler/robots/SSRF/redirect/body/deadline/page-cap behavior and does not alter historical signatures.