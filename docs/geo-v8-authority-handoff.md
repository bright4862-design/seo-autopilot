# GEO V8 authority-sealing handoff — integrator only

Date: 2026-09-23
Lane: `agent/ai-geo-readiness-20260923`
Candidate: `geo_readiness_v2_candidate`
Authority state in this lane: `authority_verified=false`

## Boundary

Lane C does not edit shared authority, persistence, customer projection, generated release contracts, admission, workers, deployment, or production. This document is the precise handoff for the serialized integrator. It is not permission to deploy.

The GEO block must not become customer-authoritative merely because a field exists in a scan result. Authority requires inclusion in the authenticated V8 snapshot and verification through persistence, reload, and customer projection.

## Candidate inputs

The integrator may construct the candidate only from already-accepted retained evidence that passed the existing page evidence gate and from exact retained policy/discovery observations. Unknown stays unknown. Access-limited scans suppress content diagnostics. No provider visibility API, model call, extra crawl, robots impersonation, or `llms.txt` fetch is implied by this handoff.

Optional sidecars currently available in Lane C:

- `geo_named_robots_evidence_v1`: exact named-crawler policy observations only where retained directives are known; not scored in v2 candidate.
- `geo_llms_txt_evidence_v1`: structural normalization for an already-retained `llms.txt` observation; no current Standard 150 observation source is approved by this lane, and absence is neutral.

Do not synthesize either sidecar when its observation is unavailable.

## Required serialized integration sequence

1. **Compute server-side from trusted retained evidence.** Build `geo_readiness_v2_candidate` after the existing accepted-evidence and access-limited gates. Do not accept a client-supplied candidate.
2. **Compatibility-check v1.** For the same page/check matrix and gates, require equality for assessment status, numeric/null score, coverage, score bounds, dimensions/check counts, reasons, sample size, and authority=false before sealing.
3. **Version the authenticated payload.** Add the GEO candidate under a new compatible V8 snapshot revision or equivalent repository-approved authority version. Update every active producer, verifier, reconstruction path, and generated contract together. Do not append an unsigned/unsealed field beside the authority payload.
4. **Persist the sealed candidate, not a recomputation recipe.** Historical snapshots remain byte/semantic compatible and are never rescored on read. Historical scans without the new field project a neutral `not_assessed`/legacy state.
5. **Verify tamper rejection.** Mutating score, coverage, observation scope digest, dimension summaries, unknown cells, version, reasons, or evidence references inside the authenticated GEO block must fail the existing authority verification path.
6. **Verify reload/history.** A newly sealed scan must return the identical authorized GEO block after persistence/reload/history traversal. Missing or malformed candidate data must fail closed; do not coerce null score to zero.
7. **Apply existing entitlement/projection policy.** Customer projection may expose only the approved summary/findings surface. Full evidence/unknown-cell detail must not bypass the current full-access/free-preview boundary. No new repair priority or customer score is introduced by this lane.
8. **Only then set authority state.** `authority_verified=true` may be projected only after the V8 authority verifier has authenticated the exact snapshot containing that GEO block and the end-to-end equality checks pass. The evaluator itself must continue returning false.

## Required compatibility regressions

- Old V8 snapshot without GEO v2 verifies unchanged and projects neutral legacy/not-assessed GEO state.
- New snapshot with v2 candidate verifies, persists, reloads, and projects the same approved summary.
- Tampered v2 score, coverage, unknown-cell list/count, observation-scope digest, dimensions, reasons, or version fails authority verification.
- Access-limited candidate remains score null and does not surface page-content diagnostics after sealing/projection.
- All-unknown and all-not-applicable matrices remain score null.
- Exact 80% overall and 50% per-dimension boundaries remain identical to v1.
- Funbooker-like non-article pages can carry deterministic N/A support applicability without lowering gates; unresolved entity/support cells remain unknown.
- Named-crawler policy and `llms.txt` sidecars, if eventually sealed, cannot independently change the v1-compatible numeric score without a separately approved ruleset/version.
- Customer claim-boundary lint remains green for every GEO label/help/summary string changed by integration.

## Production acceptance evidence required before authority=true

A staged or production-acceptance rerun must provide the immutable scan ID/release identity, sealed snapshot version, GEO candidate version, adapter version, authority digest/verification result, assessment status, score/null state, overall coverage, per-dimension coverage/scores, unknown-cell count, and a post-reload equality check. The exact payload should be retained in an approved evidence artifact so a future lane run can refresh it instead of relying on chat-reported values.

For the currently reported Funbooker baseline, do not lower the score gates. If Entity or Support remain below their evidence thresholds after the adapter improvements, the correct result is still `insufficient_evidence` with `score=null`.

## Claim boundary

Authority sealing proves FixList result integrity only. It does not prove that any AI/search provider fetched, indexed, cited, ranked, included, displayed, or sent traffic to the assessed pages. Do not use authority verification as an AI-visibility claim.
