# H1-1 standalone comparison panel

Base integration: `776e964b23b81a4759a590969ce981789a30d6d7`.

Added `src/components/fixlist/ScanComparisonPanel.jsx`, a deterministic React view over the existing `buildScanComparisonPanelModel`. No new comparator, derived counts, score arithmetic or model calls. Shared FixList/V8 wiring remains integrator-owned.

## Behavior

- Renders fixed, still detected, returned, new-or-returned candidate, and could-not-verify counts without equating candidates with verified changes.
- Shows the server-provided before/after score, assessed-page counts and mandatory sample caution. The Funbooker-shaped fixture preserves 75 -> 72 and 126 -> 139 without asserting deterioration.
- Requires `authorityVerified === true` AND exact `currentScanId === presentation.current_scan_id`, after existing model validation. Invalid/mismatched input shows safe unavailable copy with no scores or counts. A first scan with no comparison renders no empty panel.
- React escapes all strings. Uses labelled section, definition-list metrics and a responsive grid. No raw error codes, scan IDs or owner controls shown.

## Integration contract

Render with `presentation`, `currentScanId` and `authorityVerified` only after the server has authenticated the customer, verified BOTH source scans/lineage/project/domain, and validated the comparison's authority-bound presentation. A boolean prop is a UI guard, not security or cryptographic verification. Do not build presentation from browser FixItems or pass raw `scan_comparison_v1`.

The current scan's seal alone is insufficient: the comparison and prior scan must be verified by the existing server path. Reset/withhold comparison props on navigation and never reuse data for a different scan. Keep provisional repair identities as could-not-verify. Wire through the serialized integrator; this PR does not edit `FixList.jsx`, V8, persistence or authority.

## Fresh verification

- `node --test tests/frontend/scanComparisonPanelView.test.mjs tests/frontend/scanComparisonPanelModel.test.mjs`: 21 passed.
- New tests render the actual JSX component through React SSR, including mismatched scan, missing authority, string-valued authority, unsupported contract, missing caution, first scan, text escaping and source immutability.
- Component ESLint: passed.
- Repository typecheck: passed.
- Production build: passed (chunk-size warning). As this component is not yet routed, its render tests verify its own compilation/behavior; the existing app build checks compatibility only.
- `git diff --check`: passed.

No browser visual acceptance, exact-head CI, live scan, merge or deployment claimed. Next gate: authenticated shared-page wiring, then desktop/mobile/reload acceptance on the exact integrated release.
