# Extended 500 authority and product-contract gates — source audit

Status: **private R2 proof only; no end-to-end 500 product or deployment.**
Baseline: `main` `cd9d4ff562d6aad3cc7ecce059fa12f8d4098db2`, inspected 2026-10-26.
Working branch: `agent/extended500-collector-proof-20261026`, draft PR #377.
Paired Standard 150 backfill: PR #376; independent implementation and rollout.

## Verified in GitHub CI

- Synthetic private `scanner.run_scan` with test-only 500 budget retained exactly 500 distinct HTML page objects from 510 discovered fixture URLs.
- Live published `advanced` cap remains 150; `extended_500` is not an admitted public or worker mode.
- B11 reachability has explicit 500-page scope only under `max_assessed_pages=500` and default 150 rejects 151. B10/B11 helper evidence accepts 500 only when caller opts in; fails at 501, rejects mixed-mode provenance. No helper asserts sitewide orphaning from observed sample links.
- The 150-page review/HMAC builders now explicitly refuse an oversized result or reported count before signing; a forged 150 count cannot conceal a 500-object page array. 500-page private page projection uses the positive external allowlist and strips internal main-text, raw links and unknown future fields.
- The above are fixture assertions and repository CI. They do not measure live site speed, Cloud Run peak RSS, result storage sizing, review wall time or actual customer correctness.

## Known remaining hard contract blockers

| Surface | Observed source behavior | Required change before enabling 500 |
| --- | --- | --- |
| Scanner public mode | `scanner.py` `advanced` = 150, unknown mode also resolves to advanced | Explicit internal `extended_500` budget with server-owned admission and no customer override |
| Durable worker | `main.py` `/scan-job` accepts only `standard_150`; dispatch-gateway also rejects nonstandard | New authenticated task mode, identity, replay fences, quota/entitlement and queue isolation |
| Worker timeout | `scanner.py` job crawl capped at 120s, outer wall at 135s | Benchmark and redesign/batch if 500 does not fit; do not simply increase timeouts |
| Response | `main.py` `enforce_scan_response_page_budget` clips advanced to 150 | Separate verified 500 response/summary projection preserving exact counts |
| Stage 2 | B10/B11 pure helper limit now opt-in 500; other producers/orchestrators remain audited only for 150 | Track all producers and aggregated evidence, validate CPU/memory and scope |
| Review | `review.py` site fingerprint uses `pages[:220]` in several paths | Define 500 sample policy and whether 220-page fingerprint suffices, with honest `sampled` counters |
| Review envelope | `scan_job.py` Standard 150 envelope declares `standard_150`, sends at most 60 pages and 100 findings | Version a distinct 500 authority review contract that differentiates all crawled from sampled/reviewed, never reuse Standard 150 signed completion |
| Signed storage | `scan_job.py` completion and limited contracts use Standard 150 versions; Base44 persistence/JS authority validates them | New signed mode/version, canonical serialization parity, source SHA, CAS, idempotence, compensation and replay tests |
| Frontend | `src/lib/scanRunModel.js`, `src/lib/scanStorageRecovery.js`, ScanWebsiteForm, billing still Standard 150 | Explicit feature-gated 500 plan, correctly labeled result/history/progress/export and entitlements |
| Customer release | `scripts/acceptance-gates.mjs` fails if `pages_crawled > 150` | Mode-discriminated acceptance gates retaining all existing Standard 150 fixtures |

## Formal invariants for R3/R4

1. A Standard 150 signed payload cannot contain or claim over 150 assessed pages regardless of frontend aliases or forged count.
2. A 500 signed payload, when introduced, must carry a new authenticated canonical mode distinct from Standard 150; same scan identity/mode invariant across signed task, scanner, reviewer and storage.
3. `pages_found` is a discovered inventory, `urls_attempted` is attempted fetches, `pages_crawled` is distinct retained destinations, `usable_html_pages` is accepted HTML, `sampled_pages_sent_to_review` is a bounded sample. Never substitute one for another.
4. A 500 page assessment or a 60-page review sample is *not* 500 reviewed pages by implication. Authoritative findings require observed evidence and a clear sampling denominator.
5. Distinct HTTP final destination identity and robots/scope/SSRF/rate limiting remain unchanged. 429 is never bypassed by increasing retry or concurrency.
6. Standard 150 replay and existing signed snapshots remain compatible byte-for-byte; new mode cannot consume a Standard 150 entitlement.
7. Real-site staging must measure completion, processing time, peak RAM, response and stored payload bytes, 429 behavior, error fractions and rollback. No invented throughput or `p95` threshold.

## Rollout decision

PR #377 remains a **draft test/proof branch**. Even with green CI, it is insufficient to merge/deploy as a public 500 feature. The next coherent engineering slice is an authenticated Extended 500 durable ingress **paired with** a new end-to-end signed review/persistence contract, or else a separate fixture-only design without bypassing any existing 150-page guards. No production activation absent operator approval and canary evidence.
