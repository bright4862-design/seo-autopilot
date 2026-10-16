# Stage 2 B08 redirect-meaning lane handoff — 2026-09-19

This lane was cut from Stage-2 PR #303 head `b05fe3993422357959c7755a2eda47a2e635943f` on branch `agent/stage2-b08-redirect-meaning-20260919`. Draft PR #309 is CI/review plumbing only and must not be merged directly to `main`; the Stage-2 integration owner should transplant this lane into `agent/full-blueprint-stage2-coverage-b06-20260919` after checking overlap with the other active lanes.

## Implemented behavior

B08 now retains the existing bounded redirect hop/status/canonical/noindex evidence and adds conservative destination-meaning evidence under `redirect_fetch_evidence.meaning_evidence`, versioned as `redirect_meaning_v1_semantic_destination_fit` without changing the frozen `REDIRECT_EVIDENCE_VERSION` or historical reconstruction contract.

The classifier distinguishes:

- harmless trailing-slash normalization;
- explicit home intent legitimately reaching the homepage;
- a semantically related same-site hub, using bounded source-path/link-text versus destination path/title/H1/meta terms;
- a verified specific source collapsing to an unrelated generic destination such as `/blog/` despite HTTP 200;
- a specific source collapsing to the homepage without explicit home intent;
- verified unusable final destinations (HTTP errors, loop/invalid/missing-location states, non-HTML or empty/incomplete HTML);
- access challenges, robots-blocked destinations, transport failures and chain-limit cases as not verified rather than fabricated failures.

A verified unrelated 200 destination produces the existing `redirect_wrong_destination` repair. B08 does not turn redirect evidence into missing-H1/meta/image/internal-link findings and does not alter redirect fetch, SSRF, robots, body-size, redirect-hop or deadline boundaries.

## Test-first evidence

RED commit `9176edf1a908d1d631aeaa58f8e327531f390c50` added five behavioral tests before production implementation. FixList CI run `35461877247` failed exactly those five new B08 cases while 1,820 scanner-api tests passed and 18 intentional skips remained. The frontend/lint/typecheck/build job passed.

Implementation commit `b8dc56d013395814165857e08cdb95859a8221bb` added the first meaning classifier. CI `35461949114` proved the five new B08 cases passed and exposed four compatibility regressions in the pre-existing redirect contract. Commit `d06b924ec3532e6b22301ba97d90adb9cc850d6f` corrected those compatibility regressions by preserving the prior specific-route-to-homepage fail-closed rule, HTTP 4xx/5xx unusable classification and noindex/canonical destination precedence.

Commit `42ec67043e5a32f0e66f0ca5714f7f1e90e5cf38` added the real finding -> review -> signed authority -> persisted rows -> verified customer/Grok -> card/handoff/PDF/TXT/CSV/rendered-output regression for the new `redirect_wrong_destination` classification. CI `35462196936` then exposed one test-denominator mistake: the redirect source is authenticated observed evidence but is not an eligible assessed content page, so `affected_eligible` truthfully remains zero.

Commit `e2686cfc3b68ea6d62ed7c5597280866ffe839ef` corrected that expectation and added an explicit empty/incomplete HTML destination regression.

## Exact code/test verification

FixList CI run `35462354646` passed on exact code/test head `e2686cfc3b68ea6d62ed7c5597280866ffe839ef`:

- root scanner tests: **115 passed**;
- scanner-api: **1,826 passed / 18 intentional skips**;
- B08 focused redirect-meaning tests: **6 passed**;
- existing `test_redirect_classification_contract.py`: passed;
- existing `test_redirect_evidence.py`: passed;
- labelled Stage-1 synthetic corpus: passed and still reports `full_30_site_gate=not_assessed`;
- frozen beta revision check: passed;
- production scanner image build: passed;
- lint, typecheck, generated release contracts, frontend contracts and production frontend build: passed.

Existing redirect suites cover `/page -> /page/` normalization, final 404/5xx, timeout, loop and robots-blocked destination behavior. The B08 lane adds unrelated 200 destination, legitimate related hub/home intent, access challenge, non-HTML and empty/incomplete HTML cases, plus authenticated customer-output verification.

## Required serialized integration hook

Do **not** mechanically merge the lane PR to `main`.

`scanner-api/app/scanner.py` is concurrently owned by the B07 producer/provenance lane. Its existing customer copy for `redirect_wrong_destination` still says the URL was redirected to “the site homepage.” B08 can now verify an unrelated one-level catch-all section such as `/blog/` too. During serialized Stage-2 integration, update that customer-facing copy to describe an **unrelated or catch-all destination** (using the retained redirect evidence) and add a focused wording regression. Do this only after re-reading the B07-integrated `scanner.py`; do not overwrite B07 changes.

After that wording integration, run the combined focused redirect tests and exact-head Stage-2 CI before marking B08 source-complete on PR #303.

## Release state

This lane is committed and CI-verified only. It has not been merged to Stage-2 PR #303 or `main`, staged, deployed or live-accepted. No production infrastructure, admission state, queue, worker traffic, Base44 publication or historical row was changed by this lane.
