import assert from "node:assert/strict";
import test from "node:test";

import {
  SAMPLING_DISCLOSURE_VERSION,
  samplingDisclosure,
  SUPPORTED_SAMPLING_VERSIONS,
} from "../../src/lib/samplingDisclosure.js";
import { RELEASE_COMPONENT_VERSIONS } from "../../src/lib/generatedReleaseContract.js";

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
  // Selection language throughout: every number in this module comes from
  // the pre-crawl half of sampling_report(), so none of it may claim a page
  // was looked at.
  assert.equal(disclosure.marketSummary, "Markets/languages: 2 of 3 chosen for this scan.");
  assert.equal(disclosure.familySummary, "Page families: 2 of 3 chosen for this scan.");
  assert.match(disclosure.notChosenSummary, /Markets not chosen: de/);
  assert.match(disclosure.notChosenSummary, /Page families not chosen: legal info/);
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

test("the disclosure survives the sampling version bump that ships with it", () => {
  // The allowlist was a hand-maintained list of sampler versions, so bumping
  // SAMPLING_VERSION to v6 in the checked-coverage change silently returned
  // null for every new scan and the whole disclosure block disappeared from the
  // page. Nothing failed: an absent block looks the same as a scan with nothing
  // to disclose. The list is now derived from the release contract, so the
  // shipped sampler is admitted by construction rather than by remembering.
  const shipped = RELEASE_COMPONENT_VERSIONS.sampling_version;
  assert.ok(shipped, "the release contract must name the sampler this build ships");
  assert.ok(
    SUPPORTED_SAMPLING_VERSIONS.has(shipped),
    `the shipped sampler ${shipped} produces no disclosure`,
  );

  const disclosure = samplingDisclosure({
    sampling_version: shipped,
    sampling_evidence: {
      route_signatures_discovered: 120,
      // v6 renamed the selection keys and kept these as aliases for one
      // release; the disclosure still reads the alias, so both must work.
      route_signatures_sampled: 72,
      markets_discovered: { en: 80, de: 40 },
      markets_sampled: { en: 20 },
      markets_never_sampled: ["de"],
    },
  });
  assert.notEqual(disclosure, null, "the shipped sampler must produce a disclosure");
  assert.equal(disclosure.routesDiscovered, 120);
  assert.match(disclosure.notChosenSummary, /Markets not chosen: de/);
});

test("an unrecognised sampler is still refused", () => {
  // Deriving the allowlist from the contract must not turn it into "accept
  // anything": a record written by a sampler this build does not know cannot be
  // read against this build's field names.
  assert.equal(SUPPORTED_SAMPLING_VERSIONS.has("balanced_sitemap_buckets_v99_invented"), false);
  assert.equal(samplingDisclosure({
    sampling_version: "balanced_sitemap_buckets_v99_invented",
    sampling_evidence: { route_signatures_discovered: 120, route_signatures_sampled: 72 },
  }), null);
});
