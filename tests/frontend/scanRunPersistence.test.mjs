import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildAuthorityMarkers,
  buildDiagnosticAuthorityMarkers,
  buildFixItemFields,
  buildFixListFields,
  buildScanRunFields,
  deriveTerminalStatus,
  fixLineageKey,
  getFixRecommendations,
} from "../../src/lib/scanRunModel.js";

const frozenRevision = JSON.parse(readFileSync("data/beta-crawler-revision.json", "utf8"));
const EXPECTED_SCANNER_VERSION = "python_scanner_v3_bounded_request";
const EXPECTED_REVIEW_VERSION = "python_review_v2_structural_marketplace";
const EXPECTED_CALIBRATION_VERSION = "review_evidence_calibration_v6_health_score_v2";
const EXPECTED_BETA_FINGERPRINT = RELEASE_FINGERPRINT;
const EXPECTED_CLASSIFIER_VERSION = "archetype_classifier_v9_local_business_hospitality";
const EXPECTED_SCANNER_BUILD = "authenticated_health_probe_v1";
const EXPECTED_METADATA_VERSION = "metadata_evidence_v1_description_states";
const EXPECTED_TITLE_VERSION = "title_evidence_v1_contextual_duplicates";

test("complete scans persist as complete", () => {
  assert.equal(deriveTerminalStatus({ scan_status: "complete" }), "complete");
  assert.equal(deriveTerminalStatus({ scan_status: "complete_no_high_confidence_findings" }), "complete");
});

test("limited or provisional evidence never persists as complete", () => {
  assert.equal(deriveTerminalStatus({ scan_status: "complete_with_access_limitations" }), "limited");
  assert.equal(deriveTerminalStatus({ scan_status: "incomplete_evidence" }), "limited");
  assert.equal(deriveTerminalStatus({ scan_status: "inconclusive_insufficient_evidence" }), "limited");
  assert.equal(deriveTerminalStatus({ scan_status: "blocked_or_incomplete" }), "limited");
  assert.equal(deriveTerminalStatus({ scan_status: "complete", score_is_provisional: true }), "limited");
});

test("lineage key is stable across scans and distinguishes page-scoped findings", () => {
  const familyFix = { rule: "missing_title", page_scope: "family", page_template_family: "blog" };
  assert.equal(fixLineageKey(familyFix), fixLineageKey({ ...familyFix, affected_pages: ["/a", "/b"] }));

  const pageFixA = { rule: "missing_title", page_scope: "page", page_url: "/pricing" };
  const pageFixB = { rule: "missing_title", page_scope: "page", page_url: "/about" };
  assert.notEqual(fixLineageKey(pageFixA), fixLineageKey(pageFixB));
});

test("fix list counts preserve raw priorities without narrowing critical to high", () => {
  const record = {
    website_url: "https://example.com",
    scanner_version: EXPECTED_SCANNER_VERSION,
    scanner_build_revision: EXPECTED_SCANNER_BUILD,
    advanced_scan_backend: "python_scanner_api",
    deno_fallback_used: false,
    archetype_classifier_version: EXPECTED_CLASSIFIER_VERSION,
    ai_review_backend: "python_review_api",
    python_review_fallback_used: false,
    review_version: EXPECTED_REVIEW_VERSION,
    review_evidence_calibration_version: EXPECTED_CALIBRATION_VERSION,
    beta_revision_fingerprint: EXPECTED_BETA_FINGERPRINT,
    recommendations: [
      { fix_id: "f1", priority: "critical" },
      { fix_id: "f2", priority: "high" },
      { fix_id: "f3", priority: "low" },
      { fix_id: "f4" },
    ],
  };
  const fields = buildFixListFields(record);
  assert.equal(fields.total_fixes, 4);
  assert.equal(fields.critical_count, 1);
  assert.equal(fields.high_count, 1);
  assert.equal(fields.medium_count, 1);
  assert.equal(fields.low_count, 1);
  assert.equal(fields.is_authoritative, true);
  assert.deepEqual(fields.top_action_fix_ids, ["f1", "f2", "f3"]);
});

test("fallback reviews are not marked authoritative", () => {
  const fields = buildFixListFields({ ai_review_backend: "python_review_api", python_review_fallback_used: true });
  assert.equal(fields.is_authoritative, false);
});

test("fix items carry lineage from the previous run", () => {
  const previousItems = [
    {
      rule: "missing_title",
      page_scope: "family",
      page_template_family: "blog",
      scan_run_id: "run_1",
      first_seen_scan_run_id: "run_0",
    },
  ];
  const carried = buildFixItemFields(
    { rule: "missing_title", page_scope: "family", page_template_family: "blog", issue_title: "Add titles" },
    { scanRunId: "run_2", previousItems }
  );
  assert.equal(carried.carried_over, true);
  assert.equal(carried.first_seen_scan_run_id, "run_0");

  const fresh = buildFixItemFields(
    { rule: "broken_link", page_scope: "page", page_url: "/x", issue_title: "Fix link" },
    { scanRunId: "run_2", previousItems }
  );
  assert.equal(fresh.carried_over, false);
  assert.equal(fresh.first_seen_scan_run_id, "run_2");
});

test("fix items keep contract enums valid and preserve the raw finding", () => {
  const finding = { issue_title: "X", priority: "urgent", page_scope: "galaxy", custom_field: 1 };
  const fields = buildFixItemFields(finding, { scanRunId: "run_1" });
  assert.equal(fields.priority, "medium");
  assert.equal(fields.page_scope, "page");
  assert.equal(fields.user_status, "open");
  assert.deepEqual(fields.raw_finding, finding);
});

test("scan run fields map coverage and evidence state from the merged record", () => {
  const fields = buildScanRunFields({
    scan_status: "complete_with_access_limitations",
    score_is_provisional: true,
    pages_crawled: 42,
    pages_retained: 12,
    local_cache_complete: false,
    pages_found: 80,
    health_score: 71,
    limitation: "rate limited",
  });
  assert.equal(fields.status, "limited");
  assert.equal(fields.pages_crawled, 42);
  assert.equal(fields.pages_retained, 12);
  assert.equal(fields.local_cache_complete, false);
  assert.equal(fields.health_score, 71);
  assert.equal(fields.score_is_provisional, true);
  assert.equal(fields.limitation, "rate limited");
});

test("an explicit review veto cannot be inferred back into release eligibility", () => {
  const fields = buildScanRunFields({
    release_gate_eligible: false,
    scanner_version: "python_scanner_v3_bounded_request",
    advanced_scan_backend: "python_scanner_api",
    ai_review_backend: "python_review_api",
    python_review_fallback_used: false,
    review_version: "python_review_v2_structural_marketplace",
    review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
  });
  assert.equal(fields.release_gate_eligible, false);
});

test("durable authority markers ignore polish versions and retain v9 evidence provenance", () => {
  assert.equal(frozenRevision.fingerprint, EXPECTED_BETA_FINGERPRINT);
  const mergedMarkers = buildAuthorityMarkers(
    {
      scanner_build_revision: EXPECTED_SCANNER_BUILD,
      beta_revision_fingerprint: EXPECTED_BETA_FINGERPRINT,
      metadata_evidence_version: EXPECTED_METADATA_VERSION,
      title_evidence_version: EXPECTED_TITLE_VERSION,
    },
    {
      archetype_classifier_version: EXPECTED_CLASSIFIER_VERSION,
      review_version: EXPECTED_REVIEW_VERSION,
      review_evidence_calibration_version: EXPECTED_CALIBRATION_VERSION,
      beta_revision_fingerprint: EXPECTED_BETA_FINGERPRINT,
      review_polish_version: "python_review_v2_group_dedup",
      group_dedup_version: "python_review_v2_group_dedup",
    }
  );
  assert.deepEqual(mergedMarkers, {
    scanner_build_revision: EXPECTED_SCANNER_BUILD,
    archetype_classifier_version: EXPECTED_CLASSIFIER_VERSION,
    review_version: EXPECTED_REVIEW_VERSION,
    review_evidence_calibration_version: EXPECTED_CALIBRATION_VERSION,
    beta_revision_fingerprint: EXPECTED_BETA_FINGERPRINT,
    metadata_evidence_version: EXPECTED_METADATA_VERSION,
    title_evidence_version: EXPECTED_TITLE_VERSION,
  });

  const fields = buildScanRunFields({
    ...mergedMarkers,
    ai_review_backend: "python_review_api",
    review_polish_version: "python_review_v2_group_dedup",
    group_dedup_version: "python_review_v2_group_dedup",
  });
  assert.equal(fields.review_version, EXPECTED_REVIEW_VERSION);
  assert.equal(fields.review_evidence_calibration_version, EXPECTED_CALIBRATION_VERSION);
  assert.equal(fields.beta_revision_fingerprint, EXPECTED_BETA_FINGERPRINT);
  assert.equal(fields.scanner_build_revision, EXPECTED_SCANNER_BUILD);
  assert.equal(fields.metadata_evidence_version, EXPECTED_METADATA_VERSION);
  assert.equal(fields.title_evidence_version, EXPECTED_TITLE_VERSION);

  assert.deepEqual(buildDiagnosticAuthorityMarkers(mergedMarkers), mergedMarkers);
});

test("missing beta fingerprints stay missing across merged, durable, and diagnostic records", () => {
  const mergedMarkers = buildAuthorityMarkers(
    { scanner_build_revision: EXPECTED_SCANNER_BUILD },
    {
      archetype_classifier_version: EXPECTED_CLASSIFIER_VERSION,
      review_version: EXPECTED_REVIEW_VERSION,
      review_evidence_calibration_version: EXPECTED_CALIBRATION_VERSION,
    }
  );
  assert.equal(mergedMarkers.beta_revision_fingerprint, "");
  assert.notEqual(mergedMarkers.beta_revision_fingerprint, "fa1602737697ae98");

  const fields = buildScanRunFields({ ...mergedMarkers, ai_review_backend: "python_review_api" });
  assert.equal(fields.beta_revision_fingerprint, "");

  const diagnostic = buildDiagnosticAuthorityMarkers(mergedMarkers);
  assert.equal(diagnostic.beta_revision_fingerprint, "");
});

test("recommendations are found under any of the contract array keys", () => {
  assert.equal(getFixRecommendations({ recommendations: [{ a: 1 }] }).length, 1);
  assert.equal(getFixRecommendations({ fixes: [{ a: 1 }] }).length, 1);
  assert.equal(getFixRecommendations({ findings: [{ a: 1 }, null] }).length, 1);
  assert.equal(getFixRecommendations({}).length, 0);
});


test("grouped metadata evidence persists as first-class FixItem fields", () => {
  const fields = buildFixItemFields({
    issue_title: "Add usable meta descriptions",
    rule: "meta_description_unusable",
    page_scope: "family",
    page_template_family: "activity_detail",
    affected_pages: ["/a", "/b", "/c"],
    metadata_state_counts: { missing: 1, empty: 2, malformed: 0 },
    combined_rules: ["missing_meta_description", "empty_meta_description"],
    grouping_explanation: "These URLs use the activity/detail page pattern.",
  }, { scanRunId: "run_grouped" });

  assert.deepEqual(fields.metadata_state_counts, { missing: 1, empty: 2, malformed: 0 });
  assert.deepEqual(fields.combined_rules, ["missing_meta_description", "empty_meta_description"]);
  assert.equal(fields.grouping_explanation, "These URLs use the activity/detail page pattern.");
});


test("evidence quality fields persist and block release authority defensively", () => {
  const fields = buildScanRunFields({
    scan_mode: "advanced",
    scan_status: "complete",
    score_is_provisional: false,
    scanner_version: EXPECTED_SCANNER_VERSION,
    scanner_build_revision: EXPECTED_SCANNER_BUILD,
    advanced_scan_backend: "python_scanner_api",
    deno_fallback_used: false,
    archetype_classifier_version: EXPECTED_CLASSIFIER_VERSION,
    ai_review_backend: "python_review_api",
    python_review_fallback_used: false,
    review_version: EXPECTED_REVIEW_VERSION,
    review_evidence_calibration_version: EXPECTED_CALIBRATION_VERSION,
    beta_revision_fingerprint: EXPECTED_BETA_FINGERPRINT,
    evidence_quality_state: "insufficient_discovery",
    evidence_quality_score: 35,
    evidence_quality_reasons: ["default_route_dominance"],
    discovery_quality_state: "default_route_dominated",
    representative_html_page_count: 2,
    usable_html_page_count: 5,
    default_route_page_count: 3,
    evidence_quality_blocking: true,
    evidence_quality_gate_version: "evidence_quality_gate_v1_default_route_dominance",
  });

  assert.equal(fields.release_gate_eligible, false);
  assert.equal(fields.evidence_quality_state, "insufficient_discovery");
  assert.equal(fields.evidence_quality_score, 35);
  assert.deepEqual(fields.evidence_quality_reasons, ["default_route_dominance"]);
  assert.equal(fields.discovery_quality_state, "default_route_dominated");
  assert.equal(fields.representative_html_page_count, 2);
  assert.equal(fields.usable_html_page_count, 5);
  assert.equal(fields.default_route_page_count, 3);
  assert.equal(fields.evidence_quality_blocking, true);
});
