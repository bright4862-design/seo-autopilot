# FixList release audit — Codex handoff

Date: 2026-08-27
Scope: frontend design system, routing, module graph, Base44 function package
layout, repository hygiene, and a read of the scanner's release posture.
Base commit at audit start: `eb06df4`. Design changes merged as `836fe6a`.

This is a handoff document, not a change record. It states what was checked,
what was found, what was changed, and — importantly — what was **not** verified,
so the next agent does not inherit unearned confidence.

---

## 0. Executive summary

Three separate things, with three different answers.

| Area | Verdict |
|---|---|
| Frontend design consistency | **Was drifting; now fixed and merged.** |
| Repository hygiene / architecture | **Structurally noisy. One real security issue, fixed. The rest is post-launch work.** |
| Scanner release readiness | **Engineering is strong. Empirical evidence for the current build does not exist.** |

The single most important sentence in this document is in §4:
the scanner's August 21 blockers are addressed in code, but the current
candidate has never been validated against real sites, and
`docs/beta-acceptance.md` says so itself.

---

## 1. What already landed on `main`

Merged as `836fe6a` (PR #193). Presentation and static metadata only — no
product logic, data flow, contract, or dependency changes.

### 1.1 Document head (`index.html`)

| Was | Now |
|---|---|
| `<title>` said `SEO Autopilot — AI SEO Fixes for Small Business` | FixList |
| Meta description promised *"fix the easy SEO issues, recommend redirects, clean up sitemap problems"* | Describes what the read-only scan returns |
| Favicon hotlinked from `https://base44.com/logo_v2.svg` | Local `/favicon.svg` in the ink/paper palette |
| `/manifest.json` linked but no `public/` directory existed → 404 on every load | Real manifest at `public/manifest.json` |
| No Open Graph / Twitter tags → blank link previews | Full set + `public/og-image.png` (1200×630) |

The meta description is worth understanding rather than just noting: it
advertised **write** behaviour for a product whose landing FAQ answers *"Will
FixList change my website?"* with *"No. FixList is read-only."* That was a
truthfulness defect on the most public surface the product has.

**Open decision for the owner:** the retitle assumes FixList is the public
brand. Evidence is one-sided — every shipped surface says FixList and the domain
is `getfixlist.com`; "SEO Autopilot" survives only in the repo name, the old
title tag, and a stale report. It is a one-line revert in `index.html` if that
is wrong.

### 1.2 Palette alignment

- `src/index.css`: root `--background` / `--foreground` held the cool blue-grey
  template defaults while every shipped surface paints warm `paper`/`ink` from
  `tailwind.config.js`. Repointed at the real palette. Symptom was a tint change
  on overscroll and a colour flash on every authenticated load.
- `src/components/ProtectedRoute.jsx`: the fallback paints *before* the app on
  every authenticated load and was an unlabelled slate spinner on that
  mismatched ground. Repainted; added `role="status"` and a screen-reader label.
- `src/components/billing/LeadRequestModal.jsx`: opened over Billing in
  blue-and-slate shadcn styling. Restyled to paper/ink; inputs now carry
  associated `<label for>`.
- `src/components/UserNotRegisteredError.jsx`: auth-boundary screen matching
  neither system. Restyled to the `AuthLayout` column.
- `src/components/layout/DashboardLayout.jsx`: nav links and Log out had no
  `focus-visible` ring while the brand link beside them did.

Those three components were the **only** reachable files still using off-palette
Tailwind colours. The redesign was otherwise thorough — this is a finishing
pass, not a rescue.

### 1.3 Verification performed

`eslint` clean · `tsc` clean · 815/815 frontend tests (unchanged from baseline)
· `vite build` succeeds · assets confirmed serving `200` with correct
content-types from a preview server · landing page and restyled modal rendered
in Chromium and visually inspected.

---

## 2. Open PR — security

**PR #194**, branch `claude/release-audit-design-arch-oeexdn`, head `93bc20f`.
CI green. Draft, awaiting owner decision.

`.base44-device.json` is tracked in this repository, **which is public**. The
Base44 CLI writes it during `base44 login`; it holds an OAuth `device_code` —
the value the CLI polls the token endpoint with.

**Nothing needs rotating.** Committed copies carry `"expires_in": 600`, so every
device code ever pushed here died ten minutes after it was written.

The risk is the tracked path, not the stale file:

1. `base44 login` writes a live `device_code`.
2. A routine `git add -A && git commit && git push` within ten minutes.
3. Live device code is public; GitHub's events feed is scraped in real time.
4. On browser approval, whoever holds the code can poll Base44 for the token.

Fix is `git rm --cached` plus a `.gitignore` entry. File stays on disk; CLI
unaffected. History deliberately left alone — rewriting it would break every
clone to remove codes that are already dead.

---

## 3. Architecture findings — not touched, ordered by what to pick up first

None of these were changed. Each is either too large or too close to the release
path to move on launch night.

### A1 — More than half the frontend is unreachable

Walking the import graph from `src/main.jsx`:

| | Files | Lines |
|---|---:|---:|
| Reachable | 67 | 11,911 |
| **Unreachable** | **92** | **9,961** |

Breaks down as **13 unrouted pages** (`Dashboard`, `Reports`, `Competitors`,
`Developer`, `Issues`, `CrawlStatus`, `Assistant`, `Admin`, `Canonicals`,
`JsRendering`, `Metadata`, `Redirects`, `OAuthConsent` — `App.jsx` redirects
their paths to `/dashboard`) and **43 unused shadcn components** in
`src/components/ui/`.

Rollup tree-shakes all of it, so there is no bundle or user-facing cost. The
cost is that every search of this codebase returns two answers and the file tree
does not say which one ships.

**Do not bulk-delete.** A large number of these files are pinned by the test
suite, which reads them as *source text* (e.g. `publicBetaSurface.test.mjs`
reads `MobileBottomNav.jsx`, `crawlStatusPipeline.test.mjs` reads
`CrawlStatus.jsx`). Removing a file means retiring its test in the same commit.
Work it page by page, running `npm run test:frontend` each time.

`OAuthConsent` being unrouted is worth a specific check — confirm that flow is
meant to live entirely on Base44's side.

### A2 — The SDK client rewrites customer-facing content

`src/api/base44Client.js` monkey-patches `functions.invoke` and, on the response
path, walks the payload and edits it **in place**: dropping recommendations
(returning `null` filters them out), rewriting titles and explanations by regex,
downgrading priorities, and replacing `customer_summary`,
`simple_summary`, `health_explanation` and `website_health_report` prose
outright when coverage looks thin.

That is product policy living in the layer whose job is to move bytes. It is
invisible to callers, cannot be exercised without faking a transport, and
applies to any future function that happens to match the name list.

**Before refactoring, check this:** the sanitiser only matches
`runStandard150Scan`, `runAdvancedScan`, and `aiReviewScan`. The shipped
customer read path is `getCustomerScanResult` (`src/lib/scanRuns.js`). If that
holds, most of these ~300 lines no longer execute for the durable release path,
and this becomes deletion rather than refactoring. Verify before assuming.

Related: `src/lib/scanStorageRecovery.js:454` wraps the *same*
`functions.invoke` a second time. Load order is decided by `main.jsx` importing
`scanStorageRecovery` before `App`; because `scanStorageRecovery` imports
`base44Client`, the client's wrapper installs first and the recovery wrapper
composes outside it. Not a live bug — `SCAN_GATEWAY_FUNCTIONS` deliberately
contains both the legacy and current names, so the outer wrapper still matches
before the inner one remaps `runAdvancedScan` → `runStandard150Scan`. It is
manual coupling across two files with nothing enforcing it.

### A3 — Copied function modules have drifted; only one is guarded

Base44 function packages cannot import from `../`, so shared modules are copied
per package. This is solved correctly for exactly one of them:

- `generatedReleaseContract.js` — 9 copies, **1 distinct**. Emitted by
  `scripts/generate_release_contracts.mjs`, and CI runs it with `--check`.

The other two were copied by hand and are not guarded:

- `authoritySeal.js` — **7 copies, 5 distinct**
- `authoritySnapshot.js` — **3 copies, 3 distinct**

No live mismatch found: `AUTHORITY_SEAL_VERSION` is
`scan_evidence_hmac_sha256_v1` everywhere it is declared (two copies do not
declare it at all). But this is the seal logic deciding whether a saved result
is trustworthy, five versions exist, and nothing would report further
divergence. **The fix is to bring both under the generator that already
exists** — the pattern is proven in this repo.

### A4 — `src/pages/FixList.jsx` is 1,775 lines doing five jobs

Fetches, polls, normalises, ranks, and renders. Roughly 60 pure helpers live in
it (`build429Explanation`, `getCmsSteps`, `mergeMetaDescriptionRecommendations`,
`buildSpecificTitle`, …) beside eight subcomponents.

Mostly a lift-and-shift: `src/lib/` already holds the equivalents, so helpers
can move a few at a time behind the existing tests.

### A5 — 52 runtime dependencies the app never loads

The shipped graph imports 11 packages. `dependencies` lists 65. Excluding
`@base44/vite-plugin` and `tailwindcss-animate` (config-time, legitimately
used), 52 are unused: `three`, `recharts`, `jspdf`, `html2canvas`, `moment`,
`lodash`, `react-leaflet`, `react-quill`, `framer-motion`, `@tanstack/react-query`,
both Stripe SDKs, 25 Radix packages, and others.

Tree-shaking means no bundle cost — this is install time and audit surface.
**Clear it after A1, in the same pass**, not before, or you will remove
something a pinned test still reads.

### A6 — `src/UI_UX_REPORT.md` documents a product that no longer exists

It describes SEO Autopilot: blue-to-indigo gradients, a collapsible left
sidebar, white cards on blue-grey, eight dashboard pages. The shipped app is a
flat paper-and-ink 680px column with three routes.

It is the first file anyone — designer, contractor, or agent — opens to learn
the design system, and all of it is wrong. Refresh it or move it to
`docs/archive/` with a date. `src/PROJECT_REPORT.md` and
`src/SEO_APP_GLOBAL_FUNCTIONS_ARCHITECTURE_REPORT.md` also sit in `src/` and
belong in `docs/`.

### A7 — Small items

- `base44/config.jsonc` names the app `"untitled"`. This is what shows in the
  Base44 dashboard.
- Two `ScoreRing` components. The live one
  (`src/components/fixlist/ScoreRing.jsx`) animates and handles the
  unavailable-score state; the dead one
  (`src/components/dashboard/ScoreRing.jsx`) renders a raw `{score}` and would
  print `null`.
- `MobileBottomNav` is unreachable and three of its five links point at routes
  that no longer exist (`/crawl-status`, `/developer`, `/reports`). Harmless
  while unmounted — but it is exactly the file someone restores in a hurry.
- No `canonical` tag was added in §1.1. A single static canonical in an SPA
  declares every route a duplicate of `/`. Probably desirable here, but it
  should be a deliberate call rather than a default.

### A8 — No per-account scan rate limiting

The admission coordinator (`admission-coordinator/`) provides **exactly-once**
scan admission via Firestore transactions — a correctness property, not an abuse
control. No per-account rate limit was found, and `src/pages/Billing.jsx`
advertises "Unlimited Standard 150 scans" for the $50 tier.

One account can therefore run unbounded 150-page crawls of third-party sites.
That is a Cloud Run cost exposure and a reputational one — your egress IP in
someone else's rate-limit logs. Not a launch blocker; worth a cap before the
beta scales.

---

## 4. Scanner release readiness — read this section carefully

`scanner-api/` is 46 modules / 17,271 lines with 104 test files.

### 4.1 What is strong, and verified

**SSRF is closed properly.** For a scanner that fetches arbitrary
customer-supplied URLs from a cloud VM, this is the defining risk, and
`scanner-api/app/security.py` handles it correctly: one `getaddrinfo` snapshot,
rejection of the hop unless **every** resolved address is public, connection to
the validated numeric IP while `Host` and TLS SNI keep the original hostname,
`Connection: close` to prevent pool reuse across virtual hosts, and per-hop
re-resolution and re-validation of redirects bounded by `DEFAULT_MAX_REDIRECTS`.
Covered by `scanner-api/tests/test_security_dns_pinning.py` and
`tests/frontend/scannerSsrfGuard.test.mjs`. `scanner-api/SECURITY_BACKLOG.md`
records it as CLOSED and the record matches the code.

**The release pipeline is unusually well guarded.** Publishing is
`workflow_dispatch` only and requires the exact `main` SHA as confirmation
(`.github/workflows/fixlist-base44-release-publish.yml`), with
`scripts/lib/release-source-guard.sh`, `deployment_preflight.sh`,
`post_deploy_verify.sh`, and `verify-base44-site.sh` around it. **Merging to
`main` does not deploy.** The only push-to-`main` triggers are `ci.yml` and two
workflows path-scoped to `data/final-crawler-validation-trigger` and the IAM
bootstrap workflow itself.

### 4.2 The August 21 blockers are addressed in code

`docs/audit/2026-08-21-production-50-site/REPORT-FOR-CLAUDE-CODE.md` recorded
30/50 completed, **2/30 clean result-quality passes**, and **66.7% classification
accuracy**, with a verdict of *"Do not treat the current production build as
beta-release evidence yet."*

Checked against current code:

| Blocker | Mechanism now present | Verified how |
|---|---|---|
| P0 — thin crawls sealed as authoritative (38/3,689; 40/1,374; 1-page) | `scanner-api/app/coverage_authority.py`: `MIN_RETAINED_PAGES = 50`, `MIN_RETAINED_RATIO = 0.10`, behind `MIN_INVENTORY_FOR_RATIO_TEST`; yields `authoritative: false`, `score_is_provisional: true`, `release_gate_eligible: false` | Read the state machine; 21/172 control preserved as specified |
| P0 — limited results need their own path, not generic failure | `standard_limited_result_integrity_v2`, `status: "limited"`, `result_integrity_verified`, read back in `FixList.jsx` (`hasVerifiedLimitedScan`) | Traced end to end |
| P0 — impossible denominators (127/126 vs 1 homepage) | `scanner-api/app/repair_coverage.py`: `cross_cutting`/`mixed` partitioning plus named invariants `indexable_affected_exceeds_eligible`, `family_breakdown_does_not_sum_to_page_count`, `page_count_disagrees_with_unique_affected_pages` | Read the invariant checks |
| P1 — two release contracts in one tree | Single canonical source → `scripts/generate_release_contracts.mjs` → 10 consumers, `--check` in CI | Ran `--list`; confirmed CI step |
| P1 — admission reconciliation retry storm | `admission_reconciliation_v1_exact_generation_barrier` | **Marker only — implementation not read** |
| P1 — classification accuracy 66.7% | Classifier moved v9 → v10 (`archetype_classifier_v10_structural_finance_member_retail`) | **Version moved — accuracy not measured** |

### 4.3 The evidence gap — the actual finding

`docs/beta-acceptance.md` states, in its own words:

> **Status: CANDIDATE — production acceptance NOT met.**
> Deployed commit: *not recorded*. Acceptance report: *not recorded*.
> "no deployed commit, no acceptance report, no production scan"

There is no audit newer than 2026-08-21. The build that audit measured —
fingerprint `03dbfa67f4b708cf` — is now **eight candidates back**:

```
03dbfa67f4b708cf  ← the only build with real-site evidence
  → 5caec7fdcabceee7 → 1f730bb039aef84e → fbb06c2634b74ca6
  → fdd5906461a468d3 → 6e0368d4ac5d2a6b → 400f68e10999fc59
  → cd31b3c1e5f9dd7c → e18b72b2d0e159b8  ← current candidate
```

So the only empirical numbers describe a build no longer running. Nobody knows
whether classification accuracy went to 90% or to 70%.

### 4.4 How the risk changed shape — and the one number to go get

Every fix above makes the scanner **fail closed**. A thin crawl that used to
seal as a confident score now returns provisional and limited. Being honestly
limited beats being confidently wrong to a paying customer, so shipping
unvalidated is materially less dangerous than it was in August.

But it moves the unknown rather than removing it: **what fraction of real sites
now land in `limited`?**

- 10% — fine.
- 60% — customers pay $50 and are told the site could not be covered. That is a
  business problem rather than a truthfulness one, and better discovered before
  launch than from refund requests.

**Highest-value next action, and it is small.** The tooling exists:
`scanner-api/scripts/run_beta_acceptance_scans.py` (3-site post-deploy) and
`scripts/standard150_acceptance_matrix.py` (the full matrix). Run 10–15 sites
against the deployed worker and count **authoritative vs limited only** — not
the full quality review. That answers the question in well under an hour and is
the single number that most affects how launch goes.

---

## 5. Test and CI status

| Suite | Result |
|---|---|
| `npm run lint` | clean |
| `npm run typecheck` | clean |
| `npm run test:frontend` | **815 / 815** |
| `npm run build` | succeeds (578 kB JS / 179 kB gzip, 1 chunk) |
| GitHub CI "Lint, typecheck, contract tests, and build" | green on `93bc20f` |
| GitHub CI "Scanner regression fixtures" | green on `93bc20f` |

`scanner-api` pytest run **inside the audit sandbox** gave 744 passed / 8 failed.
All 8 failures are `pyo3_runtime.PanicException` and `ModuleNotFound` from a
broken Rust extension in that sandbox, **not** real failures — the same suite is
green in CI, which also runs `scripts/freeze_beta_revision.py --check` and the
production Docker build. Do not chase those 8 locally without first confirming
the environment.

---

## 6. Suggested order of work

**Before launch (small):**
1. Merge PR #194 (device-code hygiene).
2. Get the authoritative-vs-limited rate from §4.4.
3. Confirm the FixList vs SEO Autopilot brand call (§1.1).

**Immediately after launch:**
4. A3 — bring `authoritySeal.js` / `authoritySnapshot.js` under the existing
   generator. Smallest change with the highest integrity payoff.
5. A8 — per-account scan rate limit.
6. A6 — fix or archive the stale design report before anyone builds on it.

**Then, deliberately:**
7. A2 — establish whether the `base44Client` sanitiser still executes on the
   durable path; delete or relocate accordingly.
8. A1 + A5 — retire unrouted pages and unused components with their pinned
   tests, then clear the 52 unused dependencies in the same pass.
9. A4 — move `FixList.jsx` helpers into `src/lib/` incrementally.

---

## 7. What was *not* verified

Stated plainly so the next agent does not over-trust this document:

- No scan was run against a live site. Every scanner claim is from reading code,
  tests, and the repo's own records.
- The P1 admission-reconciliation fix was confirmed only by its version marker
  in `docs/beta-acceptance.md`; the implementation was not read.
- Classification accuracy was **not** measured. Only the classifier version
  moving v9 → v10 was observed.
- Backend scanner internals, the Python services, and deployment scripts were
  read for structure and release posture, not audited line by line.
- The claim that the `base44Client` sanitiser no longer runs on the durable path
  (§A2) is inferred from the function-name list versus the read path in
  `src/lib/scanRuns.js`. **Confirm it before acting on it.**
