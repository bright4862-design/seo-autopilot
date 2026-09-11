# Owner-Managed Robots and WAF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Standard 150 owner/manager self-attestation that can ignore `robots.txt` for FixList's crawler only, preserves real robots/indexability evidence, and gives owners actionable WAF-block messaging without weakening any other safety boundary.

**Architecture:** Persist the customer's answer on `BusinessProject` using one canonical enum. `startStandardScanJobV3` is the authority boundary: it reads the owned project, derives the robots policy server-side, persists that policy on `ScanRun`, and dispatches the same policy through the signed gateway to the worker. The worker applies the override request-locally only for FixList's user agent while continuing to record the site's actual robots directives for Google/indexability evidence. Historical customer messaging is derived from the persisted scan policy, not mutable browser state.

**Tech Stack:** React 18/Vite, Base44 SDK/functions/entities, TypeScript/JavaScript, Python 3.12/FastAPI, Flask dispatch gateway, pytest, Node test runner, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-10-owner-managed-robots-waf-design.md`

## Global Constraints

- Standard 150 only; do not touch Premium 5,000 or Grok.
- Owner/manager override bypasses `robots.txt` directives only.
- Never bypass authentication, CAPTCHAs, WAF challenges, rate limits, SSRF/private-network protections, or firewall controls.
- Preserve the 150-page cap, focused-path (`/en/`, `/fr/`, etc.) behavior, subdomain behavior, admission, authority signing, persistence/history, and release gates.
- Canonical ownership enum: `owner_or_manager` and `not_owner`.
- Durable authority: `BusinessProject.site_owner_attestation`; browser storage is UX cache only.
- Persist applied policy on `ScanRun`: `respect_robots_txt` plus `owner_attested_robots_override`.
- A durable task whose policy differs from its stored ScanRun policy must fail closed as `scan_identity_mismatch`.
- Googlebot/indexability evidence must always reflect the actual `robots.txt` directives, even during an owner override.
- Customer WAF title: `Your site's security service is blocking FixList.`
- Customer WAF action: `Temporarily allow FixList in your firewall/bot protection, then Rescan.`
- No merge or deployment until exact-head CI and CodeRabbit are clean.

---

### Task 1: Canonical ownership state and project persistence

**Files:**
- Create/modify: `src/lib/siteOwnershipPolicy.js`
- Modify: `base44/entities/BusinessProject.jsonc`
- Modify: `src/lib/activeProject.js`
- Modify: `src/components/scan/ScanWebsiteForm.jsx`
- Test: `tests/frontend/siteOwnershipRobotsPolicy.test.mjs`
- Test: `tests/frontend/ownerManagedRobotsPolicy.test.mjs` (fold useful assertions into the canonical suite, then remove duplication)

**Interfaces:**
- Produces: `OWNER_ATTESTATION_OWNER = "owner_or_manager"`, `OWNER_ATTESTATION_NOT_OWNER = "not_owner"`.
- Produces: `normalizeSiteOwnerAttestation(value): "owner_or_manager" | "not_owner" | ""`.
- Produces: `robotsPolicyForAttestation(value): { respect_robots_txt: boolean, owner_attested_robots_override: boolean }`.
- `ensureScanProject({... siteOwnerAttestation })` persists `BusinessProject.site_owner_attestation` before scan admission.

- [ ] **Step 1: Write/normalize the failing frontend contract tests**

```js
assert.deepEqual(projectSchema.properties.site_owner_attestation.enum, ["owner_or_manager", "not_owner"]);
assert.match(scanForm, /Do you own or manage this website\?/);
assert.match(scanForm, /Choose whether you own or manage this website before starting the scan/);
assert.match(policySource, /owner_or_manager/);
assert.match(policySource, /not_owner/);
assert.deepEqual(robotsPolicyForAttestation("owner_or_manager"), {
  respect_robots_txt: false,
  owner_attested_robots_override: true,
});
assert.deepEqual(robotsPolicyForAttestation("not_owner"), {
  respect_robots_txt: true,
  owner_attested_robots_override: false,
});
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
node --test tests/frontend/siteOwnershipRobotsPolicy.test.mjs
```

Expected: FAIL because current main has no canonical end-to-end owner policy.

- [ ] **Step 3: Implement the minimal project/UI state**

Use one enum everywhere. `siteOwnershipPolicy.js` may cache by normalized domain for immediate reload UX, but `ensureScanProject` must persist the same value on the owned BusinessProject. The form must block submission until the question is answered for the first scan.

Core policy helper:

```js
export function robotsPolicyForAttestation(value) {
  const owner = normalizeSiteOwnerAttestation(value) === "owner_or_manager";
  return {
    respect_robots_txt: !owner,
    owner_attested_robots_override: owner,
  };
}
```

Submission must call:

```js
const context = await ensureScanProject({
  ...existingProjectFields,
  siteOwnerAttestation,
});
```

Do not treat localStorage as the server authority.

- [ ] **Step 4: Run focused frontend tests**

```bash
node --test tests/frontend/siteOwnershipRobotsPolicy.test.mjs tests/frontend/scanRunIdentity.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/siteOwnershipPolicy.js base44/entities/BusinessProject.jsonc src/lib/activeProject.js src/components/scan/ScanWebsiteForm.jsx tests/frontend/siteOwnershipRobotsPolicy.test.mjs tests/frontend/ownerManagedRobotsPolicy.test.mjs
git commit -m "feat: persist Standard 150 site ownership attestation"
```

---

### Task 2: Make Base44 admission the policy authority

**Files:**
- Modify: `base44/entities/ScanRun.jsonc`
- Modify: `base44/functions/startStandardScanJobV3/entry.ts`
- Modify: `tests/frontend/standard150ServerAdmission.test.mjs` or the existing V3 admission contract suite that asserts payload shape
- Modify: `tests/frontend/scanRunIdentity.test.mjs`

**Interfaces:**
- Consumes: `BusinessProject.site_owner_attestation` from Task 1.
- Produces persisted `ScanRun.respect_robots_txt: boolean` and `ScanRun.owner_attested_robots_override: boolean`.
- Produces a signed dispatch job carrying those exact two fields.

- [ ] **Step 1: Add failing admission tests**

Pin these cases:

```js
// durable owner project derives override server-side
assert.match(startV3, /site_owner_attestation/);
assert.match(startV3, /owner_or_manager/);
assert.match(startV3, /owner_attested_robots_override/);
assert.match(startV3, /respect_robots_txt/);

// ScanRun schema persists both policy fields
assert.equal(scanRunSchema.properties.respect_robots_txt.type, "boolean");
assert.equal(scanRunSchema.properties.owner_attested_robots_override.type, "boolean");
```

Add an executable/fixture contract proving a client cannot force `owner_attested_robots_override: true` when the loaded owned project is `not_owner`.

- [ ] **Step 2: Run the focused admission tests and confirm RED**

```bash
node --test tests/frontend/standard150ServerAdmission.test.mjs tests/frontend/scanRunIdentity.test.mjs tests/frontend/siteOwnershipRobotsPolicy.test.mjs
```

Expected: FAIL at the current hard-coded `respect_robots_txt: true` boundaries.

- [ ] **Step 3: Derive policy from the owned project**

Inside `startStandardScanJobV3`, after `loadExactOwnedProject` succeeds:

```ts
const ownerAttested = String(project.project.site_owner_attestation || "") === "owner_or_manager";
const respectRobotsTxt = !ownerAttested;
```

Persist on ScanRun:

```ts
respect_robots_txt: respectRobotsTxt,
owner_attested_robots_override: ownerAttested,
```

The browser may send its intended policy, but server behavior must be derived from the durable owned project. If a supplied override contradicts the project, reject it rather than widening access.

Include the policy in the admission/request fingerprint so an idempotent request cannot replay under a different robots policy:

```ts
const policySuffix = ownerAttested ? "|robots:owner_override" : "|robots:respect";
const canonical = `${PUBLIC_SCAN_MODE}|${normalizeWebsiteUrl(websiteUrl)}${pathSuffix}${policySuffix}`;
```

Pass both fields into the Cloud Tasks job payload.

- [ ] **Step 4: Run focused admission tests**

```bash
node --test tests/frontend/standard150ServerAdmission.test.mjs tests/frontend/scanRunIdentity.test.mjs tests/frontend/siteOwnershipRobotsPolicy.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add base44/entities/ScanRun.jsonc base44/functions/startStandardScanJobV3/entry.ts tests/frontend/standard150ServerAdmission.test.mjs tests/frontend/scanRunIdentity.test.mjs tests/frontend/siteOwnershipRobotsPolicy.test.mjs
git commit -m "feat: bind owner robots policy at server admission"
```

---

### Task 3: Carry the policy through the gateway and worker without falsifying robots evidence

**Files:**
- Modify: `dispatch-gateway/main.py`
- Modify: `dispatch-gateway/test_gateway.py`
- Modify: `scanner-api/app/main.py`
- Modify: `scanner-api/app/robots_policy.py`
- Modify: `scanner-api/app/scan_job.py`
- Create/modify: `scanner-api/tests/test_owner_robots_override.py`
- Modify: `scanner-api/tests/test_scan_identity.py`

**Interfaces:**
- Consumes task fields `respect_robots_txt` and `owner_attested_robots_override`.
- Produces request-local FixList crawl override; no global mutable policy.
- Produces actual directive evidence plus applied-policy evidence.

- [ ] **Step 1: Add failing gateway/worker tests**

Gateway cases:

```py
assert validate_dispatch(owner_job)[1] is None
assert validate_dispatch({**owner_job, "owner_attested_robots_override": False})[1] == "invalid_robots_policy"
assert validate_dispatch(non_owner_job)[1] is None
```

Worker cases:

```py
# owner override accepted only as the paired tuple (False, True)
# non-owner accepted only as (True, False)
# (False, False) and (True, True) are rejected
```

Robots evidence case:

```py
policy = parsed_policy_that_disallows_both()
token = set_owner_robots_override(True)
try:
    assert policy.allowed(SCANNER_USER_AGENT, url) is True
    page = annotate_robots_evidence({}, policy, url)
finally:
    reset_owner_robots_override(token)
assert page["robots_txt_scanner_blocked"] is True  # directive truth
assert page["robots_txt_policy_applied"] is False
assert page["owner_attested_robots_override"] is True
assert page["robots_txt_googlebot_blocked"] is True
assert page["indexable"] is False
```

- [ ] **Step 2: Run focused Python tests and confirm RED**

```bash
pytest dispatch-gateway/test_gateway.py -q
cd scanner-api && pytest tests/test_owner_robots_override.py tests/test_scan_identity.py -q
```

Expected: FAIL on the current `respect_robots_txt is True` hard gates.

- [ ] **Step 3: Update gateway validation**

Replace the true-only gate with the paired invariant:

```py
respect = job.get("respect_robots_txt")
owner_override = job.get("owner_attested_robots_override") is True
if respect not in {True, False}:
    return None, "invalid_robots_policy"
if owner_override != (respect is False):
    return None, "invalid_robots_policy"
```

Do not change signed-body validation, queue identity, OIDC, deadlines, or destinations.

- [ ] **Step 4: Apply worker override request-locally**

In `scanner-api/app/main.py`, accept the same paired invariant in both `/scan` and `/scan-job`. Use `ContextVar` helpers from `robots_policy.py` so concurrent requests cannot leak policy between scans.

Owner runs may use conservative concurrency (for example 4 versus the existing default 8) but must not receive a larger page/time budget.

Do not bypass 429/503/WAF behavior here. Existing bounded backoff remains the only retry mechanism.

- [ ] **Step 5: Preserve actual robots directive evidence**

In `robots_policy.py`, separate raw directive evaluation from applied FixList policy:

```py
def directive_allowed(self, user_agent: str, url: str) -> bool | None:
    ...

def allowed(self, user_agent: str, url: str) -> bool | None:
    if user_agent == SCANNER_USER_AGENT and owner_robots_override_enabled():
        return True
    return self.directive_allowed(user_agent, url)
```

Use an identifiable UA:

```py
SCANNER_USER_AGENT = "FixListBot/1.0 (+https://getfixlist.com/crawler)"
```

`annotate_robots_evidence()` must report `directive_allowed`, not the overridden fetch decision, and must continue to mark Googlebot-blocked pages non-indexable.

- [ ] **Step 6: Persist policy in authority/review payloads**

In `scanner-api/app/scan_job.py`, replace the hard-coded policy field:

```py
"respect_robots_txt": bool(result.get("respect_robots_txt", True)),
"owner_attested_robots_override": bool(result.get("owner_attested_robots_override", False)),
```

Extend durable identity checks so a task policy mismatch against the stored ScanRun closes as `scan_identity_mismatch` before crawling.

- [ ] **Step 7: Run focused tests**

```bash
pytest dispatch-gateway/test_gateway.py -q
cd scanner-api && pytest tests/test_owner_robots_override.py tests/test_scan_identity.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add dispatch-gateway/main.py dispatch-gateway/test_gateway.py scanner-api/app/main.py scanner-api/app/robots_policy.py scanner-api/app/scan_job.py scanner-api/tests/test_owner_robots_override.py scanner-api/tests/test_scan_identity.py
git commit -m "feat: enforce owner robots override end to end"
```

---

### Task 4: Owner-specific access-limited presentation with historical correctness

**Files:**
- Modify: `src/lib/durableScanStatePresentation.js`
- Modify: `src/pages/FixList.jsx` only if needed to pass the full ScanRun record unchanged
- Modify: `src/components/scan/ScanWebsiteForm.jsx` help text
- Test: `tests/frontend/durableScanStatePresentation.test.mjs`
- Test: `tests/frontend/savedResultRecovery.test.mjs`
- Test: `tests/frontend/siteOwnershipRobotsPolicy.test.mjs`

**Interfaces:**
- Consumes persisted `ScanRun.owner_attested_robots_override`.
- Produces `security_service_blocked` presentation only when the durable limitation kind is `access_limited` and the saved scan says owner override was active.

- [ ] **Step 1: Write failing presentation tests**

```js
const ownerBlocked = durableScanStatePresentation({
  status: "limited",
  coverage_state: "access_limited",
  owner_attested_robots_override: true,
});
assert.equal(ownerBlocked.title, "Your site's security service is blocking FixList.");
assert.equal(ownerBlocked.nextStep, "Temporarily allow FixList in your firewall/bot protection, then Rescan.");

const nonOwnerBlocked = durableScanStatePresentation({
  status: "limited",
  coverage_state: "access_limited",
  owner_attested_robots_override: false,
});
assert.equal(nonOwnerBlocked.kind, "access_limited");

for (const kind of ["save_failed", "worker_stalled", "too_few_usable_pages", "deadline_reached"])
  assert.notEqual(ownerFailureFor(kind).kind, "security_service_blocked");
```

- [ ] **Step 2: Run tests and confirm RED**

```bash
node --test tests/frontend/durableScanStatePresentation.test.mjs tests/frontend/savedResultRecovery.test.mjs
```

- [ ] **Step 3: Implement record-derived presentation**

Keep `durableScanLimitationKind(record)` pure and evidence-based. At presentation time:

```js
function presentedKind(record) {
  const kind = durableScanLimitationKind(record);
  if (kind === "access_limited" && record?.owner_attested_robots_override === true) {
    return "security_service_blocked";
  }
  return kind;
}
```

Do not use current localStorage/project ownership to rewrite a historical scan. This prevents later ownership changes from altering old FixList history.

Update the form help copy so it is truthful:

```text
If you own or manage the site, FixList can ignore robots.txt for this scan. This does not bypass logins, firewalls, bot challenges, or rate limits.
```

- [ ] **Step 4: Run focused frontend tests**

```bash
node --test tests/frontend/durableScanStatePresentation.test.mjs tests/frontend/savedResultRecovery.test.mjs tests/frontend/siteOwnershipRobotsPolicy.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/durableScanStatePresentation.js src/pages/FixList.jsx src/components/scan/ScanWebsiteForm.jsx tests/frontend/durableScanStatePresentation.test.mjs tests/frontend/savedResultRecovery.test.mjs tests/frontend/siteOwnershipRobotsPolicy.test.mjs
git commit -m "feat: explain owner WAF blocks from durable scan evidence"
```

---

### Task 5: Full regression, release contracts, and scope review

**Files:**
- Modify only if generated output requires it: `data/beta-crawler-revision.json` and generated release-contract files identified by `scripts/generate_release_contracts.mjs` / `scanner-api/scripts/freeze_beta_revision.py`.
- No unrelated source changes.

**Interfaces:**
- Produces one exact integration-head SHA eligible for PR review.

- [ ] **Step 1: Run complete frontend gates**

```bash
npm ci
npm run lint
npm run typecheck
node scripts/generate_release_contracts.mjs --check
npm run test:frontend
npm run build
```

Expected: all PASS.

- [ ] **Step 2: Run complete scanner/gateway gates**

```bash
python -m pip install --upgrade pip pytest pytest-asyncio
pip install -r scanner-api/requirements.txt
pytest tests/
(cd scanner-api && pytest tests/)
(cd scanner-api && python scripts/freeze_beta_revision.py --check)
docker build --tag fixlist-scanner:owner-robots-ci .
```

Expected: all PASS.

- [ ] **Step 3: Refresh generated/frozen contracts only if the check says they are stale**

Use the repository's existing generators, then rerun both `--check` commands. Do not hand-edit fingerprints.

- [ ] **Step 4: Review the complete diff against current main**

Required changed areas are limited to ownership UI/persistence, BusinessProject/ScanRun policy fields, V3 admission, dispatch gateway, worker robots handling, durable authority payload, presentation copy, and tests/generated release identity. Confirm no Premium/Grok, focused-path, subdomain, admission lease, signing, crawl-cap, or WAF-bypass changes.

- [ ] **Step 5: Push exact head, open draft PR, and require CI**

PR body must state exact head SHA, source main SHA, files changed, tests run, known non-goals, and that nothing has been deployed.

- [ ] **Step 6: Run CodeRabbit on the exact integration head**

Request full review, with explicit attention to:

```text
1. Can browser-supplied ownership forge a robots override without durable BusinessProject attestation?
2. Can request-local robots override leak between concurrent scans?
3. Does Googlebot/indexability evidence remain truthful during owner override?
4. Can retries/tasks change robots policy relative to the persisted ScanRun?
5. Did any change weaken WAF/rate-limit/SSRF/cap/admission/signing boundaries?
```

Resolve findings and rerun exact-head CI after any change.

---

### Task 6: Merge and guarded production acceptance

**Files:**
- No source edits unless a verified defect is found; any fix starts a new TDD cycle before merge/deploy.

**Interfaces:**
- Consumes exact green integration-head SHA.
- Produces exact merged-main SHA and production acceptance evidence.

- [ ] **Step 1: Merge only after exact-head CI and CodeRabbit are green**

Use expected-head SHA protection on the merge. If main moved materially, reconstruct/rebase and rerun CI instead of merging stale code.

- [ ] **Step 2: Require exact-main CI**

Record the merged SHA and require the push-triggered `FixList CI` to pass both jobs, including scanner image build and frozen revision verification.

- [ ] **Step 3: Verify no active release/recovery/canary conflicts**

Do not begin a new rollout while another Base44 recovery, worker promotion, or canary is active.

- [ ] **Step 4: Publish Base44 from the exact merged SHA**

Use the guarded Base44 publish/recovery path. If owner device authentication is required, stop at the human gate rather than bypassing it.

- [ ] **Step 5: Build and promote one worker candidate from the same exact merged SHA**

Build zero-traffic candidate first, verify `/health` and `/revision` source/fingerprint identity, then promote that exact revision. Do not use a default/old revision name.

- [ ] **Step 6: Run focused production acceptance**

Acceptance matrix:

```text
A. Owner-managed site previously limited only by robots.txt
   Expected: crawl proceeds past robots-disallowed pages; ScanRun records override; actual robots evidence remains visible.

B. Non-owner same/representative robots-disallowed site
   Expected: robots respected; no override.

C. Owner-managed WAF/rate-limited site
   Expected: no bypass/evasion; terminal access_limited; customer sees security-service message + allow-then-rescan action.

D. Normal accessible site
   Expected: Standard 150 behavior unchanged, cap <= 150, history/reload correct.

E. Previously targeted Bay acceptance scan
   Expected: report-quality changes from the separate Bay release candidate remain correct when that candidate is included in the release train.
```

For every run record scan ID, pages found/crawled/retained, terminal state, stored robots policy, release/source SHA, and customer-visible result.

- [ ] **Step 7: Release verdict**

GO only if production proves the owner/non-owner distinction, robots bypass is narrow, WAF remains non-bypassed, historical evidence is truthful, and there is no P0/P1 regression. Otherwise report exact blocker, evidence, smallest corrective action, and rollback path.