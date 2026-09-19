# Full blueprint progress

> Release sequencing update (2026-09-19): the user explicitly authorized “once stage one is ready deploy and publish.” Complete and review all stage-one behavior before merging and publishing exact source. Earlier references to waiting for the entire blueprint are superseded for this first release. B06–B24 and the genuine 30-site full-blueprint gate remain open; synthetic stage-one acceptance does not complete them. No further general implementation or deployment approval is required.

Goal: build and deploy the complete applicable user-supplied scanner blueprint.

## 2026-09-19 baseline and design

- Authoritative GitHub main checked with `git ls-remote origin refs/heads/main`: `7a744a501416b1b9feac462511071fc9f08e1ba1`.
- Isolated local clone: `work/seo-autopilot-blueprint`; local implementation branch: `codex/full-blueprint-20260919`.
- User approved staged implementation using the existing scanner, preserving old reports and current crawl/security limits, with deployment after full blueprint acceptance.
- Written design: [Full scanner blueprint](superpowers/specs/2026-09-19-full-scanner-blueprint-design.md). It records B01–B28 acceptance requirements and awaits the written-spec review required by the brainstorming workflow.
- No production-code changes, pushes, deployments, schema writes or live scans have been made in this phase.

## Confirmed blocking defect for evidence correctness

A fresh in-memory reproduction uses the real `extract_page`, `build_page_pattern_findings`, `evidence_url_key` and `normalize_repair_scope` functions. Input: three complete HTTP-200 HTML pages, each missing a meta description, at:

```text
https://example.com/x
https://example.com/x/
https://example.com/X
```

Observed current behavior:

```json
{
  "legacy_identity_keys": ["/x", "/x", "/x"],
  "review_page_count": 2,
  "review_affected_pages": ["/x", "/X"],
  "review_metadata_missing_observations": 3,
  "normalized_scope_page_count": 1,
  "normalized_scope_affected_pages": ["https://example.com/x"]
}
```

Required new-report behavior: three distinct affected pages through review, canonical grouping, persisted authority, verified projection and export. Historical reports retain legacy byte/signature reconstruction. An observed redirect to one final page remains a different case from three independent 200 responses.

The migration audit also identified slash-losing singleton suppression in the JavaScript authority writer and path-based priority/cross-run joins. Fixing only the Python identity helper cannot satisfy the end-to-end requirement.

## Verification environment

- Local Node 20.19.5/npm 10.8.2 were prepared to match the workflow runtime.
- Local Python virtual environment has scanner requirements and pytest.
- Earlier full local release-gate run passed lint, typecheck, build, Base44 package checks, Python/scanner checks and manifest checks; frontend baseline had 1,368 passes and eight failures. These historical results are not post-change verification.
- The eight frontend failures were traced to macOS Bash 3.2 parsing Bash-4 associative arrays under `set -u`, before their behavioral assertions ran.
- A clean, unshimmed rerun of `base44V3RuntimeRecovery.test.mjs` and `base44V3RuntimeRecoverySept14.test.mjs` passed 11/11 tests under Node 20.19.5 and Bash 5.2.37 in the existing `fixlist-scanner:merged-main-check` container. Network was disabled, root/repository/Node mounts were read-only and `/tmp` was isolated. No test/source edits or credentials were used. This is a scoped result, not a fresh full-suite pass.
- Linux Node runtime: sibling `work/node-v20.19.5-linux-arm64`; the official tarball's verified SHA256 is `d462267863ae8ee556039ebdf559055a8ec562c633889ef1403f3adb449ba1dd`.

### Fresh full frontend baseline

The complete frontend suite at `7a744a501416b1b9feac462511071fc9f08e1ba1` now passes: **1,376 tests, 1,376 passed, zero failures/skips**, exit 0. Command inside the isolated environment: `node --test --test-reporter=spec tests/frontend/*.test.mjs`.

The verified runtime is the official `node:20.19.5-bookworm` image, manifest digest `sha256:ba36e9b2705008e63e354214f0e3011c528af9df2ca13ac2bd2c0114650302e6`: Node 20.19.5, Bash 5.2.15, Git 2.39.5 and Python 3.11.2. Test inputs came from `git archive HEAD` into disposable executable tmpfs; dependencies and Git metadata were read-only mounts. Network was disabled and the root filesystem was read-only. No source/test changes or service calls were used to make this pass.

Two intermediate environment runs were not green and are retained in `.release/`: the read-only/noexec setup prevented test scratch commands; the writable archive lacked Git and history. A shallow-history gap was also found: the historical `33f471e` fixture did not exist locally. Fetching history without changing the checkout restored that real fixture before the final passing run. The final log is `.release/baseline-frontend-node20-bookworm.log`.

This is baseline evidence for existing behavior, not acceptance evidence for unimplemented blueprint requirements or a complete release gate.

## Release blocker, separate from implementation

Base44 Builder has displayed `Couldn't fetch your code from GitHub` with publishing disabled. Its development snapshot was older than the GitHub candidate; the live deployment was also not proven to match that candidate. A connected label or loaded preview is insufficient evidence of synchronization. Local CLI app-level credential validation also failed despite a cached `whoami` identity.

Do not disconnect the repository, publish a stale snapshot, rotate secrets or infer that the deployment wrapper caused the Builder fetch failure. Revalidate exact source, named schema changes, active runtime identities and owner authorization at release time.

## Next work

1. Complete written-design review.
2. Write the first executable implementation plan for evidence correctness, including the versioned Python/JavaScript identity contract and historical fixtures.
3. Implement with failing behavioral regressions first; independently review each coherent task and run integrated checks.
4. Continue all remaining B01–B28 requirements; the first stage is not a substitute for full blueprint completion.

## Specification self-review

- Cross-checked the final seven PDF pages against the register, adding the explicitly named `scripts/assertCorpusRun.mjs` runner, the 30-site baseline/candidate gate and operator-only suppression visibility.
- The named assertion runner is absent at the starting commit; the design requires creating it, not claiming an existing gate passed.
- Preserved the approved safety amendments over the PDF's unsafe/broader sketches: bounded requests, no automatic sibling-host expansion or UA impersonation, conservative image/local applicability and no blanket accessibility suppression on noindex pages.
- Identified and recorded the writer-side second deduplication, seal-selected reconstruction, historical version comparability and GEO-capability requirements for the new identity revision.
- Documentation whitespace checks pass; no production implementation is claimed.

## 30-site gate input inventory

The repository does not yet contain the data needed to claim the blueprint's 30-site no-new-artifact gate passes.

- `data/renderer-risk-study-manifest.jsonl` provides 30 unique sites, 10 per stratum. Its workflow and collector are live-run renderer studies, not full scanner baseline/candidate comparisons. The expected study output files are not tracked or present locally.
- `docs/audit/2026-08-21-production-50-site/matrix.csv` and `results.jsonl` provide 50 historical summary rows, including 30 completed scans. This is a different roster; the summaries contain neither full page/FixItem evidence nor paired candidate outputs. They cannot silently be combined with the renderer roster into a passing corpus.
- Existing synthetic HTTP fixtures cover four sites. Other tracked synthetic scan snapshots and derived fingerprint fixtures are useful test inputs but not a replayable 30-site corpus.
- `scripts/acceptance-gates.mjs` evaluates one current scan bundle. It does not compare baseline/candidate artifacts. The PDF's named `scripts/assertCorpusRun.mjs` still needs to be implemented.

Required input contract: one explicit canonical 30-site manifest; stable site IDs; paired comparable baseline/candidate artifacts with source/fingerprint, capture time, URL/scope/mode and evidence-backed artifact identities. A deterministic CI gate also needs immutable sanitized HTTP response fixtures (robots, sitemaps, redirects, status/headers/HTML) so it executes current source rather than merely comparing precomputed exports. Any newly captured fixture must be labelled as such; historical summary counts are not substitute evidence.

This inventory was read-only: no new live scans, provider calls or source edits.

## Goal blocker audit

The written-design review requested after the high-level architecture approval remains unanswered across three consecutive goal turns. Baseline verification and the corpus-input inventory are complete; their processes are terminal. GitHub main remains `7a744a501416b1b9feac462511071fc9f08e1ba1`, and this branch still has only the two new documentation files, with no production-code edits.

The brainstorming workflow requires written-spec approval before implementation. Further repeated status checks do not advance the build, and no additional in-scope preparation is needed to resolve this decision. Mark the goal blocked, not complete, pending approval of the linked design. On approval, resume with the first executable implementation plan and retain the entire B01–B28 objective. Deployment additionally remains subject to the recorded release/authentication and acceptance gates.

## Implementation resumed — 2026-09-19

The user explicitly approved the written design: **“Approved—start implementation.”** This resolves the historical approval blocker above. The first executable plan is `docs/superpowers/plans/2026-09-19-published-evidence-identity.md`; implementation starts with literal shared Python/JavaScript URL-identity regressions. Root owns the coupled changes on the existing isolated branch. The full B01–B28 objective and deployment gates remain unchanged.

### First implementation slice: identity primitives

- Added opt-in published-route identity helpers in Python and the package-local JavaScript mirrors, preserving legacy behavior. The new helper retains case, trailing slash, reserved escapes, raw query ordering and foreign-origin distinctions.
- Added 72 shared literal cases. New assertions failed before implementation; historical assertions stayed green. Follow-up origin regressions caught Unicode scheme case-folding, line-separator handling and IDNA2008/WHATWG differences.
- Added pinned `ada-url==1.32.0` for origin-only WHATWG normalization; paths and queries never enter its serializer. This avoids handwritten Unicode/bidi rules. Scanner image installation must be verified before release.
- Fresh full checks: **1,647 scanner tests passed, 18 intentional skips, 694 existing dependency warnings; 1,449 frontend tests passed with no failures/skips.** Base44 package closure and generated-contract checks passed. The independent bounded Python/JS comparison reported 98 cases with zero differing pairs.
- This is not yet a fix to produced report counts: connecting the helper through producers, authority, persistence and export is the next dependent work. No push, live scan or deployment occurred.

### Second implementation slice: opt-in Python production path

- Threaded trusted scan-origin/version context through extraction-derived findings, review filtering, grouped suppression, exact family/role/indexability joins, canonical evidence union and priority calculation. Classifier normalization and legacy defaults remain unchanged.
- The real three-HTTP-200-route case now retains three affected pages through review and canonical grouping. Merged source URLs, coverage counts and ordering use the same evidence identity.
- Cross-run verification rejects mismatched/unknown URL identity versions and cannot resolve an old relative URL against a different scan's origin or silently discard unresolved evidence.
- Behavioral regressions failed before each fix. Full pre-checkpoint checks passed 1,669 scanner tests (18 intentional skips) and 1,449 frontend tests; package/generated checks passed. A final merged-order test then failed and passed after its fix; the checkpoint gate reruns the complete suites.
- Activation is intentionally deferred until the new authority seal, persisted evidence and historical reconstruction are implemented together. This remains local, undeployed work, not full-blueprint completion.

### Third implementation slice: versioned authority and persisted readers

- Activated the published-route producer together with the new internal authority seal; public V6 routes remain unchanged. Persisted count/family columns and version/completeness metadata in existing `raw_finding` are authenticated. No entity migration was needed.
- Actual Python-produced canonical repairs pass writer, persisted readback, customer and chat signature reconstruction with three distinct route URLs and counts. The integration tests exposed and fixed dropped chat child groups and missing priority identity/count fields.
- Historical GEO rows retain their captured, literal HMAC and preview proof even when new markers are injected. New-route, escape, count, partition and version tampering is rejected. The new unpaid request path preserves the two-fix preview without loading hidden findings.
- The latest full pre-checkpoint gate passed **1,672 scanner tests, 18 intentional skips, 718 dependency warnings; 1,459 frontend tests, zero failures/skips**, plus package closure and generated-contract checks. Two subsequent regressions exposed mutable customer status in chat reconstruction and unknown-seal fallback in persisted writing; both failed before their fixes and then passed in a 32-test authority/historical set. The checkpoint gate reruns the complete suites.
- Pinned `ada-url==1.32.0` installed from official PyPI wheels and executed all **73 identity/legacy checks** on both Linux arm64 and Linux amd64 (the latter under Docker emulation). Tests used read-only source, disabled networking and no credentials. The amd64 official Python 3.12-slim manifest was `sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9`.
- Candidate fingerprint `5fb87bf7869c51c2` is explicitly marked candidate, not frozen/accepted or deployed; prior fingerprint `47793ce37ca20523` remains supported for historical reading. Export-path verification and independent review remain open, as do the other blueprint requirements and deployment.

## Work-agent stage-one candidate (2026-09-19)

Recovered exact checkpoint `a51fa796` from GitHub, preserving Tasks 1–3. Implemented Task 4 through actual rendered consumers and serializers, then integrated B03/B04/B05 and the named synthetic acceptance runner. Details and explicit remaining gates: `docs/stage-one-evidence-acceptance.md`.

Fresh full verification: 1,767 scanner tests passed (18 intentional skips), 1,479 frontend tests passed, root Python gate/lint/typecheck/build/package/generated/freeze checks passed. Candidate fingerprint `01ebe8e90df1e6bd` remains unaccepted. Independent review subsequently found four Important issues, now corrected with reproducing tests. Final source gate: 1,798 scanner tests passed (18 intentional skips), 1,479 frontend tests passed, all source checks green. Exact-source CI, merge and production verification are next. No full-blueprint or real 30-site acceptance is claimed.


## Stage 2 coverage checkpoint — B06 source-complete on PR #303 (2026-09-19)

Stage 2 is isolated from the Stage-1 release line on branch `agent/full-blueprint-stage2-coverage-b06-20260919`, draft PR [#303](https://github.com/bright4862-design/seo-autopilot/pull/303). GitHub `main` remained at the merged Stage-1 source `22ce4e69aa915a2e5ba796f9432fea33a0fa79bb` throughout this checkpoint, so this work has **not** moved the exact-SHA cutover underneath the pending Stage-1 production promotion.

Requirement status:

- **B06 — source-complete and CI-verified on the branch; not merged/deployed/live.** Added one shared bounded coverage-probe scheduler, then used it to status-check same-site internal-link targets that fall outside the assessed-page sample. Probe pages never enter the assessed-page count. Actual request identities are reused, redirect hops use the same safe request provider, and the pool is bounded by both a small per-mode allowance and the crawler's existing finite `max_pages * 8` request ceiling.
- The scheduler exposes eligible/attempted/completed/pass/fail/not-verified/skipped/exhausted counts and a bounded evidence sample. Exhaustion/deadline/robots/access challenge states remain unknown/not-verified rather than becoming a pass. Probe time receives its own subdeadline so additive coverage cannot starve the existing canonical validator.
- A verified unsampled 404/410 becomes the existing authenticated broken-link repair with retained source page/link text. It is explicitly non-scoring until B19/B23 land. The review coverage context counts a confirmed versioned probe URL as `affected_observed` but never as `affected_eligible`, preventing an invented denominator. Unknown versions and unverified probe claims cannot inflate the signed count.
- The behavioral regression uses the real Python producer → review → canonical authority → persisted rows → verified customer/chat/card/handoff/export helper. It proves a broken target beyond a 4-page assessed sample is requested, remains outside `pages`, persists as one signed repair, and reloads with truthful `affected_observed=1`, `affected_eligible=0`.
- Exact code checkpoint `d88b5b89a870b9f502f46da654eab9c831945c40` passed FixList CI run **35450285277**: **1,806 scanner tests passed, 18 intentional skips**, **1,479 frontend tests passed**, lint/typecheck/generated-contract checks, labelled Stage-1 corpus verification, frozen revision check, frontend build and production scanner-image build all passed.
- Two preceding CI failures were retained as useful evidence rather than hidden: the first caught a direct-404 classification mistake; the second proved that the repair reached the signed customer row while `affected_observed` was still zero. Both causes were fixed with reproducing regressions before the green run.

**Open Stage 2:** B07–B18. The next dependency-owned slice is B07 active soft-404 baselines using this same scheduler; B09 sitemap integrity and B16 URL variants must reuse the same pool rather than create new request budgets. B08 reuses retained redirect evidence. B10–B15/B17–B18 remain unimplemented here.

**Stages 3–4:** B19–B28 remain open. No Stage-2 code is merged, staged, deployed or live-accepted by this checkpoint. The genuine provenance-labelled 30-site baseline/candidate gate remains open and historical summary counts are still not substitute evidence.
