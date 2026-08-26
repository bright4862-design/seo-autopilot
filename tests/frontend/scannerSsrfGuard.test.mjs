import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

// Modules that fetch CUSTOMER-SUPPLIED URLs. Every network read in these must
// go through security.safe_get / safe_get_once, which resolve DNS once, reject
// the hop unless every answer is public, connect to the validated IP, and keep
// Host + SNI on the original hostname. A direct client.get() here reopens the
// DNS-rebinding window: httpx would resolve a second time, and a hostile
// nameserver can answer public during validation and private during the fetch.
const CRAWL_MODULES = [
  "scanner-api/app/scanner.py",
  "scanner-api/app/sitemap.py",
  "scanner-api/app/robots_policy.py",
  "scanner-api/app/trust_discovery.py",
  "scanner-api/app/canonical_validation.py",
  "scanner-api/app/redirect_validation.py",
];

// Base44 and the Grok API are fixed, operator-configured endpoints, not
// attacker-controlled input, so they are correctly outside the crawl guard.
const NON_CRAWL_CLIENTS = ["scanner-api/app/main.py", "scanner-api/app/grok_chat.py"];

const strip = (src) =>
  src
    .split("\n")
    .filter((l) => !/^\s*#/.test(l))
    .join("\n");

test("no crawl module fetches a customer URL outside the SSRF guard", () => {
  for (const path of CRAWL_MODULES) {
    const src = strip(fs.readFileSync(path, "utf8"));
    assert.doesNotMatch(src, /\bclient\.(get|post|request|stream|head)\s*\(/,
      `${path} must fetch only through safe_get/safe_get_once`);
    assert.match(src, /safe_get(_once)?\s*\(/, `${path} must use the guarded fetch`);
  }
});

test("the SSRF guard pins one DNS snapshot and revalidates every redirect hop", () => {
  const src = fs.readFileSync("scanner-api/app/security.py", "utf8");

  // One resolution, and the whole answer set must be public — a single private
  // answer hidden among public ones rejects the hop.
  assert.match(src, /getaddrinfo\(/, "must resolve explicitly rather than let httpx do it");
  assert.match(src, /any\(not _is_public_ip\(candidate\) for candidate in addresses\)/,
    "a single non-public answer must reject the entire hop");

  // Connect to the validated IP; keep Host and SNI on the real hostname so TLS
  // verification still happens against the requested public host.
  assert.match(src, /connect_url=logical_url\.copy_with\(host=selected_ip\)/,
    "must connect to the validated numeric IP");
  assert.match(src, /"Host": resolved\.host_header/, "must send the original Host header");
  assert.match(src, /sni_hostname/, "must preserve TLS SNI");
  assert.match(src, /"Connection": "close"/,
    "a numeric-IP pool must not be reused across virtual hosts");

  // Redirects are the classic bypass: each hop must be re-resolved and bounded.
  assert.match(src, /async def safe_get\(/, "bounded redirect walker must exist");
  assert.match(src, /for _ in range\(max\(0, int\(max_redirects\)\) \+ 1\)/,
    "redirect chain must be bounded");
  assert.match(
    src,
    /response\s*=\s*await\s+safe_get_once\(\s*client,\s*current,\s*max_decoded_bytes\s*=\s*max_decoded_bytes,\s*\)/,
    "every redirect hop must be re-resolved, re-validated, and response-budgeted",
  );

  // Deny-list beyond is_global, which has classified multicast as global.
  for (const guard of ["is_private", "is_loopback", "is_link_local", "is_reserved", "is_multicast", "is_unspecified"]) {
    assert.match(src, new RegExp(`address\\.${guard}`), `must explicitly deny ${guard}`);
  }
});

test("crawl clients never let httpx follow redirects on its own", () => {
  for (const path of [...CRAWL_MODULES, ...NON_CRAWL_CLIENTS]) {
    const src = strip(fs.readFileSync(path, "utf8"));
    assert.doesNotMatch(src, /follow_redirects\s*=\s*True/,
      `${path} must not delegate redirect following to httpx, which would skip revalidation`);
  }
});
