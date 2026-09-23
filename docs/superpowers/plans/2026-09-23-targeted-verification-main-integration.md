# Targeted verification integration checkpoint — 2026-09-23

## Scope and status

The eight pure targeted-verification modules and their tests from Lane E
`ad1ae90d54aac6bd908536f4c0684de6ccf3b750` are reconciled with main
`99e74965775f731c120e185b0e26d11f150c084f`. Main already contains the source-type
hardening from PR #351. This checkpoint changes no shared identity code, protected
fetch code, scheduler, worker, authority, persistence, V8 reader or customer UI.

This is an integrated deterministic foundation, **not an enabled customer verification
feature**. Production execution and signed persistence remain required. Historical
provisional identities remain `COULD_NOT_VERIFY`; do not reconstruct their missing
technical identity from titles, roles, URLs or matching fingerprints.

The earlier Lane-E handoffs describe the incremental modules. This checkpoint
supersedes their integration recommendation: any service integration must use
`evaluate_rule_execution_bound_targeted_fix_verification_service`, the strongest
boundary, with its v2 receipt and trusted execution window. Do not wire a lower
adapter directly to customer actions.

## Defects resolved while integrating

- Two claimed observations previously passed with zero requests or reuse; arbitrary
  reuse totals also passed. Positive observations now require one accounted fetch
  or reuse per URL, with no accounting beyond the bounded plan. Explicit denied or
  unverified attempts can spend no request, but cannot contribute positive evidence.
- Claimed observation states must match scheduler terminal counters exactly.
- MIME evidence uses exact supported HTML media types, including normal parameters;
  strings such as `application/nothtml` cannot satisfy the HTML gate.
- Malformed scheduler flags, scheduler states and originating-rule states fail
  closed instead of raising unhashable-type exceptions.
- Legacy execution receipts had no freshness bound. The strongest v2 boundary
  requires one explicit execution window and rejects stale or mixed execution data.

The canonical comparator remains the only repair truth engine. No thresholds,
request budgets, URL scope or PASS conditions were relaxed.

## Fresh execution contract

The protected service supplies a closed `execution_window` object with:

- `version = targeted_fix_verification_execution_window_v1_server_owned`
- `execution_id`: server-generated identifier for this verification execution
- `plan_fingerprint`: the exact complete bounded plan
- `started_at_ms` and `expires_at_ms`: exact positive integer epoch milliseconds

The service also supplies its own `expected_execution_id` and `evaluation_time_ms`.
Every protected observation carries the same `execution_id` and its actual
`observed_at_ms`. The rule receipt binds the whole window and the full observation
population. Evaluation requires `started_at_ms <= observed_at_ms <= evaluation_time_ms
< expires_at_ms`. The window duration cannot exceed the existing scheduler's bounded
time budget. The real scheduler's remaining deadline is still authoritative and
must never be extended to match a new window.

Missing windows, legacy receipts, invalid clocks, expired windows, future
observations, foreign execution IDs and plan substitutions all produce
`COULD_NOT_VERIFY`. Existing PASS/PARTIAL/FAIL behavior remains available only for
complete, fresh, exact originating-rule observations and canonical comparison.

These hashes and timestamps establish internal consistency only. They are not an
authority seal, an authentication mechanism or an execution permit. Never accept
expected execution IDs, trusted times, page observations or rule receipts from a
customer request body. A persisted historical result is a signed as-of observation;
replaying its evidence later must not create a new successful verification.

## Smallest safe protected path still required

The serialized integrator owns these shared steps:

1. Authenticate the scan owner, enforce the existing entitlement and admission/rate
   policy, and read the selected historical repair through the current authority
   reader. Require a stable technical identity and the complete sealed URL scope.
2. Capture the existing `SharedCoverageProbeScheduler` snapshot and prepare the
   exact plan. A repair exceeding the current 18-URL targeted bound cannot be
   silently truncated. Persist or otherwise hold an authenticated execution ID,
   exact plan and deadline before network work; reserve no new independent pool.
3. Fetch only the plan population through `scanner.fetch_and_extract` with the existing
   robots policy and `request_provider=scheduler.fetch_once`, following the existing
   protected orchestration pattern. Preserve DNS/IP pinning, SSRF, redirect, body
   and monotonic deadline protections. A cache reuse needs actual fresh evidence
   from the same execution, not a new timestamp attached to older observations.
4. Re-run the exact originating deterministic rule/version and comparison profile
   on each observed page. Reuse its existing producer; do not infer “fixed” from an
   empty findings array. Where a rule cannot be rerun under its exact original
   evidence contract, return `COULD_NOT_VERIFY`.
5. Capture postflight scheduler accounting and create the originating-rule results
   and v2 receipt inside that trusted producer. Evaluate through the strongest
   service boundary while the execution window is valid.
6. Persist an append-only, signed verification result binding owner/source scan,
   exact repair, execution, versions, window, page evidence and canonical outcomes.
   Do not overwrite sealed historical repairs. Validate the signature and owner
   again on V8 reload; regression reopening requires canonical `came_back` evidence.
7. Add a small customer verification action/status only after protected execution,
   authority, persistence and reload are tested together. Keep detailed diagnostics
   optional. Preserve all four states, including explicit `COULD_NOT_VERIFY`.

No production probes or runtime AI calls were made by this work.

## Verification evidence

The imported baseline had 165 passing targeted tests. Fresh regressions reproduced
false PASS for missing freshness and zero accounting before the corrections.

Final combined focused command:

```sh
python -m pytest -q scanner-api/tests/test_targeted_fix_verification*.py scanner-api/tests/test_repair_identity*.py scanner-api/tests/test_coverage_probes.py
```

Result: **284 passed**. This covers the deterministic core, adversarial transport,
exact scope/versions, scheduler accounting, expiry/replay, provisional identity,
canonical PASS/PARTIAL/FAIL and no mutation of historical repair evidence. It does
not demonstrate a production endpoint, protected I/O execution or signed reload.

Independent read-only review reproduced closure of the reported defects and ran
128 affected tests successfully; no blocking finding remained.
