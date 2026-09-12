import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

function source(path) {
  return existsSync(path) ? readFileSync(path, "utf8") : "";
}

const appSource = source("src/App.jsx");
const landingSource = source("src/pages/Landing.jsx");
const previewSource = source("src/components/blog/BlogPreview.jsx");
const blogSource = source("src/pages/Blog.jsx");
const articleSource = source("src/pages/BlogArticle.jsx");
const publisherSource = source("base44/functions/generateDailyBlog/entry.ts");
const publisherConfig = source("base44/functions/generateDailyBlog/function.jsonc");

test("blog index and article routes are public, not nested behind ProtectedRoute", () => {
  assert.match(appSource, /import Blog from ["']@\/pages\/Blog["']/);
  assert.match(appSource, /import BlogArticle from ["']@\/pages\/BlogArticle["']/);

  const blogRoute = appSource.indexOf('path="/blog"');
  const articleRoute = appSource.indexOf('path="/blog/:slug"');
  const protectedRoute = appSource.indexOf("<ProtectedRoute");

  assert.notEqual(blogRoute, -1, "expected a public /blog route");
  assert.notEqual(articleRoute, -1, "expected a public /blog/:slug route");
  assert.ok(blogRoute < protectedRoute, "/blog must appear before ProtectedRoute");
  assert.ok(articleRoute < protectedRoute, "/blog/:slug must appear before ProtectedRoute");
});

test("the existing landing page visibly links to the blog and previews recent posts before FAQ", () => {
  assert.match(landingSource, /to="\/blog"[^>]*>[\s\S]*?Blog[\s\S]*?<\/Link>/);
  assert.match(landingSource, /import BlogPreview from ["']@\/components\/blog\/BlogPreview["']/);
  const preview = landingSource.indexOf("<BlogPreview");
  const faq = landingSource.indexOf('id="faq"');
  assert.notEqual(preview, -1, "expected BlogPreview on Landing");
  assert.notEqual(faq, -1, "expected FAQ section on Landing");
  assert.ok(preview < faq, "Latest from FixList must render before FAQ");
});

test("landing preview exposes only the three newest published articles", () => {
  assert.ok(previewSource, "BlogPreview.jsx must exist");
  assert.match(previewSource, /BlogPost\.filter\(\s*\{\s*status:\s*["']published["']\s*\}/);
  assert.match(previewSource, /["']-published_at["']/);
  assert.match(previewSource, /,\s*3\s*,?\s*\)/);
  assert.match(previewSource, /Latest from FixList/);
  assert.match(previewSource, /to=\{`\/blog\/\$\{post\.slug\}`\}/);
});

test("public blog index lists only published posts and links by slug", () => {
  assert.ok(blogSource, "Blog.jsx must exist");
  assert.match(blogSource, /BlogPost\.filter\(\s*\{\s*status:\s*["']published["']\s*\}/);
  assert.match(blogSource, /["']-published_at["']/);
  assert.match(blogSource, /to=\{`\/blog\/\$\{post\.slug\}`\}/);
});

test("article route only renders a matching published slug as Markdown", () => {
  assert.ok(articleSource, "BlogArticle.jsx must exist");
  assert.match(articleSource, /useParams\(\)/);
  assert.match(articleSource, /BlogPost\.filter\(\s*\{\s*slug,\s*status:\s*["']published["']\s*\}/);
  assert.match(articleSource, /ReactMarkdown/);
  assert.match(articleSource, /document\.title/);
  assert.match(articleSource, /meta\[name=["']description["']\]/);
});

test("public blog surfaces do not advertise unreleased product modes", () => {
  for (const [name, value] of [
    ["landing", landingSource],
    ["preview", previewSource],
    ["blog", blogSource],
    ["article", articleSource],
  ]) {
    assert.doesNotMatch(value, /Grok|Premium 5,?000|premium_5000/i, `${name} leaked an unreleased mode`);
  }
});

test("daily publisher is idempotent, quality gated, scheduled, and scanner-isolated", () => {
  assert.match(publisherSource, /generationKey\s*=\s*`daily:\$\{dayKey\}`/);
  assert.match(publisherSource, /wordCount\(bodyMarkdown\)\s*<\s*800/);
  assert.match(publisherSource, /status:\s*["']published["']/);
  assert.match(publisherConfig, /"cron_expression"\s*:\s*"0 12 \* \* \*"/);
  assert.match(publisherConfig, /"is_active"\s*:\s*true/);

  assert.doesNotMatch(
    publisherSource,
    /runStandard150Scan|startStandardScanJob|runAdvancedScan|scanAdmission|persistDurableScanAuthority|persistLimitedScanResult|durableScanWorkerControl/,
  );
});
