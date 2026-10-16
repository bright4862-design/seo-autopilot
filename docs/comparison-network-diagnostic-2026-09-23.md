# Live comparison transport checkpoint — 2026-09-23

The owner supplied a new Funbooker result: 141 checked pages, score 72, seven
repairs, and `CMP-NETWORK`. This comparison is still unavailable; this change is
diagnostic instrumentation, not a claim that the production defect is fixed.

The V8 code emits that reference only after both reader-side authority checks,
ownership, scope and seal ordering pass, while the gateway fetch has not yet
returned an HTTP response. The local deadline has its own `CMP-TIMEOUT` code.
This narrows this attempt; it does not establish the cause of older failures.

Read-only Cloud Run diagnostic job `107341013417` in run `35860744807` succeeded.
Its final comparison request metadata section at 19:16:46 UTC contained no rows
for the preceding eight hours. The gateway `/health` still reported source
`a9a96faf24ee9a841720981dcfbcee7bf0967a84`. These observations do not prove whether
DNS, the configured destination, TLS, a proxy or a platform restriction failed.
Captured earlier request pairs exceed 2 MiB, but no documented Base44 outbound
limit has been established. Do not change limits or trim sealed snapshots on
that hypothesis alone.

## Diagnostic release

The V8 reader writes one private `scan_comparison_transport_failure_v1` record
per failed gateway attempt. It contains a fixed support reference and error
category, request byte count, elapsed time, local-abort flag, HTTP status,
normalized origin fingerprint, function build ID and runtime activation marker.
It never records exception text, bodies, proofs, signatures, customer identifiers
or raw URLs. Logging failures cannot change comparison behavior.

Redirects remain prohibited. Manual redirect handling records a fixed
`CMP-GATEWAY-REDIRECT` reference without following or reading `Location`.
The expected origin fingerprint for the current gateway is `331c376c537c3e34`.
A mismatch means the reader is configured for a different normalized origin;
a match alone does not establish reachability.

After publishing the exact reviewed source, reopen an existing saved result.
No new crawl is required. Correlate the private failure record with gateway
request metadata. Current Base44 CLI logs default to preview, so specify:

```sh
npx base44 logs --app-id 6a498732ec779dfaaeab0e53 --function getCustomerScanResultV8 --env prod --since 1h --limit 100 --json
```

Publication still uses the existing owner-authorized Base44 workflow. This
change neither replaces baseline lineage nor enables verified Fixed claims.
Stable producer identities and authenticated page/rule outcomes remain a
separate comparison milestone. PR #359 remains held; chat/model calls remain off.
