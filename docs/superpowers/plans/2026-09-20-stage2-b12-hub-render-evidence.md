# Stage 2 B12 — paired raw/rendered hub-link evidence

## Scope

Requirement B12 from the approved full-scanner blueprint: compare retained link sets from paired successful raw/rendered evidence for up to five eligible hubs, bounded by the overall deadline and explicit rendering resource policy, while disclosing selected, completed, failed and unassessed hubs.

This slice stays on `agent/full-blueprint-stage2-coverage-b06-20260919` / PR #303 and does not move production, `main`, admission, worker traffic, schemas, secrets or customer data.

## Implemented at exact executable head

Exact executable head: `d612ceade6fc31ecd3e01d5b195dbd4d646524ef`.

Files:

- `scanner-api/app/stage2_hub_render_evidence.py`
- `scanner-api/app/render_followup.py`
- `scanner-api/app/scanner.py`
- `scanner-api/tests/test_stage2_hub_render_integration.py`
- `scanner-api/tests/test_stage2_run_scan_integration.py`

Behavior:

1. Select at most five retained B11-verified structural hubs, preferring one representative from each strong hub family before filling remaining slots. Ordinary leaf pages are not promoted merely because one sample contains many links.
2. Preserve the exact eligible-hub count and `selection_truncated` separately from selected/completed/failed/unassessed counts.
3. Reconstruct raw retained links only from B11 retained assessed-page provenance. If bounded B11 source samples are truncated such that absence of a source edge cannot be proven, fail the raw side closed rather than invent a render-only difference.
4. Accept rendered links only from an explicit renderer link collection. Missing link evidence is failed/unavailable, never an empty successful set.
5. Resolve rendered hrefs against the hub, remove fragments, and intersect only with the exact retained Standard-150 URL set. Unsampled targets cannot increase the assessed set or denominator.
6. Preserve exact path/query/case/reserved-escape identity. Because `urllib.parse.urljoin` removes an explicit empty query delimiter, the adapter restores that delimiter before exact retained-set matching so `/page` and `/page?` are not collapsed.
7. Use only the existing `run_render_followup` browser observations. `DEFAULT_RENDER_FOLLOWUP_LIMIT` remains three. B12 does not perform a separate render, fetch, coverage probe or scheduler operation.
8. Selected hubs not covered by that existing browser resource policy remain explicitly `unassessed`; attempted renderer failures are `failed`; only paired successful raw/rendered sets are `completed`.
9. New B12 failure provenance uses a normalized `renderer_failed` reason rather than copying raw exception text into the new evidence envelope. Existing browser-followup diagnostics are otherwise unchanged.
10. Pin `interpretation=paired_comparison_neither_surface_is_sole_truth` so raw and rendered sets remain comparison surfaces rather than competing authorities.
11. The shared caller gap is now closed without widening browser execution. `run_render_followup` has a separate `evidence_pages` retained-set input used only for B12 disclosure; its existing positional `pages` input still solely controls browser eligibility. `scanner.run_scan` passes `pages if material_render_risk else []` as the browser-policy input and always passes the final retained assessed set as `evidence_pages=pages`. When rendering policy declines browser work, eligible hubs can therefore be disclosed as selected/unassessed while `selected_pages=0`, `attempted_pages=0`, and no render callback is enabled.

## Behavioral regressions

Eight focused B12 regressions cover:

- max-five family-diverse structural hub selection plus eligible/selection-truncation counts;
- exact retained identity across case/query/reserved escape variants and unsampled rendered links;
- explicit empty-query delimiter preservation;
- fail-closed B11 truncated source samples;
- missing renderer link collection not becoming empty success;
- reuse of the existing three-page browser budget with completed/failed/unassessed disclosure and normalized failure provenance;
- no-renderer state remaining unassessed without invented rendered links;
- evidence-only retained-set disclosure cannot enable browser work when rendering policy declines.

The real `run_scan` integration regression additionally proves the exact final retained `result["pages"]` set is passed as `evidence_pages`, while the browser-policy input remains empty and `render_page` remains `None` when material rendering risk is absent.

## Verification

FixList CI `35483256047` passed both jobs on exact executable head `d612ceade6fc31ecd3e01d5b195dbd4d646524ef`:

- immutable checkout verified the exact SHA;
- root scanner regressions: **115 passed**;
- `scanner-api`: **1,932 passed / 18 intentional skips**;
- labelled Stage-1 synthetic corpus: 14 cases / 55 assertions, `full_30_site_gate=not_assessed`;
- frozen scanner revision `01ebe8e90df1e6bd`: passed;
- production scanner image: passed, image SHA `sha256:be6a8dfc68ad87a156698402cbf4f89199a05a938225a8a4f25cae01338d2c28`;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build: passed.

The workflow resolved Node `20.20.2`; do not describe this run as Node `20.19.5` runtime evidence.

A fresh incremental CodeRabbit review is requested for this exact head, focused on the separation between B12 disclosure and browser authorization, exact retained-set identity, no new request/render budget, and compatibility with existing `run_render_followup` callers. Independent review remains open until a current response is recorded.

## Source-completion status

The previously recorded shared `run_scan` caller gap is resolved at `d612ceade6fc31ecd3e01d5b195dbd4d646524ef`. B12 producer/source integration is implemented and exact-head CI green.

B12 is not yet recorded as independently reviewed on this final caller shape. No new customer repair/card or score adjustment is introduced by B12. If its link-set samples are later promoted into cards, previews, handoff or exports, add authenticated producer → Review → signed authority → persistence → entitlement/customer-output coverage before calling that display path complete.

## Next action

1. Resolve the current independent review request for the exact B11/B12 shared head and add a reproducing regression for any concrete finding.
2. Continue serialized Stage-2 engineering with B13/B14 local entity/NAP producer evidence, preserving fail-closed entity matching and optional-field semantics.
3. Then continue B15 and direct B17-transfer/B18 provider-state wiring.
4. Require exact-head FixList CI and independent review at meaningful combined checkpoints before Stage 3 shared integration.
