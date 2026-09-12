import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const html = readFileSync(new URL("../../index.html", import.meta.url), "utf8");

const title = "SEO Audit Tool | Find Website Issues & Fixes | FixList";
const description = "Run an SEO audit across up to 150 pages. FixList finds crawl, indexability, redirect, metadata, and internal-link issues and shows what to fix first.";

test("homepage SEO title targets the core SEO audit query without overstating the product", () => {
  assert.match(html, new RegExp(`<title>${title.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")}</title>`));
  assert.ok(title.length <= 60, `homepage title is too long: ${title.length}`);
});

test("homepage meta description is specific, accurate, and search-snippet sized", () => {
  assert.ok(html.includes(`<meta name="description" content="${description}" />`));
  assert.ok(description.length >= 120 && description.length <= 160, `description length=${description.length}`);
});

test("Open Graph and Twitter metadata match the homepage search metadata", () => {
  assert.ok(html.includes(`<meta property="og:title" content="${title}" />`));
  assert.ok(html.includes(`<meta property="og:description" content="${description}" />`));
  assert.ok(html.includes(`<meta name="twitter:title" content="${title}" />`));
  assert.ok(html.includes(`<meta name="twitter:description" content="${description}" />`));
});
