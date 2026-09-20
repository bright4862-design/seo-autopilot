# Stage 2 follow-up review hardening

Authoritative design: `docs/superpowers/specs/2026-09-19-full-scanner-blueprint-design.md`.

Scope: final serialized B06–B18 hardening on PR #303 after fresh independent review. This record does not authorize production publication, admission mutation, worker promotion, live scans, schema/secrets changes, or Stage-3 integration.

## First follow-up review: direct authority privacy + future provider time

The first fresh CodeRabbit follow-up review reported two material P1 defects:

1. direct calls to `build_authority_review_payload`, `build_completion_envelope`, and `build_limited_envelope` could bypass the normal post-crawl projection and re-sign private B10/B11/B13/B15 evidence;
2. optional CrUX/GSC staleness checks did not reject `observed_at > as_of`.

### RED

`bea5d3d8a1ec5d7f77d7f68ca4919a45226ded42` added three behavioral regressions. FixList CI `35498446283` failed as intended: root **115 passed**; `scanner-api` **3 failed / 1,990 passed / 18 skipped**; the three new regressions were the failures; the build-side job passed.

### Corrections

- `12d6c7a24b68a681cd9a5d1a0b78a996ae23edaa`: CrUX/GSC adapters fail closed on future observation time with `provider_observation_time_invalid`.
- `0e5a0ed176d764a9ac78bc2d96833f46a268911d`: connected provider envelopes preserve the normalized invalid-time reason.
- `10798d00d1c0e7cc31a6dfaca3cd4fc67abeb354`: all direct authority/signing helpers defensively project before sampling/signing/persistence-envelope construction.

Intermediate CI `35499222707` on `10798d00...` proved the new review regressions green but exposed one stale compatibility assertion: root **115 passed**, `scanner-api` **1 failed / 1,992 passed / 18 skipped**, build-side job green.

`f8175c496728d806085056a2b79cb42e5a0fc61c` strengthened that B13/B14 authority test instead of weakening it. Signed authority must retain approved version/count/state/NAP diagnostics while excluding exact entity IDs, page URLs, `entity_key`, `page_url` and contextual-status provenance.

FixList CI `35499312736` on `f8175c496728d806085056a2b79cb42e5a0fc61c` passed both jobs: root **115 passed**, full `scanner-api` **1,993 passed / 18 skipped**, synthetic corpus/frozen revision/image build/lint/typecheck/contracts/frontend build all passed.

## Second re-review: unknown future page fields were still fail-open

A fresh CodeRabbit re-review of stable head `464d3a84726887a32bf19ad3b372d6a5ac5498cd` found one remaining material P1 privacy/authority issue.

`project_page_for_external_boundary` copied every page field except names in a known deny-list. That protected the currently known private B10/B11/B13/B15 fields but failed open for any future producer/debug field. Such a field could cross page arrays and, because direct authority/signing helpers correctly call the projector, be signed/persisted there as well simply because its name had not yet been classified.

### RED

`e51b62220c926c671c0906b441de62dcaf9c7b53` — `test(stage2): reproduce future private page leak` — strengthened the existing direct-helper privacy fixture with an intentionally unknown `future_private_detail` sentinel and required it to be absent from the authority-review, completion-envelope and limited-envelope paths.

The commit added **no new test function**; it changed the shared fixture/assertion used by the existing three direct-helper privacy regressions.

FixList CI `35499676118` failed as intended, proving the pre-fix external projection leaked the unknown sentinel.

### Correction

`fda2ab346fa102fe2a7d02f116b1cd6e1fa92eaf` — `fix(stage2): fail closed page output projection` — changes per-page external projection from deny-list copying to a **positive external field allowlist**.

The allowlist deliberately classifies the currently approved external page contract:

- route/request identity and bounded crawl provenance;
- search metadata and approved Stage-1 content evidence;
- scalar B17 page-weight evidence;
- robots/canonical/redirect/indexability/navigation diagnostics;
- bounded access-block evidence;
- B11 sample-scoped reachability diagnostics;
- authenticated GEO compatibility fields;
- bounded client-rendering diagnostics.

Unknown future page fields are now denied by default. B10 main-content fingerprints, raw B13/B14 identity/contact observations, B15 per-page freshness evidence and the B11 private retained-link cache remain excluded. A future field must be deliberately reviewed and added before it can become part of the signed/customer/persisted contract.

### Exact executable GREEN checkpoint

Exact executable head: `fda2ab346fa102fe2a7d02f116b1cd6e1fa92eaf`.

FixList CI `35500366163` — **SUCCESS** on both jobs:

- immutable checkout passed;
- root scanner regression gate passed (same 115-test gate as the preceding certified checkpoint);
- full `scanner-api` passed; the suite remains **1,993 passed / 18 intentional skips** because the RED commit strengthened existing fixture coverage rather than adding test functions;
- the three direct-helper privacy paths now reject the unknown future sentinel;
- labelled Stage-1 synthetic corpus passed with `full_30_site_gate=not_assessed` unchanged;
- frozen scanner revision `01ebe8e90df1e6bd` passed;
- production scanner image build passed;
- lint, typecheck, generated release contracts, frontend contract tests and production frontend build passed.

GitHub Actions requested Node 20 but resolved Node 20.20.2. Do not describe this run as Node 20.19.5 evidence.

## Remaining Stage-2 gate

The latest material re-review finding now has RED reproduction, a narrow source correction, strengthened behavioral coverage and exact executable green CI. Stage 2 remains **not recorded complete** until:

1. the final persisted documentation head receives exact-head FixList CI;
2. one fresh independent review of that stable corrected head reports no unresolved material finding.

If a new material issue appears, reproduce it first, apply the smallest safe correction, and require fresh exact-head CI. If the review is clean, record B06–B18 complete and begin serialized integration of the existing B19/B20 and B21–B24 Stage-3 lanes.

Keep internal B09/B10–B18 data internal unless a deliberate producer → Review → signed authority → persisted rows → customer/card/handoff/export contract is added. Preserve Standard 150, one finite request budget, robots/DNS/SSRF/redirect/body/deadline controls, exact scan isolation, one active scan/account, cancellation/terminalization, historical readers/signatures, preview privacy and Python Review authority.
