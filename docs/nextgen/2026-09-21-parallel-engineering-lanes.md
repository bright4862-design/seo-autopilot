# Next-generation FixList parallel engineering lanes — 2026-09-21

Base integration line: `nextgen/integration-20260921`

Frozen starting source for these lanes:
`53d8d110d44c2b779b2ca0f270bf6fea6f9e28e2`
(the canonical PR #319 integration head when the lanes were created).

These lanes are NEXT-GENERATION follow-on work. They do not replace or weaken the
current B01–B28 release gate. No lane may merge, deploy, publish, alter production,
change admission, rotate credentials, or claim release acceptance.

## Shared architecture rules

1. Preserve the existing Standard 150 contract and its current safety boundaries.
2. New deeper behavior must be opt-in/shadow-first and versioned.
3. Reuse the existing scanner, evidence, authority, persistence and repair contracts.
4. New evidence must retain provenance, coverage and truthful unknown/not-verified states.
5. Do not create a second crawler, second report authority, or hidden unbounded fetch path.
6. Network work must reuse existing safe request/DNS/SSRF/redirect/body/deadline/robots controls.
7. Keep historical report reconstruction byte-compatible.
8. Lane agents must not edit shared integration surfaces unless explicitly owned below.
9. Add failing behavioral regressions before implementation where practical.
10. Each lane must finish with exact changed files, tests run, totals, blockers and an integration handoff.

## Serialized integrator ownership — DO NOT MODIFY IN LANE BRANCHES

Only the serialized integrator may change shared wiring in:
- `scanner-api/app/scanner.py` run_scan orchestration / global scan budgets
- shared authority/seal/persistence writers/readers
- repair priority composition / final customer ranking
- Base44 customer projections / preview entitlement paths
- ScanRun entity schema
- public route generations / admission / durable worker controls
- release manifest, deployment/promotion workflows, production config
- existing historical reconstruction bytes or signing contracts

Lane branches may create pure helpers/adapters/tests and explicit proposed integration points.
If a lane requires a shared-surface change, stop and document the required integrator patch.

## Agent A — Adaptive Crawl
Branch: `agent/nextgen-adaptive-crawl-20260921`

Own:
- pure adaptive selection/scoring helpers
- 150→500→1000 tranche planning
- marginal discovery/Fix-yield telemetry
- simulation/benchmark tooling and fixtures
- tests proving Standard 150 remains unchanged

Do not own repair priority, final customer projection, authority/persistence or run_scan wiring.

Primary output:
- deterministic pure selector + telemetry contract
- benchmark comparing smart-500 vs blind-1000
- integration handoff describing minimal run_scan hook

## Agent B — Semantic Graph
Branch: `agent/nextgen-semantic-graph-20260921`

Own:
- template/zone inference helpers
- semantic/topic clustering using deterministic/local interfaces
- weighted internal-link graph model
- cannibalization/near-duplicate candidate analysis
- source→target internal-link proposal evidence
- pure tests and fixtures

Do not write final customer fixes, repair priority, persistence or scan orchestration.

Primary output:
- graph evidence contract + deterministic analyzers
- no external model dependency required for correctness
- integration handoff to repair/root-cause layer

## Agent C — Browser / Performance
Branch: `agent/nextgen-browser-performance-20260921`

Own:
- CrUX/PSI adapter interfaces with explicit unavailable/error states
- representative template/high-value page sampler
- Lighthouse result normalization contract
- raw vs rendered critical-content parity evidence helpers
- performance/browser evidence tests

Do not add credentials, call live providers in deterministic tests, modify worker budgets,
or wire customer scoring.

Primary output:
- provider-neutral performance evidence envelopes
- sample-selection logic
- integration handoff showing where later browser execution should attach

## Agent D — Evidence Connectors
Branch: `agent/nextgen-evidence-connectors-20260921`

Own:
- provider-neutral connected-evidence schema
- GSC Search Analytics / URL Inspection normalization
- Bing AI Performance import schema (CSV/Excel-derived rows normalized in pure code)
- GA4 AI-assistant evidence normalization
- explicit unsupported/not-connected/not-verified states
- import fixtures and tests

Do not create new OAuth scopes/credentials, enable external accounts, alter Base44 schema,
or perform live provider calls in CI.

Primary output:
- stable evidence adapter contract
- import parsers/normalizers with provenance
- no claim that undocumented Google Gen-AI API endpoints exist

## Agent E — Fix Verification
Branch: `agent/nextgen-fix-verification-20260921`

Own:
- acceptance-criterion contract layered over existing repair identity/versioning
- targeted recheck planning as pure data (which URLs/evidence need re-observation)
- PASS/PARTIAL/FAIL/COULD_NOT_VERIFY state machine
- regression reopening semantics
- tests preserving current verified_fixed comparability rules

Do not modify final persistence/customer projection or cross-scan authority wiring.

Primary output:
- versioned verification-plan/result contracts
- focused regressions
- integration handoff for serialized authority/persistence wiring

## Integration order

1. Current B01–B28 release remains authoritative and must finish independently.
2. Agents A–E work independently on their branches.
3. No lane PR merges directly to main.
4. Integrator reviews lane contracts first, then selectively integrates in this order:
   A adaptive crawl foundations
   B semantic graph
   C browser/performance
   D connected evidence
   E fix verification
5. Integration branch runs full existing suites after every lane transplant.
6. Customer-visible feature flags remain off until shadow/corpus acceptance passes.

## Definition of done for every lane

- branch starts from the frozen nextgen integration base
- no forbidden shared surfaces changed
- focused tests demonstrate intended semantics
- full relevant local suite run when feasible
- no live production/provider mutation
- exact commit SHA recorded
- handoff document describes integration hook, data contract, tests, risks and rollback
