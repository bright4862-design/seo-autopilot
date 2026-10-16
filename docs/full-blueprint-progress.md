# Full blueprint progress

Updated 2026-09-23. This ledger supersedes the September 21 Stage-3 partial / Stage-4 held checkpoint formerly in this file. Its detailed regression history remains in Git and `docs/superpowers/plans/`.

## Accepted scanner baseline

The original B01–B28 scanner blueprint is complete through Stages 1–4 and landed in `main`. Stage 4 landed through PR #319, merge `dad5722fe787d608289ecb358acd65e87258a0e8`. Do not rebuild those stages from old lane branches.

The production baseline reported in the owner's September 23 acceptance recap is main `c1080d75f7d1aacd748e74009be7a6c15aa40a93`, V8 intake/history/customer routes, and worker `fixlist-standard150-worker-00095-sn2`. PRs #333–#336 repaired release alignment, canonical repair ordering, runtime reactivation and the V8 cutover.

The owner accepted Funbooker scan `6ab2abb3763febb79a7470e4` and rerun `6ab314008da962a9f8c58929`: authority sealed, score 72, seven repairs, customer display and reload/history working. The rerun checked 139 pages and points to `6ab272fc6dfa7f9faf97a90f`. These are historical acceptance records supplied by the owner, not a claim that a later candidate has been deployed or independently accepted.

## Active customer milestone

The AI-layer roadmap now governs new work: deterministic rescan comparison, useful role explanations, implementation guidance, targeted verification, and GEO evidence improvement. Grok and customer chat are deferred. Runtime model calls remain off.

The scoped customer-milestone release is based on accepted main and reuses the existing `compare_repair_runs`. It includes per-row Stage-3 degradation, authenticated comparison delivery, role explanations and deterministic implementation guidance. Implementation and test status must be distinguished from deployment and production acceptance; see the customer milestone release handoff.

Comparison must authenticate both saved results and the server-selected relationship. Missing page evidence cannot establish a fix. Different sample sizes, or equal counts with different pages, cannot establish overall improvement or regression from score changes alone.

Grounding/FixBench work remains separately gated. Do not merge the entire AI integration branch merely to publish these deterministic features. No numeric GEO score may appear before evidence and authority support it; do not lower thresholds.

## Release evidence

Each customer-path release still requires its exact source SHA, applicable CI and review, a known rollback, verified Base44 runtime/build identity, and live customer acceptance. Synthetic fixtures do not become live acceptance by updating this ledger.
