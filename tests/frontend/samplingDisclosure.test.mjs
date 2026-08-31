import assert from "node:assert/strict";
import test from "node:test";

import {
  SAMPLING_DISCLOSURE_VERSION,
  samplingDisclosure,
} from "../../src/lib/samplingDisclosure.js";

const VERSION = "balanced_sitemap_buckets_v2_locale_collapsed_identity_reserve";

test("sampling disclosure reports route, market, family and identity coverage", () => {
  const disclosure = samplingDisclosure({
    sampling_version: VERSION,
    sampling_evidence: {
      route_signatures_discovered: 120,
      route_signatures_sampled: 72,
      locale_variants_collapsed: 48,
      identity_pages_in_sitemap: 30,
      identity_pages_sampled: 20,
      markets_discovered: { en: 80, fr: 60, de: 40 },
      markets_sampled: { en: 20, fr: 10 },
      markets_never_sampled: ["de"],
      family_totals: { product_detail: 70, category_listing: 30, legal_info: 20 },
      family_sampled: { product_detail: 30, category_listing: 20 },
      families_never_sampled: ["legal_info"],
    },
  });

  assert.equal(disclosure.version, SAMPLING_DISCLOSURE_VERSION);
  assert.equal(disclosure.routesDiscovered, 120);
  assert.equal(disclosure.routesSampled, 72);
  assert.equal(disclosure.localeVariantsCollapsed, 48);
  assert.equal(disclosure.identityDiscovered, 30);
  assert.equal(disclosure.identitySampled, 20);
  assert.equal(disclosure.marketSummary, "Markets/languages: 2 of 3 represented in the sample.");
  assert.equal(disclosure.familySummary, "Page families: 2 of 3 represented in the sample.");
  assert.match(disclosure.unsampledSummary, /Unsampled markets: de/);
  assert.match(disclosure.unsampledSummary, /Unsampled page families: legal info/);
});

test("sampling disclosure refuses old or evidence-free samplers", () => {
  assert.equal(samplingDisclosure({ sampling_version: "balanced_sitemap_buckets_v1" }), null);
  assert.equal(samplingDisclosure({
    sampling_version: VERSION,
    sampling_evidence: {},
  }), null);
});

test("sampling disclosure never invents missing market or family counts", () => {
  const disclosure = samplingDisclosure({
    sampling_version: VERSION,
    sampling_evidence: {
      route_signatures_discovered: 3,
      route_signatures_sampled: 3,
      identity_pages_in_sitemap: 1,
      identity_pages_sampled: 1,
    },
  });

  assert.equal(disclosure.marketSummary, "");
  assert.equal(disclosure.familySummary, "");
  assert.equal(disclosure.unsampledSummary, "");
});
