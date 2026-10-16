import assert from "node:assert/strict";
import test from "node:test";

import { buildGeoReadinessPresentation } from "../../src/lib/geoReadinessPresentation.js";
import { buildRepairCards } from "../../src/lib/repairCardModel.js";

const BASE = {
  geo_readiness_version: "geo_readiness_v1_experimental",
  evidence_adapter_version: "geo_evidence_v1",
  assessment_status: "assessed",
  score: 0,
  coverage: 0.875,
  sample_pages: 8,
  score_bounds: { lower: 0, upper: 12.5 },
  bounds_kind: "unknown_outcome_range_not_statistical_confidence",
};

test("keeps an assessed zero distinct from an unavailable null", () => {
  const zero = buildGeoReadinessPresentation({ geoReadiness: BASE, customerAccess: "preview" });
  const unavailable = buildGeoReadinessPresentation({
    geoReadiness: { ...BASE, assessment_status: "insufficient_evidence", score: null },
    customerAccess: "preview",
  });

  assert.equal(zero.score, 0);
  assert.equal(zero.scoreAvailable, true);
  assert.equal(unavailable.score, null);
  assert.equal(unavailable.scoreAvailable, false);
});

test("labels the sample, coverage, provenance, time, and unknown-outcome bounds", () => {
  const result = buildGeoReadinessPresentation({
    geoReadiness: { ...BASE, score: 100, coverage: 0.8, sample_pages: 12, score_bounds: { lower: 80, upper: 100 } },
    customerAccess: "preview",
    completedAt: "2026-09-18T12:30:00Z",
  });

  assert.equal(result.sampleLabel, "12 assessed pages");
  assert.equal(result.coverageLabel, "80% evidence coverage");
  assert.equal(result.boundsLabel, "80–100 possible as unresolved checks are completed");
  assert.match(result.methodologyLabel, /Experimental v1/);
  assert.match(result.methodologyLabel, /raw HTML/i);
  assert.match(result.nonCitationLabel, /does not measure.*citation/i);
  assert.equal(result.completedAt, "2026-09-18T12:30:00.000Z");
});

test("treats historical absence and malformed payloads as neutral unavailable states", () => {
  const absent = buildGeoReadinessPresentation({ geoReadiness: undefined });
  const malformed = buildGeoReadinessPresentation({ geoReadiness: { ...BASE, coverage: "0.8" } });

  assert.equal(absent.state, "not_assessed");
  assert.equal(absent.statusLabel, "Not assessed for this scan");
  assert.equal(malformed.state, "unavailable");
  assert.equal(malformed.statusLabel, "GEO readiness unavailable");
});

test("preview never exposes findings, observations, URLs, or actions even if supplied", () => {
  const preview = buildGeoReadinessPresentation({
    geoReadiness: {
      ...BASE,
      observations: [{ page_url: "https://secret.example/private" }],
      findings: [{
        rule_id: "geo_template_integrity",
        check_id: "template_integrity",
        affected_page_count: 1,
        evidence_samples: [{ page_url: "https://secret.example/private" }],
        suggested_action: "Secret action",
        verification_step: "Secret verification",
      }],
    },
    customerAccess: "preview",
  });

  assert.deepEqual(preview.actions, []);
  assert.doesNotMatch(JSON.stringify(preview), /secret|private|observations|findings/i);
});

test("full findings deduplicate only supported matching repairs with overlapping URLs", () => {
  const geo = {
    ...BASE,
    authority_verified: true,
    findings: [
      {
        rule_id: "geo_indexability",
        root_cause_id: "geo_indexability",
        check_id: "indexability",
        label: "Observed search indexing directives",
        affected_page_count: 2,
        evidence_samples: [{ page_url: "https://example.com/a" }, { page_url: "https://example.com/b" }],
        suggested_action: "Reconcile noindex and sitemap intent.",
        verification_step: "Inspect the directives after publication.",
      },
      {
        rule_id: "geo_template_integrity",
        root_cause_id: "geo_template_integrity",
        check_id: "template_integrity",
        label: "Template token syntax",
        affected_page_count: 1,
        evidence_samples: [{ page_url: "https://example.com/c" }],
        suggested_action: "Replace unintended placeholders.",
        verification_step: "Check the published text.",
      },
    ],
  };
  const cards = [
    { title: "Resolve sitemap indexing conflicts", rule: "sitemap_indexability_conflict", evidence: { affectedPages: ["/a"] } },
    { title: "Unrelated repair on the same page", rule: "missing_h1", evidence: { affectedPages: ["/c"] } },
  ];

  const result = buildGeoReadinessPresentation({
    geoReadiness: geo,
    customerAccess: "full",
    cards,
    siteOrigin: "https://example.com",
  });

  assert.equal(result.actions.length, 2);
  assert.equal(result.actions[0].existingRepairTitle, "Resolve sitemap indexing conflicts");
  assert.equal(result.actions[0].suggestedAction, "");
  assert.equal(result.actions[1].existingRepairTitle, "");
  assert.equal(result.actions[1].suggestedAction, "Replace unintended placeholders.");
  assert.equal(result.actions[1].pages[0].href, "https://example.com/c");
});

test("full details require verified authority", () => {
  const result = buildGeoReadinessPresentation({
    geoReadiness: { ...BASE, findings: [{ check_id: "template_integrity" }] },
    customerAccess: "full",
  });
  assert.deepEqual(result.actions, []);
});

test("rejects impossible assessed summary shapes", () => {
  for (const geoReadiness of [
    { ...BASE, sample_pages: 0 },
    { ...BASE, coverage: 0.79 },
    { ...BASE, score_bounds: null },
  ]) {
    const result = buildGeoReadinessPresentation({ geoReadiness, customerAccess: "preview" });
    assert.equal(result.state, "unavailable");
    assert.equal(result.score, null);
  }
});

test("dedup preserves trailing-slash resource identity", () => {
  const result = buildGeoReadinessPresentation({
    geoReadiness: {
      ...BASE,
      authority_verified: true,
      findings: [{
        rule_id: "geo_indexability",
        root_cause_id: "geo_indexability",
        check_id: "indexability",
        label: "Indexability",
        affected_page_count: 1,
        evidence_samples: [{ page_url: "https://example.com/product/" }],
        suggested_action: "Review it.",
        verification_step: "Verify it.",
      }],
    },
    customerAccess: "full",
    cards: [{ title: "Different resource", rule: "sitemap_indexability_conflict", evidence: { affectedPages: ["/product"] } }],
    siteOrigin: "https://example.com",
  });

  assert.equal(result.actions[0].existingRepairTitle, "");
  assert.equal(result.actions[0].suggestedAction, "Review it.");
});

test("generic robots repairs do not deduplicate an OAI-specific policy finding", () => {
  const result = buildGeoReadinessPresentation({
    geoReadiness: {
      ...BASE,
      authority_verified: true,
      findings: [{
        rule_id: "geo_search_policy",
        root_cause_id: "geo_search_policy",
        check_id: "search_policy",
        label: "OAI-SearchBot robots directive",
        affected_page_count: 1,
        evidence_samples: [{ page_url: "https://example.com/a" }],
        suggested_action: "Review the OAI-SearchBot policy.",
        verification_step: "Recheck it.",
      }],
    },
    customerAccess: "full",
    cards: [{ title: "Scanner access", rule: "robots_blocked", evidence: { affectedPages: ["/a"] } }],
    siteOrigin: "https://example.com",
  });

  assert.equal(result.actions[0].existingRepairTitle, "");
});

test("the real location-template card deduplicates only on an exact overlapping resource", () => {
  const geoReadiness = {
    ...BASE,
    authority_verified: true,
    findings: [{
      rule_id: "geo_template_integrity",
      root_cause_id: "geo_template_integrity",
      check_id: "template_integrity",
      label: "Template token syntax in ordinary text",
      affected_page_count: 1,
      evidence_samples: [{ page_url: "https://example.com/locations/austin" }],
      suggested_action: "Replace unintended placeholders.",
      verification_step: "Confirm the published text no longer contains the token.",
    }],
  };
  const [overlappingCard] = buildRepairCards([{
    id: "loc-1",
    fix_id: "loc-1",
    rule: "broken_location_template_content",
    category: "web_dev",
    priority: "high",
    issue_title: "Fix broken location-page template content",
    why_it_matters: "Unresolved location variables publish broken geographic copy.",
    recommendation: "Fix the shared location template and its geographic variables.",
    affected_pages: ["/locations/austin"],
    page_count: 1,
    page_template_family: "location_landing",
    requires_developer: true,
    who_can_do_this: "your_web_person",
  }]);

  const overlapping = buildGeoReadinessPresentation({
    geoReadiness,
    customerAccess: "full",
    cards: [overlappingCard],
    siteOrigin: "https://example.com",
  });
  const differentResource = buildGeoReadinessPresentation({
    geoReadiness,
    customerAccess: "full",
    cards: [{ ...overlappingCard, evidence: { ...overlappingCard.evidence, affectedPages: ["/locations/dallas"] } }],
    siteOrigin: "https://example.com",
  });

  assert.equal(overlapping.actions[0].existingRepairTitle, "Fix the wrong or unfinished text on this location page");
  assert.equal(overlapping.actions[0].suggestedAction, "");
  assert.equal(differentResource.actions[0].existingRepairTitle, "");
  assert.equal(differentResource.actions[0].suggestedAction, "Replace unintended placeholders.");
});
