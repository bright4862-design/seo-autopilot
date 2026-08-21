# Source trace for production audit findings

Repository baseline: PR #152 merge commit
`1eb20072095dd182fb41e276e57050eee071bd50`.

## Mixed-family findings are born as Homepage and use an incompatible denominator

- `scanner-api/app/navigation_indexability.py:164-197,201-230` creates one
  `potential_orphan_pages` finding containing URLs from every page family. It
  calls the generic finding constructor with an empty `page_url` and replaces
  the affected list without replacing family or scope.
- `scanner-api/app/scanner.py:1175-1199` stamps every generic finding with
  `page_template_family=classify_template(page_url)`, while
  `scanner-api/app/extract.py:442-453` classifies an empty URL as `homepage`.
  The aggregate orphan finding is therefore born with the wrong family.
- `scanner-api/app/review.py:1850-1858` selects the representative before
  `score_fix()` runs. At `review.py:1958-1959`, scoring defaults a multi-page
  finding to family scope and preserves the already-present Homepage family.
- `scanner-api/app/repair_priority.py:238-284` counts every affected URL in
  the numerator, but builds the denominator from usable HTML pages in the
  finding family. It does not intersect the numerator with that eligible set.
  This allows values such as 126 affected URLs divided by one homepage and
  customer copy such as "126 of 1 searchable homepage pages."
- The denominator-domain defect is broader than orphan findings. Production
  also persisted Pretto 35/30, Meilleurtaux access evidence 47/6, and
  Meilleurtaux failed-page evidence 22/6. Failure/access URLs are excluded
  from the usable-HTML denominator even while remaining in the numerator.
- `base44/functions/persistDurableScanAuthority/authoritySnapshot.js:246-311`
  retains the bad priority context but drops schema-supported `page_count`,
  `family_breakdown`, and `representative_pages_by_family`, leaving the
  durable evidence impossible to explain.

Production examples: Wecandoo `6a8881947fb057d255e2a8d0`, Smartbox
`6a88827a264c554d19a18c08`, Funbooker
`6a88832528f4e86d8614d430`, Airbnb
`6a8883c17ecc3561c6554f6d`, BBR
`6a888557e397a535d0aaa818`, Naked Wines
`6a8886c4b4f506e7ac518a46`, Vinatis
`6a8887d18c5a2dc2732c852c`, Millesima
`6a88884e47cea59803439374`, and others.

## "Should be handled first" uses a different priority model than the UI bands

- `src/pages/FixList.jsx:1702-1714` counts raw scanner `priority` values
  (`critical` and `high`).
- The displayed Fix first / Important / Improve / Review bands use
  `action_priority`.

This produces customer-visible contradictions, including Tanners (five said
to be handled first, but every actionable card is in Improve) and PayFit (two
said to be handled first, but the rendered bands contain one Fix first and
three Important cards).

## Durable timestamps and evidence counters are not truthful

- `base44/functions/persistDurableScanAuthority/index.ts:67-75,363-368`
  deliberately derives a stable authority-seal timestamp from `started_at`.
- `base44/functions/persistDurableScanAuthority/authoritySnapshot.js:118-139`
  writes that stable value into `scan.completed_at`.
- The staged `reviewing` write in
  `base44/functions/persistDurableScanAuthority/index.ts:120-130` does not
  set `reviewing_at`.
- `src/lib/scanRunModel.js:160-244` also sources `completed_at` from
  `record.created_at`.

Every successful production ScanRun inspected so far has
`completed_at == started_at`, `reviewing_at == null`,
`representative_html_page_count == 0`, and
`usable_html_page_count == 0` while simultaneously claiming evidence quality
100 with reason `representative_html_evidence`.

## Failure and stalled-run copy discards useful durable state

- `src/pages/FixList.jsx:1620-1637` maps every active state to the same "still
  running" copy and every failure to the same generic interruption copy.
- The durable ScanRun often contains actionable `status_detail`, such as a
  rate-limit/challenge explanation, which is not presented to the customer.
- `base44/functions/durableScanWorkerControl/reconciliation.js:1-15,50-85`
  waits 15 minutes after the last heartbeat (or 35 minutes after start) before
  closing a vanished worker. The customer UI does not identify the stale
  heartbeat while waiting.

## Severe under-coverage threshold misses materially thin samples

- `scanner-api/app/review.py:933-943` marks under-coverage incomplete only
  when fewer than 20 pages were received.
- Tanners reviewed 38 of 3,689 discovered URLs (1.0%) and was therefore saved
  as complete, non-provisional, authoritative, and release-eligible.
- Decathlon similarly saved 40 of 1,374 (2.9%) as complete and authoritative.
- `scanner-api/app/evidence_quality.py:127-181` treats every crawl with seven
  or more usable pages as representative without checking retained-versus-
  discovered coverage.
- A separate one-page false-positive exists: the small-site proof accepts an
  exhausted queue and zero page-fetch failures but does not reject sitemap
  failure buckets or require a positively established inventory. A sitemap
  404 plus an empty DOM frontier can therefore make a real multi-page site
  look like a proven one-page site.

## Terminal admission reconciliation retries superseded scans

- Cloud Scheduler invokes `/scan-reconcile` every five minutes.
- `base44/functions/durableScanWorkerControl/index.ts:181-209` queries recent
  terminal rows and retries release whenever durable provenance contains an
  `admission_access_id`.
- `base44/functions/durableScanWorkerControl/reconciliation.js:21-35` makes
  every such terminal row release-eligible for two hours. The access ID is
  permanent provenance, not a release-pending marker.
- The coordinator correctly stores only the owner's current generation. Once
  scan B has claimed the slot, a retry for old scan A correctly returns
  `scan_not_bound` before B binds or `scan_identity_conflict` after B binds.
- The sweep treats both safe fencing outcomes as errors, returns
  `success:false`, and turns `/scan-reconcile` into a retryable 503. Production
  logs show this repeating in waves for complete, failed, and cancelled rows.

The safe boundary requires a durable release-pending/satisfied marker,
pagination and retry rotation for every unresolved terminal row, and recovery
of exact bound leases regardless of age. The sweep must read signed coordinator
status, release only the exact bound scan, and mark a row superseded only when a
different generation is positively identified. Mutable owner status must be
refreshed for each different candidate and after release races. Coordinator
conflict checks must remain unchanged, and the worker-completion path must not
globally reinterpret identity conflicts as successful releases.

The local four-file status-lookup prototype is not merge-ready: independent
review proved that the two-hour lookback can permanently strand a bound lease,
the newest-50 query can hide unresolved work, and owner-wide status caching can
be stale across same-owner candidates.

## Release topology and split contract constants

The first health probe targeted the legacy `seo-autopilot-4545` service, which
still reports `51c813a6219b4e70` from revision
`seo-autopilot-4545-eddf450-b8301297`. The actual task target is the separate,
authenticated `fixlist-standard150-worker` service. Its revision
`fixlist-standard150-worker-00030-fj6`, `/health`, and `/revision` report
`03dbfa67f4b708cf` and source SHA
`1eb20072095dd182fb41e276e57050eee071bd50`, matching all 30 completed ScanRuns.

The authority gate used by the audited asynchronous flow is therefore
consistent. Operational monitoring can still select the wrong service, and
the repository retains stale `51c...` literals in `aiReviewScan`,
`persistScanAuthority`, and `grokChat` while the durable authority,
customer-result, and frontend paths use `03db...`.
