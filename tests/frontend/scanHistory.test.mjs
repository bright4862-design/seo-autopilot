import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPersistedScanRecord,
  hydratePersistedIssue,
  loadLatestPersistedScanRecord,
} from "../../src/lib/scanHistory.js";

function fakeBase44() {
  const calls = [];
  const project = {
    id: "project-1",
    business_name: "Example Ltd",
    website_url: "https://example.com",
    cms_platform: "WordPress",
    scan_mode: "deep",
  };
  const jobs = [
    {
      id: "job-old",
      project_id: project.id,
      status: "complete",
      completed_at: "2026-07-10T10:00:00Z",
      pages_crawled: 20,
      seo_score: 70,
    },
    {
      id: "job-new",
      project_id: project.id,
      status: "complete",
      completed_at: "2026-07-12T10:00:00Z",
      pages_found: 48,
      pages_crawled: 40,
      issues_found: 1,
      seo_score: 86,
    },
  ];
  const issue = {
    id: "issue-1",
    project_id: project.id,
    crawl_job_id: "job-new",
    category: "canonical",
    issue_title: "Review canonical URLs",
    priority: "high",
    status: "needs_developer",
    affected_pages: ["https://example.com/page"],
    details: {
      fix_id: "canonical-1",
      rule: "canonical_missing",
      source_pages: ["https://example.com/sitemap.xml"],
      page_scope: "family",
      evidence_status: "confirmed",
      who_can_do_this: "your_web_person",
    },
  };
  const page = {
    id: "page-1",
    project_id: project.id,
    crawl_job_id: "job-new",
    url: "https://example.com/page",
    status_code: 200,
    indexable: true,
  };
  const diagnostic = {
    project_id: project.id,
    crawl_job_id: "job-new",
    created_date: "2026-07-12T10:01:00Z",
    pages_found: 48,
    pages_crawled: 40,
    health_score: 86,
    crawl_warnings: ["One page could not be fully read."],
    site_summary: {
      ai_summary: "Fix the canonical family first.",
      top_actions: [{ fix_id: "canonical-1", title: "Review canonical URLs" }],
      positive_findings: ["Important pages were discovered."],
      scanner_version: "python_scanner_v2_contract_parity",
      review_version: "python_review_v1_archetype_templates",
      review: {
        scan_status: "complete_with_access_limitations",
        score_is_provisional: true,
        access_evidence_state: "partial_access_limited",
        review_confidence_state: "partial_access_needs_verification",
        ai_review_backend: "python_review_api",
        python_review_fallback_used: false,
      },
      website_health_report: {
        health_score: 86,
        health_grade: "Good",
        next_best_step: "Review the canonical family.",
      },
    },
  };

  const entity = (name, result) => ({
    filter(query, sort, limit) {
      calls.push({ name, query, sort, limit });
      return Promise.resolve(result);
    },
  });

  return {
    calls,
    client: {
      entities: {
        BusinessProject: {
          get(id) {
            calls.push({ name: "BusinessProject.get", id });
            return Promise.resolve(project);
          },
          list() {
            return Promise.resolve([project]);
          },
        },
        CrawlJob: entity("CrawlJob", jobs),
        SeoIssue: entity("SeoIssue", [issue]),
        CrawledPage: entity("CrawledPage", [page]),
        ScanDiagnostic: entity("ScanDiagnostic", [diagnostic]),
        Report: entity("Report", []),
      },
    },
  };
}

test("latest completed scan is reconstructed by crawl_job_id", async () => {
  const { client, calls } = fakeBase44();
  const record = await loadLatestPersistedScanRecord({
    base44: client,
    activeProjectId: "project-1",
  });

  assert.equal(record.storage_source, "base44");
  assert.equal(record.crawl_job_id, "job-new");
  assert.equal(record.website_url, "https://example.com");
  assert.equal(record.pages_crawled, 40);
  assert.equal(record.health_score, 86);
  assert.equal(record.scan_status, "complete_with_access_limitations");
  assert.equal(record.score_is_provisional, true);
  assert.equal(record.recommendations[0].rule, "canonical_missing");
  assert.deepEqual(record.recommendations[0].source_pages, [
    "https://example.com/sitemap.xml",
  ]);

  const issueCall = calls.find((call) => call.name === "SeoIssue");
  const pageCall = calls.find((call) => call.name === "CrawledPage");
  assert.deepEqual(issueCall.query, {
    project_id: "project-1",
    crawl_job_id: "job-new",
  });
  assert.deepEqual(pageCall.query, {
    project_id: "project-1",
    crawl_job_id: "job-new",
  });
});

test("persisted issue hydration restores authoritative evidence fields", () => {
  const hydrated = hydratePersistedIssue({
    id: "issue-2",
    category: "redirect",
    details: {
      fix_id: "redirect-2",
      rule: "redirect_chain",
      affected_pages: ["/old"],
      source_pages: ["/nav"],
      page_scope: "page",
      who_can_do_this: "your_web_person",
    },
  });

  assert.equal(hydrated.fix_id, "redirect-2");
  assert.equal(hydrated.rule, "redirect_chain");
  assert.deepEqual(hydrated.affected_pages, ["/old"]);
  assert.deepEqual(hydrated.source_pages, ["/nav"]);
  assert.equal(hydrated.page_scope, "page");
});

test("record builder preserves an authoritative zero score", () => {
  const record = buildPersistedScanRecord({
    project: { id: "project", website_url: "https://example.com" },
    job: {
      id: "job",
      status: "complete",
      completed_at: "2026-07-12T10:00:00Z",
      seo_score: 0,
      pages_crawled: 1,
    },
    issues: [],
    pages: [{ url: "https://example.com", status_code: 200 }],
    diagnostic: { health_score: 0, site_summary: {} },
  });

  assert.equal(record.health_score, 0);
  assert.equal(record.website_health_report.health_score, 0);
});
