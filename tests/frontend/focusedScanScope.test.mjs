import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  FOCUSED_SCAN_SCOPE_VERSION,
  displayPathPrefix,
  focusedPathSections,
  focusedScanFingerprintTarget,
  focusedScopeFromSearchParams,
  focusedSectionOnboardingPath,
  focusedSectionUrl,
  normalizeRequestedPathPrefix,
  normalizeScopeOrigin,
  orderFocusedScanHistory,
} from "../../src/lib/focusedScanScope.js";
import { buildScanRequestIdentity, resolveScanRunReplay } from "../../src/lib/scanRunIdentity.js";

test("focused scope normalization rejects traversal, origins, query strings, and encoded separators", () => {
  assert.equal(FOCUSED_SCAN_SCOPE_VERSION, "focused_scan_scope_v2_same_origin_path_prefix_traversal_parity");
  assert.equal(normalizeRequestedPathPrefix("/fr/"), "/fr");
  assert.equal(normalizeRequestedPathPrefix("fr/guides/"), "/fr/guides");
  assert.equal(displayPathPrefix("/fr"), "/fr/");
  assert.equal(normalizeRequestedPathPrefix("/"), "");
  assert.equal(normalizeRequestedPathPrefix("/fr?preview=1"), "");
  assert.equal(normalizeRequestedPathPrefix("/fr#top"), "");
  assert.equal(normalizeRequestedPathPrefix("/%2e%2e/private"), "");
  assert.equal(normalizeRequestedPathPrefix("/%2Fprivate"), "");
  assert.equal(normalizeRequestedPathPrefix("https://evil.example/fr"), "");
  assert.equal(normalizeRequestedPathPrefix("//evil.example/fr"), "");
});

test("focused scope keeps an exact HTTP(S) origin and never accepts credentials", () => {
  assert.equal(normalizeScopeOrigin("https://www.example.com/fr/page"), "https://www.example.com");
  assert.equal(normalizeScopeOrigin("http://example.com/path"), "http://example.com");
  assert.equal(normalizeScopeOrigin("https://user:pass@example.com/fr"), "");
  assert.equal(normalizeScopeOrigin("javascript:alert(1)"), "");
});

test("full-site and focused paths have distinct durable request identities", () => {
  const full = buildScanRequestIdentity({ websiteUrl: "https://example.com/", scanMode: "standard_150", requestId: "req-full" });
  const fr = buildScanRequestIdentity({ websiteUrl: "https://example.com/", scanMode: "standard_150", requestId: "req-fr", pathPrefix: "/fr/" });
  const en = buildScanRequestIdentity({ websiteUrl: "https://example.com/", scanMode: "standard_150", requestId: "req-en", pathPrefix: "/en/" });
  assert.equal(full.request_fingerprint, "standard_150|https://example.com/");
  assert.equal(fr.request_fingerprint, "standard_150|https://example.com/|path:/fr");
  assert.equal(en.request_fingerprint, "standard_150|https://example.com/|path:/en");
  assert.notEqual(full.request_fingerprint, fr.request_fingerprint);
  assert.notEqual(fr.request_fingerprint, en.request_fingerprint);
  const replay = resolveScanRunReplay({
    requestRuns: [],
    activeRuns: [{
      id: "full-active",
      website_url: "https://example.com/",
      scan_mode: "standard_150",
      request_fingerprint: full.request_fingerprint,
      status: "crawling",
      started_at: "2026-08-31T18:00:00.000Z",
    }],
    identity: fr,
    now: Date.parse("2026-08-31T18:01:00.000Z"),
  });
  assert.equal(replay.action, "create", "focused path must never reuse a full-site active scan");
});

test("fingerprint target retains the path scope separately from the requested URL", () => {
  assert.equal(focusedScanFingerprintTarget("https://example.com/", ""), "https://example.com/");
  assert.equal(focusedScanFingerprintTarget("https://example.com/", "/fr"), "https://example.com/|path:/fr");
});

test("onboarding scope round-trips only a same-origin path scope", () => {
  const section = { requested_origin: "https://example.com", requested_path_prefix: "/fr", discovered_from: "sitemap" };
  const pathValue = focusedSectionOnboardingPath("parent-1", section);
  assert.equal(pathValue.startsWith("/onboarding?"), true);
  const params = new URLSearchParams(pathValue.split("?")[1]);
  const scope = focusedScopeFromSearchParams(params);
  assert.deepEqual(scope, {
    scope_type: "path_prefix",
    parent_scan_id: "parent-1",
    requested_origin: "https://example.com",
    requested_path_prefix: "/fr",
    discovered_from: "sitemap",
  });
  assert.equal(focusedSectionUrl(scope), "https://example.com/fr/");
});

test("section suggestions are bounded and suppress system folders", () => {
  const sections = focusedPathSections({
    website_url: "https://example.com/",
    pages_found: 1200,
    sampling_evidence: {
      path_prefixes_discovered: { "/fr": 300, "/en": 280, "/shop": 200, "/cdn-cgi": 100, "/login": 50, "/tiny": 4 },
      path_prefixes_sampled: { "/fr": 8, "/en": 60, "/shop": 10 },
    },
  });
  assert.deepEqual(sections.map((section) => section.requested_path_prefix).sort(), ["/en", "/fr", "/shop"]);
  assert.ok(sections.every((section) => section.scope_type === "path_prefix"));
  assert.ok(sections.every((section) => section.requested_origin === "https://example.com"));
  assert.equal(sections.some((section) => section.requested_path_prefix === "/cdn-cgi"), false);
  assert.equal(sections.some((section) => section.requested_path_prefix === "/login"), false);
  assert.equal(focusedPathSections({ website_url: "https://example.com", pages_found: 120 }).length, 0);
});

test("focused children are displayed immediately after their durable parent", () => {
  const scans = [
    { id: "new-root", occurredAt: "2026-08-31T19:00:00Z" },
    { id: "child-fr", parent_scan_id: "parent", occurredAt: "2026-08-31T18:30:00Z" },
    { id: "parent", occurredAt: "2026-08-31T18:00:00Z" },
    { id: "child-en", parent_scan_id: "parent", occurredAt: "2026-08-31T18:40:00Z" },
  ];
  assert.deepEqual(orderFocusedScanHistory(scans).map((scan) => scan.id), ["new-root", "parent", "child-en", "child-fr"]);
});

test("server admission requires owned discovered parent scope and does not enable subdomains", () => {
  const source = fs.readFileSync("base44/functions/startStandardScanJob/entry.ts", "utf8");
  const schema = JSON.parse(fs.readFileSync("base44/entities/ScanRun.jsonc", "utf8"));
  assert.equal(source.includes("buildAdmissionFingerprint(websiteUrl, scope?.pathPrefix || \"\")"), true);
  assert.equal(source.includes("scopeType !== \"path_prefix\""), true);
  assert.equal(source.includes("body.user_confirmed !== true"), true);
  assert.equal(source.includes("String(parent.owner_user_id || \"\") !== String(user.id)"), true);
  assert.equal(source.includes("String(parent.project_id || \"\") !== String(project.id)"), true);
  assert.equal(source.includes("focused_scope_not_discovered"), true);
  assert.equal(source.includes("scanMatchesRequestedScope(row, scope)"), true);
  assert.equal(source.includes("focused_parent_must_be_full_site"), true);
  assert.equal(source.includes('raw.replace(/^\\/+/, "").split("/")'), true);
  assert.equal(source.includes('rawDecoded === ".."'), true);
  assert.equal(source.includes("scope_type: \"subdomain\""), false);
  assert.deepEqual(schema.properties.scope_type.enum, ["", "path_prefix"]);
  assert.deepEqual(schema.properties.discovered_from.enum, ["", "sitemap", "internal_link", "canonical", "hreflang"]);
  assert.equal(schema.properties.user_confirmed.type, "boolean");
  for (const field of ["parent_scan_id", "requested_origin", "requested_path_prefix"]) assert.equal(schema.properties[field].type, "string");
});

test("focused scope is bound into authoritative and limited result proofs", () => {
  const authority = fs.readFileSync("base44/functions/persistDurableScanAuthority/authoritySnapshot.js", "utf8");
  const authorityWriter = fs.readFileSync("base44/functions/persistDurableScanAuthority/entry.ts", "utf8");
  const limited = fs.readFileSync("base44/functions/persistLimitedScanResult/limitedResultIntegrity.js", "utf8");
  const limitedWriter = fs.readFileSync("base44/functions/persistLimitedScanResult/entry.ts", "utf8");
  const reader = fs.readFileSync("base44/functions/getCustomerScanResult/entry.ts", "utf8");
  const readerIntegrity = fs.readFileSync("base44/functions/getCustomerScanResult/limitedResultIntegrity.js", "utf8");
  assert.equal(authority.includes("standard_review_snapshot_hmac_v4_focused_scope"), true);
  assert.equal(authority.includes("requested_path_prefix"), true);
  assert.equal(authorityWriter.includes("scope_type: String(scan.scope_type || \"\")"), true);
  assert.equal(authorityWriter.includes("scan: authorityScanResult"), true);
  assert.equal(limited.includes("standard_limited_result_integrity_v4_focused_scope_effective_path"), true);
  assert.equal(limited.includes("requested_path_prefix"), true);
  assert.equal(limited.includes("effective_path_prefix"), true);
  assert.equal(limitedWriter.includes("scope_type: String(scan.scope_type || \"\")"), true);
  assert.equal(reader.includes("standard_review_snapshot_hmac_v4_focused_scope"), true);
  assert.equal(reader.includes("standard_limited_result_integrity_v4_focused_scope_effective_path"), true);
  assert.equal(readerIntegrity.includes("standard_limited_result_integrity_v4_focused_scope_effective_path"), true);
  assert.equal(readerIntegrity.includes("effective_path_prefix"), true);
  const projection = fs.readFileSync("base44/functions/getCustomerScanResult/projection.js", "utf8");
  assert.equal(projection.includes('"standard_limited_result_integrity_v4_focused_scope_effective_path"'), true);
});
