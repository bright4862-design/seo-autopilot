#!/usr/bin/env node
/** Validate observed synthetic stage-one output; never infer live-site acceptance. */
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const manifestPath = fileURLToPath(new URL("../tests/fixtures/stage1-blueprint-corpus.json", import.meta.url));
const manifestBytes = fs.readFileSync(manifestPath);
const manifest = JSON.parse(manifestBytes);
const mandatoryCases = new Set([
  "pretto_published_routes", "pretto_visible_year", "pretto_redirect_aliases",
  "center_visible_templates", "center_hidden_examples", "ike_main_utility_noindex",
  "ike_main_sitemap_conflict", "ike_locations_canonical_away", "ike_locations_shells",
  "getfixlist_image_applicability", "getfixlist_search_metadata",
  "ironwood_siteground_200", "ironwood_siteground_403", "ironwood_truncated",
]);
const searchRules = new Set([
  "missing_title", "generic_fallback_title", "title_over_pixel_limit", "missing_meta_description",
  "empty_meta_description", "malformed_meta_description", "meta_description_unusable",
  "canonical_missing", "missing_canonical",
  "duplicate_title", "duplicate_title_template", "duplicate_title_query_variants",
]);

function check(condition, message) {
  if (!condition) throw new Error(message);
}

function readPath(object, key) {
  return key.split(".").reduce((value, part) => value?.[part], object);
}

function pages(item) {
  return item.scan.pages || item.scan.crawled_pages || [];
}

function pageFor(item, url) {
  const page = pages(item).find(row => row.url === url || row.final_url === url);
  check(page, `missing observed page ${url}`);
  return page;
}

function rows(item, raw = false) {
  const result = raw ? item.scan.findings : item.review.recommendations;
  check(Array.isArray(result), `missing ${raw ? "raw findings" : "recommendations"}`);
  return result;
}

function affected(item, row) {
  const values = Array.isArray(row.affected_pages) && row.affected_pages.length
    ? row.affected_pages : [row.page_url].filter(Boolean);
  return values.map(url => url.startsWith("/") ? item.origin + url : url);
}

function matching(item, assertion) {
  return rows(item, assertion.raw).filter(row => row.rule === assertion.rule
    && (!assertion.url || affected(item, row).includes(assertion.url)));
}

function sameSet(left, right) {
  return JSON.stringify([...new Set(left)].sort()) === JSON.stringify([...new Set(right)].sort());
}

function evaluate(item, assertion) {
  switch (assertion.kind) {
    case "page_field": {
      const actual = readPath(pageFor(item, assertion.url), assertion.field);
      if (Object.hasOwn(assertion, "equals")) {
        check(JSON.stringify(actual) === JSON.stringify(assertion.equals),
          `${assertion.field}: expected ${JSON.stringify(assertion.equals)}, observed ${JSON.stringify(actual)}`);
      } else if (Object.hasOwn(assertion, "minimum")) {
        check(Number.isFinite(actual) && actual >= assertion.minimum,
          `${assertion.field}: expected at least ${assertion.minimum}, observed ${JSON.stringify(actual)}`);
      } else throw new Error("page field assertion has no operator");
      break;
    }
    case "rule": {
      const found = matching(item, assertion);
      check(Boolean(found.length) === assertion.present,
        `${assertion.rule}: expected ${assertion.present ? "present" : "absent"}${assertion.url ? ` for ${assertion.url}` : ""}`);
      if (Object.hasOwn(assertion, "non_scoring")) {
        check(found.every(row => (row.non_scoring === true) === assertion.non_scoring),
          `${assertion.rule}: incorrect non_scoring state`);
      }
      if (assertion.verification_state) {
        check(found.every(row => row.verification_state === assertion.verification_state),
          `${assertion.rule}: incorrect verification state`);
      }
      break;
    }
    case "rule_count":
      check(matching(item, assertion).length === assertion.equals,
        `${assertion.rule}: expected ${assertion.equals} repair(s), observed ${matching(item, assertion).length}`);
      break;
    case "affected_urls": {
      const urls = matching(item, assertion).flatMap(row => affected(item, row));
      check(sameSet(urls, assertion.equals), `${assertion.rule} affected URLs differ: ${JSON.stringify(urls)}`);
      break;
    }
    case "no_search_metadata": {
      const found = [...rows(item), ...rows(item, true)].filter(row => searchRules.has(row.rule)
        && affected(item, row).includes(assertion.url));
      check(!found.length, `independent search metadata remains: ${found.map(row => row.rule).join(", ")}`);
      break;
    }
    case "template_samples": {
      const evidence = pageFor(item, assertion.url).visible_template_evidence;
      check(evidence?.accepted === true && evidence.state === "fail", "template evidence is not accepted failure evidence");
      check(Array.isArray(evidence.samples) && evidence.samples.length > 0
        && evidence.samples.length <= assertion.max_samples, "template sample bound violated");
      check(evidence.samples.every(sample => typeof sample.snippet === "string"
        && sample.snippet.length > 0 && sample.snippet.length <= assertion.max_length), "template excerpt bound violated");
      check(sameSet(evidence.samples.map(sample => sample.placement), assertion.placements), "template placement evidence differs");
      break;
    }
    case "redirect_aliases": {
      const page = pages(item).find(row => row.final_url === assertion.final_url);
      check(page, "missing accepted redirect destination");
      const sources = [page.url, ...(page.redirect_aliases || []).map(row => row.url)];
      check(sameSet(sources, assertion.source_urls), "published redirect source observations were lost");
      check(item.scan.technical_audit_summary.final_url_duplicates_deduped === assertion.duplicates,
        "incorrect verified final-page deduplication count");
      check(assertion.source_urls.every(url => item.requested_urls.includes(url)), "redirect source was not actually requested");
      break;
    }
    case "access_limited":
      check(item.review.release_gate_eligible === false, "access challenge became authoritative");
      check(item.review.score_is_provisional === true, "access-limited SEO result lost its provisional state");
      check(item.review.geo_readiness?.score === null
        && item.review.geo_readiness?.assessment_status === "access_limited", "access challenge produced a GEO score");
      check(pages(item).every(page => !page.geo_evidence || page.geo_evidence.accepted === false),
        "access challenge entered accepted GEO evidence");
      break;
    default:
      throw new Error(`unknown assertion kind ${assertion.kind}`);
  }
}

export function assertCorpusRun(report) {
  check(report && typeof report === "object", "Expected corpus report object");
  check(report.provenance === "synthetic", "Corpus provenance must be synthetic");
  check(report.version === manifest.version && report.scope === manifest.scope, "Unknown corpus version or scope");
  check(report.full_30_site_gate === "not_assessed", "Synthetic corpus cannot claim the full 30-site gate");
  check(report.manifest_sha256 === createHash("sha256").update(manifestBytes).digest("hex"), "Corpus manifest hash mismatch");
  check(/^[a-f0-9]{40}$/.test(report.source?.git_sha || "")
    && /^[a-f0-9]{64}$/.test(report.source?.source_tree_sha256 || "")
    && report.source?.execution === "actual_python_scanner_and_local_review"
    && /^[a-f0-9]{16}$/.test(report.source?.versions?.fingerprint || "")
    && ["scanner_version", "review_version", "geo_evidence_version", "evidence_url_identity_version"]
      .every(key => typeof report.source?.versions?.component_versions?.[key] === "string"
        && report.source.versions.component_versions[key]), "Missing actual source/version context");
  check(!Number.isNaN(Date.parse(report.generated_at)), "Missing observation timestamp");
  check(Array.isArray(report.cases), "Missing corpus cases");
  const ids = report.cases.map(item => item.id);
  check(new Set(ids).size === ids.length, "Duplicate corpus case");
  const missing = [...mandatoryCases].filter(id => !ids.includes(id));
  check(!missing.length, `Missing mandatory cases: ${missing.join(", ")}`);
  check(sameSet(ids, [...mandatoryCases]) && sameSet(manifest.cases.map(item => item.id), [...mandatoryCases]),
    "Unexpected or unregistered corpus case");
  const failures = [];
  let count = 0;
  for (const fixture of manifest.cases) {
    const item = report.cases.find(candidate => candidate.id === fixture.id);
    check(item.provenance === "synthetic" && item.origin === fixture.origin && item.mode === fixture.mode,
      `${fixture.id}: incorrect case provenance, host or execution mode`);
    check(item.scan && item.review && Array.isArray(item.requested_urls), `${fixture.id}: missing observed output`);
    for (const assertion of fixture.assertions) {
      count += 1;
      try { evaluate(item, assertion); }
      catch (error) { failures.push(`${fixture.id}: ${error.message}`); }
    }
  }
  check(!failures.length, `Corpus assertions failed:\n${failures.join("\n")}`);
  return { version: manifest.version, provenance: "synthetic", cases: ids.length, assertions: count,
    full_30_site_gate: "not_assessed", source_tree_sha256: report.source.source_tree_sha256 };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    check(process.argv.length === 3, "Usage: node scripts/assertCorpusRun.mjs observed-corpus.json");
    console.log(JSON.stringify(assertCorpusRun(JSON.parse(fs.readFileSync(process.argv[2], "utf8")))));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
