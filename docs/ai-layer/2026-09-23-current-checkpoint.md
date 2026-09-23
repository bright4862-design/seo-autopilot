# AI-layer current checkpoint — 2026-09-23

## Scope and authority

Repository main inspected: `c1080d75f7d1aacd748e74009be7a6c15aa40a93`.
AI integration source inspected: `8faf869a66316bd7cbe3d749028853748a392944`.

The release owner's September 23 handoff supersedes the September 21 Stage-1 freeze and incomplete Stage-3/4 status in the older ledgers. B01–B28 are landed. Their historical RED/GREEN records are retained, not new implementation instructions.

This checkpoint is read-only source verification plus documentation. It does not certify current production, enable AI, merge lanes, or take ownership of shared integration. The scheduled AI Integrator remains the sole shared-seam and release owner.

## Roadmap state at the inspected integration SHA

| Item | Branch evidence | Remaining gate |
| --- | --- | --- |
| R0 per-row degradation | `repairCardModel.js` preserves canonical row order; malformed rows degrade individually. `customerRepairPlan.js` emits `presentation_mode` and `row_coverage` for degraded batches. | Exact-head CI/review and production acceptance; note that the implemented coverage field is `row_coverage`, not the recap's proposed `stage3_row_coverage`. Healthy/historical shapes intentionally remain unchanged. |
| H1-0 grounding | AI schemas, EvidenceSet, grounding verifier, offline FixBench and trace primitives are integrated. | An upstream authenticated authority boundary is still required; marker presence in an offline fixture is not cryptographic authority verification. Passing fixtures do not authorize customer AI. |
| H1-1 comparison | `scan_comparison.py` calls existing `compare_repair_runs`; integrity validation, transport helpers and standalone panel model exist. | Serialized V8/customer wiring and a genuine sealed stable repair identity source; keep provisional repairs incomparable. |
| H1-2 explanations | Versioned owner/marketing/SEO/developer helpers and presentation seam exist. | Shared customer UI wiring and acceptance by the integrator. |
| H1-3 implementation plan | Deterministic dependency planner and exact-scan root-cause authority regressions exist. | Shared customer UI wiring; never substitute execution order for canonical priority. |
| H1-4 verification | Bounded plan/evaluation core and budget-integrity tests exist. | Protected scheduler/rule execution, authenticated identity, persistence and customer integration; no endpoint is certified here. |
| GEO | Applicability/evidence work and fail-closed V8 candidate transport are integrated. | Actual sealed authority plus live acceptance; no threshold reduction and no score under insufficient evidence. |
| Chat | Not enabled by this work. | Consolidate duplicate grounding, retrieval, structured output, verification, budgets, evaluation and owner/beta rollout before customer enablement. |

## Next executable integration slice

1. Preserve the accepted Standard 150/V8 production release while certifying the exact integration source.
2. Resolve the H1-1 identity source before exposing any verified-fixed claim. The Lane-B handoff records all 13 inspected Funbooker FixItems as provisional, with empty `repair_surface` and `remediation_family`. Matching fingerprints alone cannot upgrade them.
3. Trace authenticated repair data through `scanner-api/app/repair_identity.py` and `base44/functions/persistDurableScanAuthorityV8/authoritySnapshotStage1Legacy.js`. The latter already projects both technical identity fields and the stability marker; do not assume missing schema is the cause. Find whether the producer supplied a genuine sealed identity, and if not, retain `could_not_verify` for history. Do not derive identity from UI copy or template similarity, or backfill historical authority.
4. Wire only a comparison derived from exact previous/current scan authority receipts through the existing validator and deterministic presentation. Preserve descriptive score/sample context: 75 to 72 over 126 to 139 checked pages is not proof of deterioration.
5. Require regressions for absent/provisional identity, cross-owner/scan input, failed authority, tampered counts, changed sampling and reload/history. Then follow existing exact-head CI/review, release and rollback requirements under the integrator.

Lane handoffs: [comparison integrity](../superpowers/plans/2026-09-23-ai-rescan-comparison-integrity-handoff.md), [comparison panel](../superpowers/plans/2026-09-23-ai-rescan-comparison-panel-handoff.md), [targeted verification](../superpowers/plans/2026-09-23-ai-targeted-fix-verification-handoff.md), [role explanations and planning](2026-09-23-lane-d-explanation-plan.md).

## Fresh local verification

At integration source `8faf869a`:

- Node tests for Stage-3 per-row degradation, implementation-plan authority, role presentation and scan-comparison panel: **25 passed, 0 failed**.
- `scripts/fixbench/run_grounding.py` fixture runner: adversarial suite **10/10**; V8 preservation suite **7/7**. These are synthetic offline cases, not live acceptance or general model-quality proof.
- Focused Python suites for grounding, V8 compatibility, schemas, traces, FixBench, comparison/integrity and targeted verification/budget integrity: **139 passed in 1.07s**. Command: `PYTHONPATH=scanner-api python -m pytest -q scanner-api/tests/test_grounding_verifier.py scanner-api/tests/test_grounding_v8_compatibility.py scanner-api/tests/test_ai_schema_registry.py scanner-api/tests/test_ai_trace.py scanner-api/tests/test_fixbench_grounding.py scanner-api/tests/test_scan_comparison.py scanner-api/tests/test_scan_comparison_integrity.py scanner-api/tests/test_targeted_fix_verification.py scanner-api/tests/test_targeted_fix_verification_budget_integrity.py`.
- Initial Python attempts failed before testing because this fresh workspace lacked dependencies. Installing `scanner-api/requirements.txt` resolved that environment issue; no source fallback or stub was introduced.
- `git diff --check`: passed. Full CI/build and live acceptance were not run in this documentation-only slice.

No production mutation, model call, main merge, customer scan, authority rewrite or historical-row modification was performed.
