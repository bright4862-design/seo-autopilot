#!/usr/bin/env node
/**
 * Full-blueprint 30-site baseline/candidate gate.
 *
 * The tracked renderer-risk manifest supplies only the 30-site roster. It is not
 * acceptance evidence. A passing gate requires newly supplied paired captured
 * artifacts for every roster entry. Historical summaries and synthetic/test
 * fixtures are deliberately unable to produce a PASS result.
 */
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const ROSTER_PATH = path.join(ROOT, "data/renderer-risk-study-manifest.jsonl");
export const BLUEPRINT_30_SITE_GATE_VERSION = "blueprint_30_site_baseline_candidate_v1";

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function clean(value) {
  return typeof value === "string" ? value.trim() : "";
}

function isSha(value, width) {
  return new RegExp(`^[a-f0-9]{${width}}$`).test(clean(value));
}

function parseTime(value) {
  const time = Date.parse(clean(value));
  return Number.isFinite(time) ? time : null;
}

export function loadBlueprint30SiteRoster() {
  const bytes = fs.readFileSync(ROSTER_PATH);
  const rows = bytes.toString("utf8").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
  if (rows.length !== 30) throw new Error(`Expected 30 roster rows, observed ${rows.length}`);
  const ids = rows.map((row) => clean(row.site));
  if (ids.some((id) => !id) || new Set(ids).size !== rows.length) throw new Error("30-site roster has missing or duplicate site ids");
  return {
    rows: rows.map(({ site, url, stratum }) => ({ site: clean(site), url: clean(url), stratum: clean(stratum) })),
    sha256: sha256(bytes),
  };
}

function capturedArtifactErrors(artifact, label) {
  const failures = [];
  if (!artifact || typeof artifact !== "object" || Array.isArray(artifact)) return [`${label} artifact missing`];
  if (clean(artifact.provenance) !== "captured") failures.push(`${label} provenance is not captured`);
  if (!isSha(artifact.artifact_sha256, 64)) failures.push(`${label} artifact_sha256 invalid`);
  if (!isSha(artifact.source_sha, 40)) failures.push(`${label} source_sha invalid`);
  if (!isSha(artifact.release_fingerprint, 16)) failures.push(`${label} release_fingerprint invalid`);
  if (parseTime(artifact.captured_at) === null) failures.push(`${label} captured_at invalid`);
  if (clean(artifact.scan_mode) !== "standard_150") failures.push(`${label} scan_mode must be standard_150`);
  if (!clean(artifact.scope)) failures.push(`${label} scope missing`);
  if (!clean(artifact.policy_id)) failures.push(`${label} policy_id missing`);
  if (!clean(artifact.evidence_bundle_id)) failures.push(`${label} evidence_bundle_id missing`);
  return failures;
}

function adjudicationErrors(pair) {
  const failures = [];
  const difference = pair?.difference_summary;
  if (!difference || typeof difference !== "object" || Array.isArray(difference)) return ["difference_summary missing"];
  const newArtifacts = Array.isArray(difference.new_artifact_ids)
    ? [...new Set(difference.new_artifact_ids.map(clean).filter(Boolean))]
    : null;
  if (!newArtifacts) return ["new_artifact_ids missing"];
  const adjudications = Array.isArray(pair.adjudications) ? pair.adjudications : [];
  const byId = new Map(adjudications.map((row) => [clean(row?.artifact_id), clean(row?.outcome)]));
  const allowed = new Set(["expected_change", "not_regression"]);
  for (const id of newArtifacts) {
    if (!byId.has(id)) failures.push(`new artifact ${id} has no adjudication`);
    else if (!allowed.has(byId.get(id))) failures.push(`new artifact ${id} adjudication is ${byId.get(id) || "unset"}`);
  }
  for (const row of adjudications) {
    const id = clean(row?.artifact_id);
    if (!id) failures.push("adjudication has no artifact_id");
    if (!clean(row?.evidence_reference)) failures.push(`adjudication ${id || "(missing)"} has no evidence_reference`);
    if (!clean(row?.reviewed_by)) failures.push(`adjudication ${id || "(missing)"} has no reviewer identity`);
    if (parseTime(row?.reviewed_at) === null) failures.push(`adjudication ${id || "(missing)"} reviewed_at invalid`);
  }
  return failures;
}

/**
 * Evaluate one full-blueprint gate record.
 *
 * Returns status pass / failed / not_assessed. test_fixture=true is always
 * not_assessed so unit tests can exercise shapes without manufacturing live
 * acceptance evidence.
 */
export function evaluateBlueprint30SiteGate(record) {
  const roster = loadBlueprint30SiteRoster();
  const failures = [];
  const blockers = [];

  if (!record || typeof record !== "object" || Array.isArray(record)) {
    return { status: "not_assessed", pass: false, failures: [], blockers: ["gate record missing"], site_count: 0 };
  }
  if (clean(record.version) !== BLUEPRINT_30_SITE_GATE_VERSION) blockers.push("gate version missing or unsupported");
  if (clean(record.roster_sha256) !== roster.sha256) blockers.push("30-site roster hash mismatch");
  if (record.test_fixture === true) blockers.push("test fixtures cannot satisfy the live 30-site gate");
  if (clean(record.provenance) !== "captured_baseline_candidate") blockers.push("gate provenance is not captured_baseline_candidate");
  if (parseTime(record.generated_at) === null) blockers.push("gate generated_at missing or invalid");

  const pairs = Array.isArray(record.pairs) ? record.pairs : [];
  const pairIds = pairs.map((pair) => clean(pair?.site_id));
  if (pairs.length !== 30) blockers.push(`expected 30 paired sites, observed ${pairs.length}`);
  if (new Set(pairIds).size !== pairIds.length) blockers.push("duplicate paired site ids");

  const expected = new Map(roster.rows.map((row) => [row.site, row]));
  for (const row of roster.rows) {
    const pair = pairs.find((item) => clean(item?.site_id) === row.site);
    if (!pair) {
      blockers.push(`missing pair for ${row.site}`);
      continue;
    }
    if (clean(pair.url) !== row.url) failures.push(`${row.site}: url does not match canonical roster`);
    if (clean(pair.stratum) !== row.stratum) failures.push(`${row.site}: stratum does not match canonical roster`);
    for (const message of capturedArtifactErrors(pair.baseline, `${row.site} baseline`)) failures.push(message);
    for (const message of capturedArtifactErrors(pair.candidate, `${row.site} candidate`)) failures.push(message);
    if (clean(pair.baseline?.policy_id) && clean(pair.candidate?.policy_id)
        && clean(pair.baseline.policy_id) !== clean(pair.candidate.policy_id)) {
      failures.push(`${row.site}: baseline/candidate scan policy differs`);
    }
    if (clean(pair.baseline?.scope) && clean(pair.candidate?.scope)
        && clean(pair.baseline.scope) !== clean(pair.candidate.scope)) {
      failures.push(`${row.site}: baseline/candidate scope differs`);
    }
    for (const message of adjudicationErrors(pair)) failures.push(`${row.site}: ${message}`);
  }
  for (const id of pairIds) if (id && !expected.has(id)) failures.push(`unexpected site ${id}`);

  if (blockers.length) return { status: "not_assessed", pass: false, failures, blockers, site_count: pairs.length, roster_sha256: roster.sha256 };
  if (failures.length) return { status: "failed", pass: false, failures, blockers: [], site_count: pairs.length, roster_sha256: roster.sha256 };
  return { status: "pass", pass: true, failures: [], blockers: [], site_count: 30, roster_sha256: roster.sha256 };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const target = process.argv[2];
  if (!target) {
    console.error("usage: node scripts/assertBlueprint30SiteGate.mjs <gate-record.json>");
    process.exit(2);
  }
  const result = evaluateBlueprint30SiteGate(JSON.parse(fs.readFileSync(target, "utf8")));
  console.log(JSON.stringify(result));
  process.exit(result.pass ? 0 : 1);
}
