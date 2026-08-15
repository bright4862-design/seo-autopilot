import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const auth = readFileSync("src/lib/AuthContext.jsx", "utf8");
const activeProject = readFileSync("src/lib/activeProject.js", "utf8");
const scanRuns = readFileSync("src/lib/scanRuns.js", "utf8");
const customerResult = readFileSync("base44/functions/getCustomerScanResult/index.ts", "utf8");
const scanForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const fixList = readFileSync("src/pages/FixList.jsx", "utf8");
const assistant = readFileSync("src/pages/Assistant.jsx", "utf8");
const grok = readFileSync("src/lib/grokChat.js", "utf8");
const app = readFileSync("src/App.jsx", "utf8");

const activeCustomerSources = [activeProject, scanRuns, scanForm, fixList, assistant, grok];

test("active customer routes do not read or write global scan, report, debug, Grok, or restore caches", () => {
  for (const source of [scanForm, fixList, assistant, grok]) {
    assert.doesNotMatch(source, /localStorage\.(?:getItem|setItem)/);
    assert.doesNotMatch(source, /sessionStorage\.(?:getItem|setItem)/);
  }
  assert.doesNotMatch(scanForm, /seo_autopilot:(?:last_scan|scan_history|scan_debug|active_scan|restore_pointer|grok_conversation)/);
  assert.doesNotMatch(fixList, /readBestScanRecord|loaded_local|seo_autopilot:(?:last_scan|scan_history|scan_debug|done_fixes)/);
});

test("auth expiry, logout, account switch, and project switch share one atomic boundary", () => {
  assert.match(auth, /synchronizeAuthenticatedOwner\(currentUser\?\.id\)/);
  assert.match(auth, /clearCustomerAuthBoundary\(/);
  assert.match(auth, /clearCustomerBrowserCaches\(undefined, 'logout'\)/);
  assert.match(auth, /event\?\.detail\?\.reason !== 'auth_expired'/);
  assert.match(activeProject, /readCustomerActiveProject\(user\.id\)/);
  assert.match(activeProject, /writeCustomerActiveProject\(user\.id, stableProjectId\)/);
  assert.match(activeProject, /clearCustomerAuthBoundary\(error\)/);
  assert.match(scanRuns, /clearCustomerAuthBoundary\(error\)/);
  assert.doesNotMatch(activeProject, /projects\[0\]/);
  assert.doesNotMatch(activeProject, /localStorage/);
  for (const source of [scanForm, fixList, assistant]) assert.match(source, /CUSTOMER_BOUNDARY_EVENT/);
});

test("refresh and browser history reopen only an exact owner-authorized server scan", () => {
  assert.match(fixList, /searchParams\.get\("scan_id"\)/);
  assert.match(fixList, /getScanRunWithFixList\(requestedScanId\)/);
  assert.doesNotMatch(fixList, /latest local|readBestScanRecord|loaded_local/);
  assert.match(scanRuns, /base44\.functions\.invoke\("getCustomerScanResult"/);
  assert.doesNotMatch(scanRuns.match(/export async function getScanRunWithFixList[\s\S]*?\n\}/)?.[0] || "", /entities\.(?:FixList|FixItem)/);
  assert.match(customerResult, /const exactOwner = cleanId\(run\?\.owner_user_id\) === cleanId\(user\.id\)/);
  assert.match(customerResult, /\(!exactOwner && !legacyOwner\)/);
  assert.match(customerResult, /verifyAuthoritySeal\(snapshot, secret, proof\)/);
  assert.match(scanRuns, /String\(fixList\.project_id \|\| ""\) !== projectId/);
  assert.match(scanRuns, /String\(item\.scan_run_id \|\| ""\) !== String\(run\.id \|\| ""\)/);
});

test("scan duplicate and late-response guards bind owner, project, request, scan, domain, mode, and release", () => {
  assert.match(scanForm, /submitLockRef\.current/);
  assert.match(scanForm, /requestEpochRef\.current/);
  assert.match(scanForm, /assertCurrentScanSession\(sessionIdentity, requestEpoch, requestEpochRef\)/);
  assert.match(scanForm, /ownerId: scanOwner\.id/);
  assert.match(scanForm, /projectId: scanProject\.id/);
  assert.match(scanForm, /requestId,/);
  assert.match(scanForm, /scanId,/);
  assert.match(scanForm, /normalizedDomain: normalizedScanDomain\(normalizedUrl\)/);
  assert.match(scanForm, /canonicalMode: scanMode/);
  assert.match(scanForm, /releaseIdentity: RELEASE_AUTHORITY_CONTRACT\.betaRevisionFingerprint/);
  assert.match(scanForm, /err\?\.code === "stale_customer_session"/);
  assert.match(scanForm, /requestEpochRef\.current !== requestEpoch/);
  // Review and persistence moved to the server, so their browser-side session
  // guards moved with them. The submit-path guard is what remains.
  assert.match(scanForm, /clearCustomerAuthBoundary\(err\)/);
  assert.doesNotMatch(scanForm, /clearCustomerAuthBoundary\(persistenceError\)/);
  assert.match(scanForm, /clearCustomerAuthBoundary\(err\)/);
});

test("Grok conversations and pending responses bind owner, project, scan, domain, and release", () => {
  assert.match(grok, /conversation\.owner_user_id/);
  assert.match(grok, /grokWorkspaceMatches/);
  assert.match(assistant, /workspaceIdentityRef/);
  assert.match(assistant, /assertCurrentGrokWorkspace\(workspaceAtSend, workspaceIdentityRef\.current\)/);
  assert.match(assistant, /sendError\?\.code === "stale_grok_workspace"/);
  assert.match(assistant, /workspaceEpochRef/);
  assert.match(assistant, /loadEpoch !== workspaceEpochRef\.current/);
  assert.match(assistant, /loadEpoch === workspaceEpochRef\.current/);
  assert.match(assistant, /clearCustomerAuthBoundary\(loadError\)/);
  assert.match(assistant, /clearCustomerAuthBoundary\(sendError\)/);
});

test("review scope leaves hidden legacy pages unbundled while the Standard 150 boundary remains unchanged", () => {
  assert.match(app, /path="\/reports" element=\{<Navigate to="\/dashboard" replace \/>\}/);
  assert.match(app, /path="\/crawl-status"[\s\S]*<Navigate to="\/onboarding" replace \/>/);
  assert.match(scanForm, /Scan depth: up to 150 pages · respects robots\.txt · read-only/);
  // Standard 150 is the only customer scan; Premium is not selectable today.
  assert.doesNotMatch(scanForm, /Premium · 5,000/);
  assert.doesNotMatch(scanForm, /premium_5000/);
  assert.match(activeCustomerSources.join("\n"), /releaseIdentity|release_identity/);
});
