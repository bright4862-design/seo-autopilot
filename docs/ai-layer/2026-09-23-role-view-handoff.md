# H1-2 role explanation view

Base integration: `776e964b23b81a4759a590969ce981789a30d6d7`.

`src/components/fixlist/RepairRoleView.jsx` adds two standalone deterministic components:

- `RepairRoleSelector({ role, onRoleChange, disabled })`: native labelled select for owner/marketing/SEO/developer. Controlled per-view preference; emits only supported roles. Read-only without a callback. Does not persist anything.
- `RepairRoleExplanation({ repair, role })`: uses the existing `repairRolePresentation` helper to show the versioned role explanation beside the authoritative suggested change. Scanner-authored remediation keeps precedence. Missing repair renders nothing; missing rules/roles retain the existing library fallback. React escapes all output.

The caller supplies an already-authenticated repair from the current scan. These components neither establish authority nor alter rank, counts, scores, repair identity or repair rows. No model calls, generated copy, new comparison logic or schema changes.

## Shared-page handoff

The serialized integrator should hold one per-view role state (initial `owner`), place the selector above the repair list and pass the same role into each explanation view. Keep canonical cards, evidence and ordering intact. Avoid rendering duplicate instruction blocks: replace only the presentation slots intended for explanation/remediation, not the authoritative repair model. Do not persist a user setting solely for this feature.

This candidate edits no FixList/V8/persistence/release seam. Product activation still requires integrated page tests, browser/mobile acceptance and the usual exact-release gates.

## Fresh verification

- `node --test tests/frontend/repairRoleView.test.mjs tests/frontend/repairRolePresentation.test.mjs tests/frontend/repairRoleExplanations.test.mjs`: 52 passed, including 9 new view/interaction tests.
- Actual JSX rendered with React SSR; selector event handler exercised directly for valid/invalid/disabled input and controlled-state behavior.
- One initial test expected raw apostrophe text instead of React-escaped HTML; corrected the assertion to compare escaped text, without changing production behavior.
- Component ESLint, repository typecheck, `git diff --check`: passed.
- No browser visual test, full app suite, deployment or runtime AI enablement claimed.
