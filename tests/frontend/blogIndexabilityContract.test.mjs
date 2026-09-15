import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const sitemapPath = "public/sitemap.xml";
const blogArticleSource = readFileSync("src/pages/BlogArticle.jsx", "utf8");

const publishedBlogSlugs = [
  "what-to-fix-first-after-an-seo-audit",
  "technical-seo-audit-checklist",
  "technical-seo-audit-service",
  "ecommerce-seo-audit",
];

test("the public sitemap includes every currently published blog article URL", () => {
  assert.ok(existsSync(sitemapPath), "public/sitemap.xml must exist in source control");
  const sitemap = readFileSync(sitemapPath, "utf8");
  for (const slug of publishedBlogSlugs) {
    assert.match(sitemap, new RegExp(`<loc>https://getfixlist\\.com/blog/${slug}</loc>`));
  }
});

test("blog articles publish a self-referencing canonical and article-specific social URL", () => {
  assert.match(blogArticleSource, /rel["']?,\s*["']canonical["']/);
  assert.match(blogArticleSource, /https:\/\/getfixlist\.com\/blog\/\$\{slug\}/);
  assert.match(blogArticleSource, /property["']?,\s*["']og:url["']/);
});
