# Action Priority Export Contract — Implementation Plan

**Goal:** Make customer handoff exports preserve the backend-owned action priority without changing the historical technical-severity contract or any Standard 150 crawl/runtime behavior.

**Base:** `5a8022495e79eb6a229878643b076a924ac4048a`

## Invariants

- Keep `priority` unchanged as historical technical severity.
- Export the canonical repair card `actionPriority` as `action_priority`; do not recompute it from breadth/page count in the browser.
- Preserve repair order exactly as rendered by the canonical FixList.
- Keep historical/legacy fallbacks readable.
- No crawler, sampling, robots, SSRF, admission, authority, persistence, worker, or release-path changes.

## Steps

1. Add a focused frontend regression proving one canonical repair can be `priority: critical` while `action_priority: important`, and both values survive the handoff independently.
2. Verify the regression fails against the current exporter for the intended reason: row-level `action_priority` is absent.
3. Make the smallest implementation change in `src/lib/scanHandoff.js`: copy `card.actionPriority` into `action_priority` while leaving `priority` unchanged and preserving ordering.
4. Run the focused handoff regression and the complete frontend test suite through CI.
5. Inspect PDF export separately. Only change it in this PR if a focused regression can prove the same contract safely; otherwise keep PDF follow-up isolated.
6. Open a PR from this branch after the focused contract is green. Do not deploy from this work item.

## Acceptance

A Center Street-like repair whose technical severity is `critical` but backend action band is `important` exports both facts without contradiction: `priority: "critical"`, `action_priority: "important"`. The export still contains the same repair rows in the same order as the customer FixList.
