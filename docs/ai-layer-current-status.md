# FixList roadmap status — 2026-09-23

This checkpoint distinguishes built code, merged code, publication and customer acceptance. Do not rebuild B01–B28: the original scanner blueprint is complete and production accepted. Historical Stage-1 freezes and Stage-3/4 partial statuses are superseded by `docs/full-blueprint-progress.md` and the production recovery recap.

## Current customer milestone

Trustworthy rescan comparison, useful role explanations and concise implementation guidance remain the immediate milestone. The owner explicitly deferred Grok, chat and runtime model calls. The owner also requested less visible information: prioritize the repair cards, keep the role selector compact, and reveal supporting detail only when needed.

Verified production source: `ea6a99b8aaffea51c646124ae8cac777eb2de4a7` (PR #357). Base44 publication `35862100758` passed both public-site checks and all six V8 function identities. UI simplification merged as PR #358 into `99e74965775f731c120e185b0e26d11f150c084f`; main CI `35865324421` passed, but that UI has not been published. The gateway was published from `a9a96faf24ee9a841720981dcfbcee7bf0967a84`. Worker `fixlist-standard150-worker-00095-sn2` still serves; candidate `00096-76l` belongs to the earlier source and has not been promoted by this release.

| Item | Current evidence | Remaining gate |
| --- | --- | --- |
| R0 presentation reliability | Per-row degradation and canonical display ordering are merged and deployed | Preserve evidence and readable valid rows |
| H1-0 grounding, schemas, FixBench | This integration imports the reviewed pure foundation, closes both reported defects, and adds an explicit CI gate: 83/83 offline cases | Authenticate source snapshots at the future runtime adapter. Narrative/model-quality evaluation and runtime integration remain open; v1 unconstrained prose is rejected |
| H1-1 rescan comparison | Existing `compare_repair_runs()` is wired into the deployed signed comparison path | Live owner acceptance failed; use the newly deployed bounded support reference to identify the production failure |
| H1-2 role explanations | Deterministic copy is live and covers all seven current Funbooker repairs | Validate usefulness with less repeated framing |
| H1-3 implementation guidance | Pure deterministic plan and customer view are live; concise prerequisite-only presentation merged in PR #358 | Publish the simpler UI; keep canonical cards as the instruction surface |
| H1-4 targeted verification | This integration imports the pure stack and fixes accounting, malformed-state, MIME and stale-execution false positives | Protected execution, authority, persistence and customer wiring; provisional identities must never produce PASS |
| GEO | Experimental v1 view is live; score is correctly withheld. Reviewed v2 evidence/applicability and retained-only robots/llms.txt candidates are included here | Activate matching versioned extraction/assessment only after exact source authentication, persistence and reload gates; never lower thresholds to force a score |
| Adaptive 500/1,000 pages | PR #328 contains offline/shadow planning and benchmark helpers | Not integrated or authorized for production execution; still deprioritized behind the current milestone |

The architecture baseline is now preserved here at `docs/superpowers/specs/2026-09-22-ai-layer-architecture-blueprint.md`, with a clear notice that the original prose schema is superseded by the reviewed constrained v2 contract. The fuller owner proposal and reconciliation remain in PR #352. The old integration branch is not merged wholesale.

## Reliability integration checkpoint

- Grounding source `75d43d507ff55b9618e0eaefa3686c2f9addf3d6`: exact trusted evidence paths; arbitrary diagnostics/metadata collections cannot become evidence. Typed v2 declarations replace unverifiable free prose. Focused tests: 150 passed; FixBench: 83/83 cases across 11 suites. AI remains off.
- Targeted verification source `2528a21e09689af3841e710b66464911feee3e8f`: exact scheduler accounting and an explicit server-owned execution window bound into v2 receipts. Focused tests: 284 passed. Main already had repair-identity type hardening; this release does not rebuild it. The strongest evaluator and remaining protected path are documented in `docs/superpowers/plans/2026-09-23-targeted-verification-main-integration.md`.
- GEO source `28dc9ef3e174d4cb2cdeaa8f49b943ad553901b0`: isolated v2 candidate, leaving v1 semantics untouched. Foreign subjects, incomplete article exclusion, custom contexts and fabricated citation links fail closed. Focused tests: 161 passed. `authority_verified` stays false. See `docs/geo-v2-evidence-integration-2026-09-23.md`.
- Crawler recovery now honors initial HTTP 429 `Retry-After` for any server. If the required wait cannot fit, it does not retry or run active follow-up probes. The retained result remains access limited. Live IP configuration and website-owner firewall allowance are separate operational work; see `docs/crawler-access-reliability-2026-09-23.md`.

Independent reviews covered each slice. Local integrated checks are recorded in the release PR; exact-head repository CI remains required before merge. These checks do not authorize customer AI, targeted-verification PASS, GEO numeric display or a worker promotion.

The read-only gateway diagnostic rerun `35860744807`, job `107199156878`, succeeded at 13:21 UTC and returned no `/compare` request metadata in its eight-hour window. That is not proof of a healthy comparison or a specific configuration defect. The available browser is signed out of FixList. A live bounded CMP support reference is still needed to distinguish the failing reader/configuration/gateway boundary. Never synthesize production acceptance from local fixture signatures.

## Scheduled lanes checked

Five engineering lanes plus research are enabled. Their latest recorded launches were on 2026-09-23: Grounding 12:42 UTC; Rescan, GEO, Explanation and Research 12:46 UTC; Verification 10:54 UTC. A launch timestamp is not proof of completed work. The scheduled Integrator remains paused while the interactive release owner controls shared files and release gates.

| Lane | Latest reviewed durable checkpoint | Outstanding work |
| --- | --- | --- |
| Grounding, PR #339 | Older `b5c1f4a5623f68960cafa33f4a33c0ff7601d6d2` is superseded by the reviewed integration checkpoint above | Rebase onto integrated v2; preserve the closed contract and expand adversarial/model-free evaluation |
| Rescan, PR #337 | `e32e69c2204ba7e79d6d403d78d7c6410a6214d5`; comparison integrity guard | Core work already reused by the customer integration; resolve live failure without upgrading historical provisional identities |
| GEO, PR #341 | `10102a6eaa470106f5dbc3c24ddf61273eb9bba9` was reviewed into the isolated v2 candidate above | Source binding and authenticated V8/persistence/reload integration remain open |
| Explanation, PR #342 | `ca159fdc4730192c4ae754d86f2748171a62698e`; dependency identity hardening | Reconcile lane-only hardening with deployed roles; do not duplicate the repair list |
| Verification, PR #340 | `ad1ae90d54aac6bd908536f4c0684de6ccf3b750` was hardened into the v2 execution checkpoint above | Protected execution/customer integration; use the strongest fresh-execution evaluator |
| Research | Recent schedule launch observed | No fresh deliverable was verified in the source/PR audit |

All five listed engineering heads have successful repository CI. That does not close substantive review findings, integration or live acceptance. No new worker promotion is authorized by these test results alone.

## Presentation simplification already merged in PR #358

- Keep the selected role and distinct guidance inside each card; remove the two explanatory paragraphs beside the selector.
- Omit the duplicate implementation list when there is no verified prerequisite. When one exists, show only the before/after relationship and its rationale in a closed disclosure.
- Place scan coverage, folder accounting, optional focused scans and GEO after the actual repairs. Folder accounting and focused-scan suggestions start collapsed.
- Preserve visible scan limitations, comparison qualifications, card evidence, source instructions, authority checks and canonical repair ordering.

This UI patch does not fix or claim acceptance of the production comparison failure. It does not enable chat, runtime AI, larger crawls or a numeric GEO score.
