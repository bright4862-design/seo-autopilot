# FixList customer beta release roadmap

**Roadmap date:** 2026-08-14  
**Target:** **Capped public beta by Friday, 2026-08-21 (Europe/Paris).**  
**Release posture:** **NO-GO today. The August 21 target is aggressive but achievable only if every P0 gate passes; otherwise the public surface launches as a waitlist while scanning and payments remain invite-only.**  
**Scope:** Standard 150 only. Grok and Premium 5,000 remain disabled. Scanner crawl limits, discovery behavior, scoring, classification, and authority eligibility are frozen unless a separately approved release changes them.

### What “public beta” means for this deadline

- Landing, registration, payment, Standard 150 scanning, saved results, and support are publicly reachable.
- The first cohort is capped at 25 paid beta customers.
- One active scan per account and an explicit fair-use limit protect the single-concurrency queue.
- New purchases can be paused without taking the scanner or existing customer results offline.
- Grok, Premium 5,000, experimental routes, and unfinished workflow controls remain absent.
- This is not general availability or unlimited-scale readiness.

Because this roadmap was written on Friday evening, “end of this week” would literally mean Sunday, August 16. A safe paid public launch in that window is not credible. The execution plan therefore uses Friday, August 21 as the deadline. Sunday, August 16 can support only a public waitlist or a known-user internal beta.

## 1. What is already proven

The scanner is no longer the main beta risk.

- The keyless dispatch gateway is restored and the incorrect cross-service build trigger is disabled.
- A fresh Norris Wines production scan completed with an authoritative FixList and a valid 64-character authority proof.
- The first production matrix produced 10 authoritative outcomes from 11 sites. The one non-authoritative Malt result failed the explicit `release_gate_eligible` predicate, demonstrating that the gate discriminates instead of approving every crawl.
- The subsequent Ike's Sandwiches scan also completed authoritatively: 163 URLs found, 150 pages crawled, health score 56, Python scanner/review, no fallback, and `release_gate_eligible=true`.
- Large sites discovered up to 5,000 in-scope URLs while preserving the Standard 150 crawl cap.
- The current frontend suite passes 300 tests.

This evidence supports a tightly monitored invite beta after customer-surface and integrity blockers are closed. It does **not** establish public-beta readiness. The formal freeze record is still `candidate`, the current 20-site matrix is unfinished, and the existing tests do not cover several payment, authority, recovery, or customer-journey failures.

## 2. Newly confirmed duplicate defect

The fresh Ike's result proves that the duplicates are persisted, not merely rendered twice by React.

| Evidence | Result |
|---|---:|
| ScanRun | `6a7f5577bd5a5dade6a1089b` |
| FixList | `6a7f55c895ba0ad5d40998d3` |
| Persisted FixItems | 36 |
| `redirect_destination_noindex` items | 31 |
| Identical page-level cards | 30 |
| Family card covering the same issue | 1 card covering 105 location pages |
| `redirect_chain` items | 4: three page cards plus one family card |

The review currently collects overlapping `grouped_findings`, `raw_findings`, `findings`, and `recommendations` arrays, then primarily deduplicates by `fix_id`. The page and family forms have different IDs, so both survive. The 36-item output cap is therefore consumed by repeated work and can hide distinct recommendations.

This is a **P0 customer-release blocker**. A customer-facing action count must represent distinct work.

### Minimum fix boundary

Do not change crawling, discovery, scoring, classification, evidence thresholds, or release eligibility.

Apply one deterministic presentation rule while building the durable authority snapshot, **before** counts and the authority proof are calculated:

1. Identify family/cross-cutting items by `rule` and `page_template_family`.
2. Suppress a page-level item only when a same-rule aggregate explicitly includes that page in `affected_pages`.
3. Keep page-level outliers not covered by an aggregate.
4. Recalculate FixList totals, priority counts, and top-action IDs from the deduplicated set.
5. Seal and persist that same set so reconstruction still matches the authority proof.

Do not filter only inside `authorityRowsFromSnapshot()` after the proof is created; the saved rows would no longer reconstruct the signed snapshot. For the captured Ike's fixture, the expected action set is four distinct cards: canonical family, noindex-redirect family, redirect-chain family, and the uncovered contact-page redirect chain.

## 3. P0 — required before any paying customer

### P0.1 Authority and paid-content boundary

**Owner:** Backend/security  
**Goal:** Browsers can read verified customer projections but cannot manufacture, mutate, delete, or prematurely reveal authoritative results.

Work:

- Make `ScanRun`, `FixList`, and authority-bearing `FixItem` fields owner-readable but service-role/admin writable and deletable only.
- Move customer workflow state such as “done” into a narrow owner-bound mutation or separate progress record. Do not reopen the sealed evidence row for general updates.
- Serve results through an entitlement-aware server projection that verifies: exact owner and project, terminal `complete` status, `release_gate_eligible=true`, matching ScanRun/FixList/FixItem proofs, authoritative FixList, and correct record relationships.
- Return only preview metadata to unpaid users. The current render-only paywall downloads all FixItems before hiding them and is not an access boundary.
- Never render staged `reviewing` rows or unsealed recommendations as a completed FixList.

Acceptance:

- An owner cannot update or delete authority-bearing rows directly, including `status`, `release_gate_eligible`, `health_score`, `fix_list_id`, `is_authoritative`, recommendation text, or evidence.
- An unpaid browser cannot retrieve full FixItems through either the normal UI or direct entity queries.
- Tampered, staged, mismatched, or unsealed records produce a safe unavailable state, never a completed FixList.
- “Done” can be changed through only the narrow workflow endpoint and does not alter the authority proof.

### P0.2 Deduplicate the sealed FixList

**Owner:** Backend/FixList presentation  
**Goal:** One distinct action appears once, with affected pages grouped under it.

Acceptance:

- The captured Ike's fixture contracts from 36 rows to four distinct actions under the coverage rule above.
- No page-level item remains when a same-rule aggregate covers that exact page.
- An uncovered page-level outlier remains visible.
- FixList totals and priority counts equal the persisted deduplicated rows.
- Reconstructed rows validate against the authority proof.
- Scanner/review versions, crawl cap, score, and `release_gate_eligible` remain unchanged.

### P0.3 Make checkout and activation exact-once

**Owner:** Payments/backend + frontend  
**Goal:** A customer cannot pay and remain locked, be offered a second purchase while activation is pending, or redirect Stripe to an arbitrary origin.

Local candidate update (2026-08-14): return-origin validation, pending-session
reuse, replay-safe webhook ordering, bounded activation polling, a default-off
purchase switch, an exact allowlist capped at 25 Base44 user IDs, and
pre-provisioned-only Access admission are implemented and test-backed. Checkout
no longer creates Access rows, and Stripe idempotency is based on user ID,
cohort generation, and prior session. This remains undeployed; test-mode Stripe
acceptance and operator pre-provisioning evidence are still required.

Work:

- Derive or allowlist checkout success/cancel origins server-side.
- Reuse or safely expire a pending Stripe session; never overwrite a still-valid pending session binding.
- Test reverse-order, duplicate, delayed, and replayed webhook delivery.
- On `?paid=1`, show “Activating access,” disable the purchase CTA, and poll/reconcile entitlement for a bounded period.
- Model explicit loading, unpaid, pending, active, conflict, and support-required states without flashing paid content.

Acceptance:

- One payment creates one active entitlement exactly once under all webhook orderings.
- A repeated checkout click cannot invalidate the first paid session or create a second charge path.
- Only approved app origins can be used for Stripe return URLs.
- A successful test-mode purchase reaches an active scan entitlement without manual database repair.

### P0.4 Publish one honest offer and minimum trust surface

**Owner:** Product/founder + legal/payment operations  
**Goal:** The promise before registration matches what the application actually provides.

Fastest beta contract: keep the paid Standard 150 model, remove “Free scan included” and “No credit card needed,” and show a real anonymized sample FixList instead. Align every surface on:

- price and currency;
- one-time versus recurring payment;
- what “lifetime beta” means;
- Standard 150 page cap;
- realistic 2–4 minute estimate plus possible queue delay;
- fair-use or explicit scan limits;
- refund, tax, support, retention, and beta-change terms.

Publish and link Privacy, Terms, Refund/Cancellation, Security/Read-only scanning, Support, and data-deletion information from Landing, Register, Billing, and checkout. Account deletion must create an acknowledged request with a reference rather than redirecting the customer to generic Base44 support.

Acceptance:

- Automated copy tests cover Landing as well as the authenticated app and reject contradictory free/no-card/timing claims.
- Every policy route resolves without authentication and checkout terms match the displayed offer.
- A real support destination and deletion-request workflow are tested.

### P0.5 Make scans recoverable and server-owned

**Owner:** Backend + frontend  
**Goal:** A slow, failed, or revisited scan cannot appear lost or be incorrectly killed by a browser.

Work:

- Keep terminal transitions with the signed worker/watchdog. A browser must not mark a valid queued scan failed after a local eight-minute TTL.
- Atomically create or reuse an owner/project/target scan lease server-side.
- Enforce one active scan per owner plus a documented bounded rate; return a retry time when busy.
- Preserve the exact `scan_id` across navigation. `/dashboard` should open the newest owned result or visible scan history when no ID is supplied.
- Distinguish network failure, unauthorized, not found, queued, crawling, reviewing, delayed, failed, cancelled, limited, and complete.
- Map allowlisted error codes to customer-safe messages, retry actions, and an opaque support reference. Do not expose internal function names or raw payloads.

Acceptance:

- Cross-tab double submission creates/reuses one durable scan and one task path.
- Logout/login restores the latest owned result; explicit IDs never substitute another scan.
- Queue delay cannot be overwritten by browser recovery.
- Every started test reaches a valid terminal state or remains truthfully delayed under server ownership.

### P0.6 Remove unreleased and internal customer surfaces

**Owner:** Frontend/product  
**Goal:** Customers see only shipped features and safe support information.

Work:

- Remove the customer `ScanDebugPanel`, raw JSON, internal owner/project/request/release IDs, and misleading “Clear scans.” Keep only an opaque “Copy support reference.”
- Make `/assistant` unreachable while Grok is disabled; remove the inert Grok navigation item from the beta shell.
- Keep Premium 5,000 unavailable and out of the active purchase path.
- Use a polite stage-only live region; keep the one-second timer out of assertive announcements and expose the score as an accessible meter.

Acceptance:

- Direct `/assistant` navigation cannot load or invoke Grok.
- No normal customer route renders raw debug data or internal IDs.
- Keyboard, mobile, and screen-reader smoke tests pass the signup, checkout, scan, result, and retry paths.

### P0.7 Release operations and measurement

**Owner:** Release/operations + product analytics  
**Goal:** The team can prove what is deployed, detect a broken journey, and roll back quickly.

Work:

- Add a Base44 publish preflight that inventories `startStandardScanJob`, `durableScanWorkerControl`, and `persistDurableScanAuthority`; fail if a required function would disappear from the draft manifest.
- Keep gateway and worker build contexts/triggers separate and add a service-contract smoke test after deployment.
- Before the next worker deployment, close the Cloud Build provenance hole: `_RELEASE_SHA` is currently validated only as 40 hex characters. Verify the submitted filesystem against that commit inside the build, not just in a local preflight.
- Add alerts for gateway contract failures, task retry exhaustion, stuck active scans, missing Base44 functions, authority-predicate failures, queue age, worker 5xx rate, and latency.
- Emit one deduplicated funnel: landing CTA, registration verified, checkout started, payment returned, access activated, scan accepted, scan completed/failed, result viewed, fix opened.
- Update the formal release record only after the post-fix acceptance evidence exists; record exact commit, function package hashes, Cloud Run revision/image digest, Base44 function inventory, scan IDs, and artifact digest.

Acceptance:

- One customer-journey E2E test produces exactly one traceable funnel sequence.
- A release operator can identify the deployed source and roll back in under ten minutes.
- Missing required functions or a service/image mismatch fail before traffic or customer scans.
- `docs/beta-acceptance.md` and `data/beta-crawler-revision.json` truthfully remain candidate until the formal gate is complete.

## 4. P1 — first-cohort quality and conversion

Start after all P0 gates pass. These improve conversion and retention during the capped public beta but do not override a P0 failure.

| Workstream | Deliverable | Acceptance |
|---|---|---|
| Product proof | Real anonymized sample FixList on Landing | Shows coverage, score context, three evidence-backed fixes, affected pages, and steps; no fabricated testimonials |
| Activation | Preserve safe return intent and entered domain across registration/checkout | Verified user reaches the correct next action in at most two clicks |
| Result utility | Persist done/undo through the narrow workflow API | Survives reload, logout/login, and another device without changing the seal |
| Scan history | Latest result plus owner-scoped history | Exact `scan_id`, domain, date, status, pages, and score are visible and account switching is tested |
| Implementation handoff | Branded PDF/CSV developer brief | Includes domain, date, coverage/limitations, distinct fixes, steps, and all affected URLs |
| Content quality | Collapse repetitive wording and explain score/coverage | Top three actions are distinct; limitations and sampling are clear |
| Support operations | Support inbox/runbook and issue severity rules | Every report receives an acknowledgement/reference; P0 incidents have an owner and rollback path |
| Branding | One product name, title, favicon, emails, and Base44 configuration | No “untitled,” Base44 placeholder, or mixed SEO Autopilot/FixList identity on customer surfaces |
| Accessibility | WCAG-oriented pass on the five critical journeys | No keyboard traps, assertive timer spam, unlabeled score, or unusable mobile navigation |

Invite-beta operating targets:

- At least 95% of accepted scans reach a truthful terminal state within the published time window.
- Zero scans remain falsely active or are browser-overwritten after 15 minutes.
- Zero fallback backends on authoritative results.
- Zero cross-account or cross-project result substitution.
- Zero duplicate actionable cards under the page-covered-by-family rule.
- Payment-to-access activation success is 100% in the invited cohort; any miss pauses new payments.
- Median time from verified signup to accepted scan is under five minutes, excluding crawl time.
- Every P0 support incident is acknowledged the same business day during beta.

## 5. P2 — scale beyond the capped public beta

Do not start Grok or Premium work here. Public-beta work is about scale and confidence in Standard 150.

- Preserve the post-P0 20-site matrix as a frozen regression artifact and automate it for future release candidates. Judge expected terminal behavior, not a forced 20/20 authority-pass rate: a correctly explained evidence-quality rejection is a valid outcome; infrastructure failures and stuck scans are not.
- Add automated browser E2E coverage for acquisition through result recovery, including two accounts and two tabs.
- Run bounded concurrency, queue-age, rate-limit, and cost tests against the declared beta capacity.
- Add rescan comparisons, resolved-versus-regressed fixes, completion notifications, and verified case studies.
- Add self-service data export/deletion and verify retention controls.
- Consolidate duplicated authority-contract implementations and remove stale release/IAM artifacts under a separate, audited change.
- Consider localization, currency experiments, and broader acquisition only after the paid English-language funnel is measurable and stable.

## 6. Formal launch gates

### Gate A — release candidate by Wednesday, August 19

All must be true:

- P0.1 through P0.7 pass in automated and browser tests.
- Captured Ike's fixture produces four distinct actions and validates its reconstructed proof.
- Paid test-mode journey activates access exactly once and completes one scan.
- No raw diagnostics, Grok route, or full unpaid FixItems are reachable.
- Rollback target and operator are named before launch.

### Gate B — capped public beta by Friday, August 21

All must be true:

- Gate A remains green on the deployed production candidate.
- Fresh Ike's production scan has no page item covered by a same-rule family item.
- Fresh large-site control (Funbooker or Ornikar) reaches the expected bounded crawl and authoritative result with Python backends and no fallback.
- One controlled evidence-limited site remains safely non-authoritative and is not presented as a completed FixList.
- The remaining post-P0 sites complete the planned 20-site matrix with expected terminal behavior, no infrastructure failure, no fallback substitution, no cross-account result, and no stuck scan.
- Public policies, support, deletion requests, capacity cap, fair-use rule, monitoring, and purchase pause control are live.
- The production payment journey activates access exactly once and completes one owner-bound scan.
- No open P0 incident.
- Funnel and scan SLO dashboards receive the launch smoke-test events.
- Release identifiers and the acceptance artifact are recorded truthfully.

### Gate C — expand beyond 25 customers

All must be true for two consecutive weeks:

- The operating targets remain green across the first 25 customers.
- No unresolved P0 and no repeated P1 incident.
- At least five customers independently reach and understand their top three fixes.
- Capacity and fair-use limits match the public offer.
- Current release identifiers and acceptance artifact are frozen and independently reproducible.
- Founder/product, engineering, payments/legal, and support owners all sign the same go/no-go checklist.

## 7. Suggested sequence and ownership

This deadline requires at least two engineering lanes working in parallel, plus a founder/product owner who can approve offer, policy, and support decisions the same day.

| Window | Outcome | Primary owners |
|---|---|---|
| Fri Aug 14 | Freeze scope and public-beta contract; assign named owners; capture sanitized Ike's fixture and acceptance rubric | Product, release lead, QA |
| Sat–Sun Aug 15–16, lane A | Authority RLS/server projection, paid-content boundary, pre-seal dedup, negative tests | Backend/security |
| Sat–Sun Aug 15–16, lane B | Checkout exact-once, origin allowlist, activation states, honest offer, minimum policy/support pages | Payments/backend, frontend, founder |
| Mon Aug 17 | Scan lease/rate admission, browser-read-only recovery, history/latest result, remove debug/Grok/unfinished controls | Backend, frontend |
| Tue Aug 18 | Integrated 300-test baseline plus new authority, dedup, payment-ordering, recovery, offer-copy, and two-account browser E2E tests | QA, both engineering lanes |
| Wed Aug 19 | Gate A review; scoped Base44/site deployment to the release candidate; function inventory and post-deploy smoke checks | Release operator, QA |
| Thu Aug 20 | Fresh Ike's, large-site, and controlled-negative scans; then complete the post-P0 20-site matrix; freeze evidence and rollback target | QA, release operator |
| Fri Aug 21, 10:00 CEST | Final Gate B go/no-go with engineering, product, payments/legal, and support | All owners |
| Fri Aug 21, afternoon | If green, open a capped 25-seat public beta with active monitoring; if red, publish the waitlist and keep payments/scans invite-only | Founder/product, operations |

### Deadline cut rules

When time is short, remove incomplete promises instead of weakening controls:

- Remove “Mark as done” until persistence is ready; never leave a control that silently resets.
- Remove Grok, Premium, raw debug, “Clear scans,” and any unavailable navigation.
- Replace “free,” “unlimited,” and “lifetime” claims with the reviewed beta contract rather than building a new free tier this week.
- Defer full reports, comparisons, testimonials, localization, and visual redesign.
- Never cut RLS immutability, server-side paid-content enforcement, checkout exact-once behavior, sealed deduplication, recovery correctness, policies/support, monitoring, or acceptance tests.

Dates are subordinate to gates. A failed gate pauses expansion; it does not get reclassified as a later enhancement.

## 8. Explicit non-goals

- No scanner crawling redesign.
- No crawl-cap increase.
- No scoring or eligibility loosening.
- No Grok enablement.
- No Premium 5,000 enablement.
- No unrelated frontend redesign.
- No new production scan until the next acceptance target has a written pass/fail rubric.

## Decision

FixList has credible Standard 150 scanner evidence and can target a capped public beta on August 21, but it is not ready to accept uncontrolled customer payments today. Close the authority boundary, sealed-result deduplication, checkout exact-once path, recovery states, honest offer, and release controls in parallel; finish the post-fix 20-site matrix on the release candidate; then open at most 25 paid beta seats under active monitoring. If any P0 or Gate B check is red, the public launch becomes a waitlist and scanning/payments stay invite-only. The deadline never authorizes weakening the authority gate or shipping a known payment/data-integrity defect.
