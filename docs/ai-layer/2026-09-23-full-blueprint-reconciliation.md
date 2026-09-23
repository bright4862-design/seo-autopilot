# Full AI blueprint reconciliation — 2026-09-23

The owner supplied the full September 22 architecture/product blueprint on September 23 while implementation was in progress. Preserve its text verbatim in `docs/superpowers/specs/2026-09-22-ai-layer-full-proposal.md`. It is substantially broader than the abbreviated Grounding-lane spec currently stored at the originally suggested path. Do not silently replace deployed contracts to make the two documents appear identical.

## Controlling current state

The September 23 owner recap supersedes the proposal's historical release assumptions: Stages 1–4 landed, V8 replaced V7 in production, and submit/history/rerun acceptance was reported. R0-1 and R0-5 must be checked against current V8, not rebuilt from September 22 descriptions. The scheduled integrator owns all shared seams and release changes. AI/chat stay off; Standard 150 remains the product; GEO stays unscored without sufficient evidence and real authority.

## Latest owner steering

The owner explicitly deferred Grok on September 23 after supplying this blueprint. Defer all customer-facing model chat, provider selection and chat rollout. Prioritize deterministic rescan comparison, role-specific explanations, implementation plans, targeted verification and GEO evidence quality. Grounding/evaluation may continue without model calls. The full proposal remains a reference, not authorization to advance chat now.

## Requirement reconciliation

| Full proposal item | Current disposition |
| --- | --- |
| R0-1 package identities; R0-5 durable delivery | Owner recap reports V8 production recovery and accepted delivery. Preserve it and require fresh proof for future releases. |
| R0-2 per-row presentation | Integration branch has per-row fallback and local `row_coverage`; this is not proof of the proposed signed presentation fields/response counters. Treat the remaining telemetry/contract work separately. |
| R0-3/R0-4 retirement | Proposed, not executed here. Verify callers, deployment discovery and captured historical seal compatibility before deleting/moving packages. Do not retire V8 or reinstate V7. |
| R0-6 / T4 HF consolidation | Local candidate prepared but parked after the owner explicitly deferred Grok/chat. Do not prioritize its integration or rollout; chat remains off. |
| H1-0 full envelope | Current `ai_annotation_v1` differs from proposal §3.3: it lacks the complete owner/scan/release/subject/model/confidence envelope. Map and version any adapter/contract changes explicitly. Never treat model-supplied status/verifier metadata as authoritative. |
| H1-0 prose verification | Confirmed blocker below. Typed declaration checks alone do not establish that rendered prose is grounded. |
| H1-1 / H1-4 | Pure comparison/verification cores exist; customer integration and source identity proof remain open. PR #350 tests V8 identity transport. PR #351 addresses malformed identity coercion; it is a candidate, not a deployment. Never upgrade provisional history. |
| H1-2 / H1-3 | Deterministic role/planning helpers exist; customer UI, acceptance and required signed transport must be proved. Current steering favors a per-view role toggle; don't add a user-schema migration solely from the older proposal. |
| FixBench | Current synthetic 10-case adversarial and 7-case preservation suites are not the proposal's captured corpus or ten-suite benchmark. Need provenance manifest, Tier-A capture/privacy handling, false-fixed/injection gates, CI/reporting and usefulness review. |
| H1-5 | Off until verifier, retrieval, structured output, budgets and owner/beta gates pass. ≤8 repairs / ≤40 refs, top-three/header inclusion, message/token budgets are proposed acceptance targets, not implemented claims. |
| H2/H3 | GEO deterministic evidence can progress in parallel. Adaptive crawl, generic runtime/memory and platform extraction remain deferred. Cost estimates/dates are proposal assumptions, not fresh price research or delivery promises. |

## Reproduced H1-0 blocker: undeclared facts in free text

At integration `776e964b23b81a4759a590969ce981789a30d6d7`, copy the clean control from `scripts/fixbench/fixtures/grounding_adversarial_v1.json`, retain its valid evidence/claim arrays, replace only `payload.text`, and run `verify_grounded_payload(payload, sealed_l2=fixture['sealed_l2'])`:

| Replacement text | Observed verifier status |
| --- | --- |
| `Edit https://example.com/not-in-evidence now.` | `verified` |
| `Your health score is 999.` | `verified` |
| `FixList has applied the repair to your website.` | `verified` |

All are synthetic offline counterexamples. No customer output was generated or model called. `_annotation_errors()` checks declared `evidence`, `numeric_claims`, `fix_refs`, `root_cause_refs`, and `state_claims`; it does not inspect `annotation.text`. This fails full-proposal §3.3/§3.4 and FixBench attribution/no-state-claim requirements.

Next Grounding-lane slice: add these counterexamples and clean controls as failing acceptance cases; bind rendered factual atoms to exact evidence, including undeclared prose claims. Avoid claiming that a URL regex or numeric set alone proves semantic truth. Prefer constrained typed claims/deterministic rendering for factual content; arbitrary prose requires an explicit rejection/verification policy. Reject the whole independent annotation when safe structural redaction is impossible. Do not repair fabricated URLs or silently alter deterministic facts. Require actual verified authority before constructing the evidence context in customer integration.

This blocker takes priority over enabling any model-backed explanation or chat. Passing the existing synthetic suites does not close it.
