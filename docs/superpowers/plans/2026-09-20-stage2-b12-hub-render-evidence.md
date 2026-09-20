# Stage 2 B12 — paired raw/rendered hub-link evidence

## Scope

Requirement B12 from the approved full-scanner blueprint: compare retained link sets from paired successful raw/rendered evidence for up to five eligible hubs, bounded by the overall deadline and explicit rendering resource policy, while disclosing selected, completed, failed and unassessed hubs.

This slice stays on `agent/full-blueprint-stage2-coverage-b06-20260919` / PR #303 and does not move production, `main`, admission, worker traffic, schemas, secrets or customer data.

## Implemented at exact executable head

Exact executable head: `e3155ae722631189f338f7bd76225a5e35950bf5`.

Files:

- `scanner-api/app/stage2_hub_render_evidence.py`
- `scanner-api/app/render_followup.py`
- `scanner-api/tests/test_stage2_hub_render_integration.py`

Behavior:

1. Select at most five retained B11-verified structural hubs, preferring one representative from each strong hub family before filling remaining slots. Ordinary leaf pages are not promoted merely because one sample contains many links.
2. Preserve the exact eligible-hub count and `selection_truncated` separately from selected/completed/failed/unassessed counts.
3. Reconstruct raw retained links only from B11 retained assessed-page provenance. If bounded B11 source samples are truncated such that absence of a source edge cannot be proven, fail the raw side closed rather than inventing a render-only difference.
4. Accept rendered links only from an explicit renderer link collection. Missing link evidence is failed/unavailable, never an empty successful set.
5. Resolve rendered hrefs against the hub, remove fragments, and intersect only with the exact retained Standard-150 URL set. Unsampled targets cannot increase the assessed set or denominator.
6. Preserve exact path/query/case/reserved-escape identity. Because `urllib.parse.urljoin` removes an explicit empty query delimiter, the adapter restores that delimiter before exact retained-set matching so `/page` and `/page?` are not collapsed.
7. Use only the existing `run_render_followup` browser observations. `DEFAULT_RENDER_FOLLOWUP_LIMIT` remains three. B12 does not perform a separate render, fetch, coverage probe or scheduler operation.
8. Selected hubs not covered by that existing browser resource policy remain explicitly `unassessed`; attempted renderer failures are `failed`; only paired successful raw/rendered sets are `completed`.
9. New B12 failure provenance uses a normalized `renderer_failed` reason rather than copying raw exception text into the new evidence envelope. Existing browser-followup diagnostics are otherwise unchanged.
10. Pin `interpretation=paired_comparison_neither_surface_is_sole_truth` so raw and rendered sets remain comparison surfaces rather than competing authorities.

## Behavioral regressions

Seven focused B12 regressions cover:

- max-five family-diverse structural hub selection plus eligible/selection-truncation counts;
- exact retained identity across case/query/reserved escape variants and unsampled rendered links;
- explicit empty-query delimiter preservation;
- fail-closed B11 truncated source samples;
- missing renderer link collection not becoming empty success;
- reuse of the existing three-page browser budget with completed/failed/unassessed disclosure and normalized failure provenance;
- no-renderer state remaining unassessed without invented rendered links.

## Verification

FixList CI `35480882511` passed both jobs on exact executable head `e3155ae722631189f338f7bd76225a5e35950bf5`:

- immutable checkout passed;
- root scanner regression suite passed;
- full scanner-api suite passed, including all seven new B12 regressions;
- labelled Stage-1 synthetic corpus verification passed;
- frozen scanner revision verification passed;
- production scanner image build passed;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build passed.

A fresh incremental CodeRabbit review was requested for the combined B11 retained-link + B12 exact head. Independent review remains open until a current response is recorded.

## Known shared integration gap

B12 is **not source-complete yet**. `scanner.run_scan` currently calls:

`run_render_followup(pages if material_render_risk else [], render_page=... if material_render_risk else None)`.

That means the B12 adapter receives the final retained page set when browser follow-up is permitted, but receives an empty list when the explicit rendering policy declines browser execution. In that latter case the scan cannot disclose otherwise eligible retained hubs as selected/unassessed even though the B12 adapter itself models that state correctly.

The serialized integrator must make the final retained page set available to B12 disclosure regardless of whether the renderer is permitted, while keeping the renderer callback disabled whenever the existing policy says not to render. Do **not** increase `DEFAULT_RENDER_FOLLOWUP_LIMIT`, create another rendering loop, or create a second request/scheduler budget.

## Downstream/customer boundary

This slice adds evidence under the existing `render_evidence.browser_followup` object but does not create a new customer repair/card or score adjustment. If B12 link-set samples are later promoted into cards, previews, handoff or exports, add authenticated producer → Review → signed authority → persistence → entitlement/customer-output coverage before calling that display path complete.

## Next action

1. Fix the narrow `run_scan` caller disclosure gap without broadening browser execution.
2. Resolve current independent review findings, if any, with reproducing regressions.
3. Re-run exact-head FixList CI.
4. Only after B12 closes, continue B13/B14 local entity/NAP producer wiring, then B15/B17-transfer/B18.
