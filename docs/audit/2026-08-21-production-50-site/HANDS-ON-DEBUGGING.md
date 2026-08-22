# Hands-on debugging follow-up

Date: 2026-08-21 (Europe/Paris)

Baseline: PR #152 merge commit
`1eb20072095dd182fb41e276e57050eee071bd50`.

This note follows the 50-site production audit. Production and the scan queue
were not modified during debugging. One bounded experimental source patch is
implemented for the admission-sweep defect; it has not been committed, pushed,
or deployed and is not merge-ready.

## 1. Admission reconciliation - root cause proven, experimental prototype

Production Base44 logs contained hundreds of repeated terminal-release errors.
The admission coordinator is correctly protecting the current scan generation.
The five-minute reconciliation sweep is attempting to release historical
terminal scans after the owner's single coordinator document has moved to a
newer scan.

Deterministic lifecycle:

1. Scan A binds and releases normally.
2. Scan B claims the same owner's slot.
3. Retrying A before B binds returns `scan_not_bound`.
4. Retrying A after B binds returns `scan_identity_conflict`.
5. The current sweep treats both safe stale outcomes as errors, returns
   `success:false`, and causes `/scan-reconcile` to retry with 503.

Safe change boundary:

- read and cache the current coordinator status per owner;
- release only when the exact terminal ScanRun is still bound;
- treat released, unbound-new-generation, and other-scan generations as
  satisfied/skipped;
- preserve the coordinator's fencing and keep status-unavailable outcomes
  retryable;
- re-read status after a release race before suppressing a conflict.

Fresh baseline and patch checks:

- original reconciliation contract: 8/8 passed, demonstrating the missing
  cross-generation case;
- focused patched reconciliation suite: 16/16 passed;
- combined admission/reconciliation suites: 46/46 passed;
- complete frontend contract suite: 636/636 passed;
- admission coordinator state-machine suite: 32/32 passed;
- modified JavaScript lint, project typecheck, and diff validation passed.

The HTTP coordinator suite could not start because Flask is unavailable in the
local environment. The patch does not modify coordinator code.

Independent review found two release-blocking gaps despite the green focused
tests:

- a bound terminal lease is skipped permanently after the two-hour lookback,
  while coordinator-bound leases intentionally do not expire;
- the owner-wide status cache can reuse an inactive/synthetic observation for a
  different same-owner candidate after the coordinator generation changes.

The current top-50-per-status query can also hide an older unresolved lease.
The production-safe patch therefore needs durable release satisfaction,
pagination/rotation of all unresolved terminal rows, recovery after outages
longer than two hours, candidate-specific status refresh, and full sweep
integration tests. The existing four-file diff is reference material only.

## 2. Under-coverage authority - root cause proven, cross-boundary design needed

Production examples:

- Tanners: 38/3,689, complete, non-provisional, release eligible.
- Decathlon: 40/1,374, complete, non-provisional, release eligible.
- Habito: 1/1 on a real multi-page site, complete, non-provisional, release
  eligible.

The current severe rule only rejects large inventories when fewer than 20
pages are received. The evidence-quality gate treats any sample of at least
seven usable pages as representative without checking whether the crawl
materially missed its target.

The one-page path has a separate defect: queue exhaustion plus zero page-fetch
failures is treated as positive inventory proof even when sitemap discovery
failed. A sitemap 404 and an empty DOM frontier can masquerade as a proven
one-page site.

Fresh full local-review reproduction at PR #152:

```text
38 / 3689  -> complete, provisional=false, release_gate_eligible=true
40 / 1374  -> complete, provisional=false, release_gate_eligible=true
false 1/1  -> complete, small_site_supported, release_gate_eligible=true
```

Do not patch this by changing `20` to a different magic number alone. A valid
Standard 150 scan can be 150/5,000. The durable contract needs a versioned,
scanner-owned target/attempted/retained/terminal-reason assessment, plus
positive one-page inventory proof.

Important lifecycle boundary: a Python-only provisional gate currently becomes
a generic failed ScanRun. A truthful customer result needs a separate limited
integrity path:

- `status=limited`;
- provisional score and release gate false;
- useful FixItems persisted as non-authoritative;
- a distinct integrity proof, not the authoritative release seal;
- customer result retrieval for integrity-verified limited results.

The signed snapshot must also retain crawl timing, sampling evidence,
discovery state, representative/usable/default-route counts, and the gate
version. Those fields exist in the ScanRun schema but are currently dropped.

## 3. Impossible repair denominators - two root causes proven

Live examples include:

- Wecandoo orphan group: 126 affected / 1 eligible Homepage.
- Airbnb orphan group: 126/1.
- Decathlon orphan group: 37/1.
- Castorama orphan group: 79/1.
- Pretto redirect evidence: 35/30.
- Meilleurtaux access evidence: 47/6; failed-page evidence: 22/6.

Root cause A: an aggregate navigation finding calls the generic finding
constructor with an empty URL. The generic constructor classifies the empty
path as `homepage`, so the mixed group is born with the wrong family. Scoring
then preserves that family and defaults the multi-page finding to family scope.

Root cause B: repair priority counts every affected URL in the numerator but
derives the denominator from usable HTML pages in one family. The URL domains
are not intersected. Access and failed pages are especially vulnerable because
they are intentionally absent from the usable-HTML denominator.

Direct local reproduction produced coverage values 4.0 and 1.167.

Release-safe boundary:

- stamp mixed navigation aggregates as `mixed`/`cross_cutting` and preserve
  per-family partitions;
- use the same rule-eligible URL set for numerator and denominator;
- do not infer a usable-HTML denominator for access/failure/cross-cutting
  evidence unless the detector supplies an exact eligible universe;
- reject `affected > eligible`, `indexable_affected > indexable_eligible`, or
  ratios outside `[0,1]` in Python and Base44 authority validation;
- invariant failure must fail the release gate, not silently fall back to the
  legacy repair contract;
- persist page count and family partition evidence.

## Recommended implementation order

1. Finish and independently review the bounded admission-sweep patch.
2. Implement denominator invariants and mixed-family persistence as one
   release-contract patch.
3. Design the coverage assessment and limited-result integrity contract before
   changing coverage thresholds.
4. Only then rerun the focused production controls; do not start another broad
   matrix while these authority defects remain open.
