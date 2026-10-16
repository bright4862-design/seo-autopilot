# FixList roadmap status — 2026-09-23

This checkpoint distinguishes built code, merged code, publication and customer acceptance. Do not rebuild B01–B28: the original scanner blueprint is complete and production accepted. Historical Stage-1 freezes and Stage-3/4 partial statuses are superseded by `docs/full-blueprint-progress.md` and the production recovery recap.

## Current customer milestone

Trustworthy rescan comparison, useful role explanations and concise implementation guidance remain the immediate milestone. The owner explicitly deferred Grok, chat and runtime model calls. The owner also requested less visible information: prioritize the repair cards, keep the role selector compact, and reveal supporting detail only when needed.

Verified production source before this presentation patch: `ea6a99b8aaffea51c646124ae8cac777eb2de4a7` (PR #357). Base44 publication `35862100758` passed both public-site checks and all six V8 function identities. The gateway was published from `a9a96faf24ee9a841720981dcfbcee7bf0967a84`. Worker `fixlist-standard150-worker-00095-sn2` still serves; candidate `00096-76l` belongs to the earlier source and has not been promoted by this release.

| Item | Current evidence | Remaining gate |
| --- | --- | --- |
| R0 presentation reliability | Per-row degradation and canonical display ordering are merged and deployed | Preserve evidence and readable valid rows |
| H1-0 grounding, schemas, FixBench | Built on the AI integration/lane branches; absent from main | Open evidence-path and unsupported free-text claim defects; integrate only after those are resolved and independently verified |
| H1-1 rescan comparison | Existing `compare_repair_runs()` is wired into the deployed signed comparison path | Live owner acceptance failed; use the newly deployed bounded support reference to identify the production failure |
| H1-2 role explanations | Deterministic copy is live and covers all seven current Funbooker repairs | Validate usefulness with less repeated framing |
| H1-3 implementation guidance | Pure deterministic plan and customer view are live | Simplify the view: show prerequisite relationships only when verified; keep canonical cards as the instruction surface |
| H1-4 targeted verification | Pure contracts and bounded plan/budget logic are built on a branch | Protected execution, authority, persistence and customer wiring; provisional identities must never produce PASS |
| GEO | Experimental view is live; score is correctly withheld | Integrate evidence/applicability and authenticated transport candidates; never lower thresholds to force a score |
| Adaptive 500/1,000 pages | PR #328 contains offline/shadow planning and benchmark helpers | Not integrated or authorized for production execution; still deprioritized behind the current milestone |

The approved AI architecture document is preserved at `docs/superpowers/specs/2026-09-22-ai-layer-architecture-blueprint.md` on `ai-layer/integration-20260923` (`776e964b23b81a4759a590969ce981789a30d6d7`). The fuller owner proposal and reconciliation are in PR #352. Do not merge that entire integration branch merely to publish a focused customer UI change.

## Scheduled lanes checked

Five engineering lanes plus research are enabled. Their latest recorded launches were on 2026-09-23: Grounding 12:42 UTC; Rescan, GEO, Explanation and Research 12:46 UTC; Verification 10:54 UTC. A launch timestamp is not proof of completed work. The scheduled Integrator remains paused while the interactive release owner controls shared files and release gates.

| Lane | Latest reviewed durable checkpoint | Outstanding work |
| --- | --- | --- |
| Grounding, PR #339 | `b5c1f4a5623f68960cafa33f4a33c0ff7601d6d2`; verifier/schema/70-case FixBench foundation | Material review still rejects recursive diagnostics/metadata evidence membership; free-text unsupported facts are also unresolved despite green CI |
| Rescan, PR #337 | `e32e69c2204ba7e79d6d403d78d7c6410a6214d5`; comparison integrity guard | Core work already reused by the customer integration; resolve live failure without upgrading historical provisional identities |
| GEO, PR #341 | `10102a6eaa470106f5dbc3c24ddf61273eb9bba9`; exact scored-observation transport binding | Unsealed candidate awaiting shared V8/persistence/reload integration |
| Explanation, PR #342 | `ca159fdc4730192c4ae754d86f2748171a62698e`; dependency identity hardening | Reconcile lane-only hardening with deployed roles; do not duplicate the repair list |
| Verification, PR #340 | `ad1ae90d54aac6bd908536f4c0684de6ccf3b750`; pure targeted verification stack | Shared identity hardening and protected execution/customer integration |
| Research | Recent schedule launch observed | No fresh deliverable was verified in the source/PR audit |

All five listed engineering heads have successful repository CI. That does not close substantive review findings, integration or live acceptance. No new worker promotion is authorized by these test results alone.

## Presentation simplification in this patch

- Keep the selected role and distinct guidance inside each card; remove the two explanatory paragraphs beside the selector.
- Omit the duplicate implementation list when there is no verified prerequisite. When one exists, show only the before/after relationship and its rationale in a closed disclosure.
- Place scan coverage, folder accounting, optional focused scans and GEO after the actual repairs. Folder accounting and focused-scan suggestions start collapsed.
- Preserve visible scan limitations, comparison qualifications, card evidence, source instructions, authority checks and canonical repair ordering.

This UI patch does not fix or claim acceptance of the production comparison failure. It does not enable chat, runtime AI, larger crawls or a numeric GEO score.
