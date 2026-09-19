# Blueprint implementation checkpoint

> Release sequencing update (2026-09-19): the user explicitly authorized “once stage one is ready deploy and publish.” Complete and review all stage-one behavior before merging and publishing exact source. Earlier references to waiting for the entire blueprint are superseded for this first release. B06–B24 and the genuine 30-site full-blueprint gate remain open; synthetic stage-one acceptance does not complete them. No further general implementation or deployment approval is required.

This document preserves the original source-sharing checkpoint and its decisions. The receiving work agent has now completed stage-one implementation and the independent review; four Important findings have been corrected and the final local source gate passed (1,798 scanner and 1,479 frontend tests). Exact-source CI, merge and production cutover remain. See [current acceptance evidence](stage-one-evidence-acceptance.md) and [independent review](stage-one-independent-review.md) for current status. No deployment is claimed.

## Original source-sharing resume point

- Branch: `codex/full-blueprint-20260919`.
- Baseline: `7a744a501416b1b9feac462511071fc9f08e1ba1`.
- Completed identity-plan Task 1: `408da7c87e5170f698d28d66a9087a8d9fff5dcf`.
- Completed identity-plan Task 2: `2a50f1d93b246a5dd6f0463fa004f25cc0c6b0ef`.
- This checkpoint includes Task 3's implementation, tests, new package-local dependencies, historical fixture and generated mirrors. Task 3's formal task-done ledger step and Task 4's integrated export checks/independent whole-branch review remain open.
- The local `.superpowers` execution workspace is intentionally ignored and will not appear in a fresh clone. This tracked note carries the decisions and resume information needed by the receiving agent. Do not infer that absent scratch files mean Tasks 1 and 2 must be repeated.

Read the approved [full specification](superpowers/specs/2026-09-19-full-scanner-blueprint-design.md), [identity plan](superpowers/plans/2026-09-19-published-evidence-identity.md) and [overall progress](full-blueprint-progress.md). The earlier written-approval blocker is resolved by the user's explicit implementation approval.

## Implemented in Task 3

The durable Python producer explicitly selects `evidence_url_identity_v2_published_route`. Its matching Base44 writer uses `standard_review_snapshot_hmac_identity_v1`, while public V6 route names remain unchanged. Existing count/family columns and `raw_finding.published_evidence` retain authenticated identity, coverage, invariant and completeness metadata without a remote schema migration.

Real Python-produced canonical evidence survives writer persistence, saved-report and chat signature reconstruction. `/x`, `/x/` and `/X` remain three pages. The integration check exposed and fixed omitted chat child groups and priority identity/count fields. Customer completion state no longer invalidates the new chat authority; the persisted writer rejects unknown seal versions.

The literal historical GEO fixture remains unchanged under new-marker injection. New-seal route, escape, count, partition and version mutations are rejected. The request-level unpaid preview test enforces the two-fix limit without loading full hidden findings.

## Verification evidence

The last full pre-push implementation run passed 1,672 Python tests (18 intentional skips, 715 dependency warnings) and 1,461 frontend tests (zero failures/skips). Package closure and generated-contract checks passed. These are recorded implementation results, not full-blueprint acceptance.

Fresh checkpoint checks passed:

- 70 Node authority/invariant/dedup/GEO/historical/preview/round-trip tests.
- 93 Python grouped-metadata/identity/architecture/durable-completion tests, with 40 dependency warnings.
- `node scripts/base44_release_manifest.mjs verify`.
- `node scripts/generate_release_contracts.mjs --check`.
- `git diff --check`.

Python is 3.12 with `scanner-api/requirements.txt`; Node is 20.19.5. Put Node on PATH because Python integration tests spawn it. Run the full frontend suite under Linux/Bash 5 with actual Git history: macOS Bash 3.2 cannot execute some existing Bash-4 fixtures. The verified frontend image is `node:20.19.5-bookworm` at manifest digest `sha256:ba36e9b2705008e63e354214f0e3011c528af9df2ca13ac2bd2c0114650302e6`.

The pinned `ada-url==1.32.0` official wheels executed all 73 shared-identity/legacy tests on Linux arm64 and amd64, using read-only source and disabled test networking.

## Decisions carried from the local ledger

- Reject malformed/ambiguous authorities rather than guessing their identity; unusual malformed evidence can therefore be rejected.
- Use pinned Ada URL for origin-only WHATWG normalization; never pass observed paths/queries through its serializer. This adds a native dependency, verified on both Linux architectures.
- Mirror pure helper exports across required Base44 packages to preserve package parity; legacy helper behavior stays frozen.
- Resolve new producer evidence to absolute published keys using trusted scan-owned origin. Raw crawl observations remain unchanged; new reports may display absolute URLs where historical reports showed paths.
- Leave classification helpers unchanged. Only evidence joins receive the new identity context; integration coverage must catch missed consumers.
- Fail closed on unresolvable affected members rather than silently shrinking counts. Malformed new evidence can reject a report.
- Keep the pure snapshot builder's explicit legacy default; durable entries opt in to the new contract. Future alternate producers must explicitly opt in too.
- Store new metadata in existing raw evidence and authenticate existing count columns. Missing persisted metadata blocks re-signing.
- Move the real Python-to-all-readers integration test forward from Task 4 because handbuilt fixtures missed canonical field loss. This test requires Node on PATH.

## Checks identified at the original checkpoint

Finish the identity plan's persisted customer/card/PDF/JSON/CSV export checks, then full source verification and its independent whole-branch review. Use actual producer and consumer code, not a parallel serializer in tests.

Read-only investigation found that `evidenceLink` uses `new URL(...).toString()`, normalizing dot segments and literal Unicode; handoff examples can then deduplicate distinct observed spellings. Reproduce this at the export boundary before changing behavior. CSV serialization is currently inside FixList; existing source assertions do not prove its runtime output. Three-route card and handoff examples already retain the distinct case/slash spellings.

Stage 1 still needs the remaining image-alt applicability, visible-template, search-facing/indexability and synthetic acceptance work. Existing GEO is preserved in this stage; additional local/NAP coverage and combined SEO/GEO grouping/scoring remain later requirements. The full B01–B28 goal is not reduced to the identity plan.

## Release boundaries

Candidate fingerprint `5fb87bf7869c51c2` is explicitly a candidate, not frozen/accepted; accepted commit/report fields are empty. Historical fingerprint `47793ce37ca20523` remains supported.

The genuine 30-site baseline/candidate replay corpus is still missing. Historical summary counts are not substitute acceptance evidence. Base44 synchronization and app-level authentication previously failed and must be revalidated at release time.

The authorized first release requires complete stage-one source acceptance, exact-source CI, named schema parity, controlled cutover and verified Base44/worker activation. Live stage-one acceptance is required before recording the milestone as released and accepted. Remaining full-blueprint and 30-site requirements are not claimed by this release. Preserve the 150-page/security limits, existing GEO, historical proofs and preview privacy. Do not disconnect the repository, rotate secrets, broadly push schemas or publish a stale snapshot.
