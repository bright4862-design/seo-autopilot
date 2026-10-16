// Source-only audit for demonstrated getfixlist.com serving requirements.
//
// This does not claim anything about deployed HTTP behavior. In particular,
// soft-404 behavior requires an actual released-runtime observation and is
// deliberately reported as not_assessed here.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const read = (relative) => fs.readFileSync(path.join(ROOT, relative), "utf8");

function unique(values) {
  return [...new Set(values)];
}

function publicRoutesFromApp(source) {
  const beforeAuth = source.split("{/* Authenticated app */}")[0] || source;
  return unique([...beforeAuth.matchAll(/<Route\s+path="([^"]+)"/g)].map((match) => match[1]));
}

function sitemapLocs(source) {
  return unique([...source.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1].trim()));
}

export function auditOwnSiteSource() {
  const index = read("index.html");
  const robots = read("public/robots.txt");
  const sitemap = read("public/sitemap.xml");
  const app = read("src/App.jsx");

  const title = index.match(/<title>([^<]+)<\/title>/)?.[1]?.trim() || "";
  const description = index.match(/<meta\s+name="description"\s+content="([^"]+)"\s*\/>/)?.[1]?.trim() || "";
  const canonical = index.match(/<link\s+rel="canonical"\s+href="([^"]+)"\s*\/>/)?.[1]?.trim() || "";
  const publicRoutes = publicRoutesFromApp(app);
  const locs = sitemapLocs(sitemap);

  const metadataFailures = [];
  if (!title || !/FixList/.test(title)) metadataFailures.push("home title missing FixList identity");
  if (!description || description.length < 70) metadataFailures.push("home meta description missing or too weak");
  if (canonical !== "https://getfixlist.com/") metadataFailures.push("home canonical is not exact getfixlist root");

  const sitemapFailures = [];
  if (!/^User-agent:\s*\*/m.test(robots) || !/^Allow:\s*\/\s*$/m.test(robots)) {
    sitemapFailures.push("robots.txt does not explicitly allow the public site");
  }
  if (!/^Sitemap:\s*https:\/\/getfixlist\.com\/sitemap\.xml\s*$/m.test(robots)) {
    sitemapFailures.push("robots.txt does not declare the canonical sitemap");
  }
  for (const required of ["https://getfixlist.com/", "https://getfixlist.com/blog"]) {
    if (!locs.includes(required)) sitemapFailures.push(`sitemap is missing ${required}`);
  }
  for (const forbidden of ["/login", "/register", "/forgot-password", "/reset-password", "/dashboard", "/onboarding", "/billing", "/account"]) {
    if (locs.includes(`https://getfixlist.com${forbidden}`)) sitemapFailures.push(`sitemap exposes non-indexable/account route ${forbidden}`);
  }
  if (!publicRoutes.includes("/") || !publicRoutes.includes("/blog")) sitemapFailures.push("source router does not expose required sitemap routes");

  return {
    version: "getfixlist_source_serving_audit_v1",
    scope: "source_only",
    metadata: {
      status: metadataFailures.length ? "failed" : "pass",
      failures: metadataFailures,
      title,
      description,
      canonical,
    },
    sitemap: {
      status: sitemapFailures.length ? "failed" : "pass",
      failures: sitemapFailures,
      locations: locs,
      declared_in_robots: /^Sitemap:\s*https:\/\/getfixlist\.com\/sitemap\.xml\s*$/m.test(robots),
    },
    soft_404: {
      status: "not_assessed",
      reason: "requires deployed exact-source runtime observation; source files cannot prove HTTP fallback behavior",
    },
    deployment_verified: false,
  };
}
