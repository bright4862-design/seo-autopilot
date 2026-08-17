import assert from "node:assert/strict";
import test from "node:test";

import {
  CUSTOMER_CACHE_VERSION,
  CUSTOMER_LOCAL_STORAGE_KEYS,
  CUSTOMER_LOCAL_STORAGE_PREFIXES,
  CUSTOMER_SESSION_STORAGE_KEYS,
  clearCustomerAuthBoundary,
  clearCustomerBrowserCaches,
  clearCustomerProjectCaches,
  clearLegacyCustomerCaches,
  createResponseGuard,
  customerCacheKey,
  customerIdentityMatches,
  readCustomerActiveProject,
  readCustomerCache,
  synchronizeAuthenticatedOwner,
  writeCustomerActiveProject,
  writeCustomerCache,
} from "../../src/lib/customerBrowserCache.js";

class MemoryStorage {
  #values = new Map();
  constructor(entries = {}) { for (const [key, value] of Object.entries(entries)) this.setItem(key, value); }
  get length() { return this.#values.size; }
  key(index) { return [...this.#values.keys()][index] ?? null; }
  getItem(key) { return this.#values.get(String(key)) ?? null; }
  setItem(key, value) { this.#values.set(String(key), String(value)); }
  removeItem(key) { this.#values.delete(String(key)); }
}

function browser() {
  return { localStorage: new MemoryStorage(), sessionStorage: new MemoryStorage() };
}

const identityA = {
  ownerId: "owner-a",
  projectId: "project-a",
  requestId: "request-a",
  scanId: "scan-a",
  normalizedDomain: "https://www.alpha.example/path",
  canonicalMode: "standard_150",
  releaseIdentity: "release-1",
};
const identityB = { ...identityA, ownerId: "owner-b", requestId: "request-b", scanId: "scan-b" };


test("logout inventory covers every account-specific browser cache used by the app", () => {
  for (const required of [
    "active_project_id", "seo_autopilot:last_scan", "seo_autopilot:scan_history",
    "seo_autopilot:active_scan_id", "seo_autopilot:scan_debug",
    "seo_autopilot:restore_pointer", "seo_autopilot:grok_conversation",
    "seo_autopilot:pending_request",
  ]) assert.ok(CUSTOMER_LOCAL_STORAGE_KEYS.includes(required), `${required} missing`);
  assert.deepEqual(CUSTOMER_LOCAL_STORAGE_PREFIXES, ["seo_autopilot:scan:", "seo_autopilot:customer:"]);
  assert.ok(CUSTOMER_SESSION_STORAGE_KEYS.includes("seo_autopilot:active_request"));
  assert.ok(CUSTOMER_SESSION_STORAGE_KEYS.includes("seo_autopilot:pending_callbacks"));
});

test("logout cleanup removes every account-specific FixList cache", () => {
  const localStorage = new MemoryStorage(Object.fromEntries(CUSTOMER_LOCAL_STORAGE_KEYS.map((key) => [key, `private:${key}`])));
  localStorage.setItem("seo_autopilot:scan:run_account_a", "private scan A");
  localStorage.setItem(customerCacheKey("scan", identityA), "private scoped A");
  localStorage.setItem("base44_access_token", "sdk-managed-token");
  localStorage.setItem("unrelated_preference", "keep-me");
  const sessionStorage = new MemoryStorage(Object.fromEntries(CUSTOMER_SESSION_STORAGE_KEYS.map((key) => [key, "private event"])));
  sessionStorage.setItem("unrelated_session_value", "keep-me-too");
  clearCustomerBrowserCaches({ localStorage, sessionStorage });
  for (const key of CUSTOMER_LOCAL_STORAGE_KEYS) assert.equal(localStorage.getItem(key), null);
  assert.equal(localStorage.getItem("seo_autopilot:scan:run_account_a"), null);
  assert.equal(localStorage.getItem(customerCacheKey("scan", identityA)), null);
  for (const key of CUSTOMER_SESSION_STORAGE_KEYS) assert.equal(sessionStorage.getItem(key), null);
  assert.equal(localStorage.getItem("base44_access_token"), "sdk-managed-token");
  assert.equal(localStorage.getItem("unrelated_preference"), "keep-me");
  assert.equal(sessionStorage.getItem("unrelated_session_value"), "keep-me-too");
});

test("owner and project namespaces prevent same-browser account leakage", () => {
  const win = browser();
  assert.equal(writeCustomerCache("scan", { score: 88 }, identityA, win), true);
  assert.deepEqual(readCustomerCache("scan", identityA, win), { score: 88 });
  assert.equal(readCustomerCache("scan", identityB, win), null);
  const projectB = { ...identityA, projectId: "project-b" };
  assert.equal(readCustomerCache("scan", projectB, win), null);
});

test("exact restoration rejects request, scan, domain, mode, and release mismatches", () => {
  const win = browser();
  writeCustomerCache("scan", { score: 91 }, identityA, win);
  for (const mismatch of [
    { requestId: "other-request" }, { scanId: "other-scan" },
    { normalizedDomain: "beta.example" }, { canonicalMode: "premium_5000" },
    { releaseIdentity: "release-2" },
  ]) assert.equal(readCustomerCache("scan", { ...identityA, ...mismatch }, win), null);
});

test("invalid or legacy cache envelopes are deleted instead of restored", () => {
  const win = browser();
  const key = customerCacheKey("scan", identityA);
  win.localStorage.setItem(key, JSON.stringify({ cache_version: CUSTOMER_CACHE_VERSION - 1, identity: identityA, value: { score: 1 } }));
  assert.equal(readCustomerCache("scan", identityA, win), null);
  assert.equal(win.localStorage.getItem(key), null);
  win.localStorage.setItem(key, "not-json");
  assert.equal(readCustomerCache("scan", identityA, win), null);
  assert.equal(win.localStorage.getItem(key), null);
});

test("project switch clears only the exact owner-project namespace and pending callbacks", () => {
  const win = browser();
  const projectB = { ...identityA, projectId: "project-b", requestId: "request-b", scanId: "scan-b" };
  writeCustomerCache("scan", { owner: "A" }, identityA, win);
  writeCustomerCache("scan", { owner: "A project B" }, projectB, win);
  win.sessionStorage.setItem("seo_autopilot:pending_callbacks", "pending A");
  clearCustomerProjectCaches(identityA, win);
  assert.equal(readCustomerCache("scan", identityA, win), null);
  assert.deepEqual(readCustomerCache("scan", projectB, win), { owner: "A project B" });
  assert.equal(win.sessionStorage.getItem("seo_autopilot:pending_callbacks"), null);
});

test("late responses are rejected after logout, account switch, project switch, or new request", () => {
  const guard = createResponseGuard(identityA);
  assert.equal(guard.accepts(identityA, identityA), true);
  assert.equal(guard.accepts(identityA, identityB), false);
  assert.equal(guard.accepts(identityA, { ...identityA, projectId: "project-b" }), false);
  assert.equal(guard.accepts({ ...identityA, requestId: "late-a" }, identityA), false);
  guard.cancel();
  assert.equal(guard.accepts(identityA, identityA), false);
});

test("identity comparison normalizes domains but requires every authority field", () => {
  assert.equal(customerIdentityMatches(identityA, { ...identityA, normalizedDomain: "alpha.example" }), true);
  assert.equal(customerIdentityMatches({ ...identityA, releaseIdentity: "" }, identityA), false);
  assert.equal(customerIdentityMatches(identityA, { ...identityA, scanId: "" }), false);
});


test("active project pointers are owner scoped and global pointers are deleted", () => {
  const win = browser();
  win.localStorage.setItem("active_project_id", "project-from-other-account");
  assert.equal(writeCustomerActiveProject("owner-a", "project-a", win), true);
  assert.equal(readCustomerActiveProject("owner-a", win), "project-a");
  assert.equal(readCustomerActiveProject("owner-b", win), "");
  assert.equal(win.localStorage.getItem("active_project_id"), null);
});

test("authentication owner synchronization clears legacy and cross-account state", () => {
  const win = browser();
  win.localStorage.setItem("seo_autopilot:last_scan", "legacy");
  win.localStorage.setItem("seo_autopilot:scan:old", "legacy scan");
  assert.equal(synchronizeAuthenticatedOwner("owner-a", win), true);
  assert.equal(win.localStorage.getItem("seo_autopilot:last_scan"), null);
  assert.equal(win.localStorage.getItem("seo_autopilot:scan:old"), null);
  writeCustomerCache("scan", { owner: "a" }, identityA, win);
  assert.equal(synchronizeAuthenticatedOwner("owner-a", win), true);
  assert.deepEqual(readCustomerCache("scan", identityA, win), { owner: "a" });
  assert.equal(synchronizeAuthenticatedOwner("owner-b", win), true);
  assert.equal(readCustomerCache("scan", identityA, win), null);
  assert.doesNotThrow(() => clearLegacyCustomerCaches(win));
});

test("only 401 clears protected session state; 403 permission refusals keep the customer signed in", () => {
  const expired = browser();
  writeCustomerCache("scan", { owner: "a" }, identityA, expired);
  assert.equal(clearCustomerAuthBoundary({ status: 401 }, expired), true);
  assert.equal(readCustomerCache("scan", identityA, expired), null);

  for (const error of [{ status: 403 }, { response: { status: 403 } }, { status: 500 }]) {
    const win = browser();
    writeCustomerCache("scan", { owner: "a" }, identityA, win);
    assert.equal(clearCustomerAuthBoundary(error, win), false);
    assert.deepEqual(readCustomerCache("scan", identityA, win), { owner: "a" });
  }
});

test("cache cleanup is safe when browser storage is unavailable", () => {
  assert.doesNotThrow(() => clearCustomerBrowserCaches(undefined));
  assert.doesNotThrow(() => clearCustomerBrowserCaches({}));
  assert.doesNotThrow(() => clearCustomerBrowserCaches({
    get localStorage() { throw new DOMException("Storage disabled", "SecurityError"); },
    get sessionStorage() { throw new DOMException("Storage disabled", "SecurityError"); },
  }));
});
