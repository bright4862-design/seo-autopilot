#!/usr/bin/env node
// Default: validate and print a plan. Execution requires an exact manifest hash
// confirmation, existing projects/grants and fresh per-owner prerequisites.
// No synthetic or missing sites are generated to satisfy the fifty-site gate.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { writeNewArtifact, localAcceptanceIdentity, validatePrerequisites } from "./staged_scan_acceptance.mjs";

const identifier = value => typeof value === "string" && /^[A-Za-z0-9_-]{6,160}$/.test(value);
const targetUrl = value => { try { const url = new URL(value); return url.protocol === "https:" && !url.username && !url.password && !url.hash ? url.href : ""; } catch { return ""; } };

export function validateCorpusManifest(manifest, now = Date.now()) {
  const failures = [], add = (ok, code) => { if (!ok) failures.push(code); };
  add(manifest?.schema_version === "staged_scan_corpus_v1", "corpus_schema_invalid");
  add(/^[a-f0-9]{40}$/.test(manifest?.source_sha || "") && /^[a-f0-9]{16}$/.test(manifest?.release_fingerprint || ""), "corpus_source_invalid");
  const reviewed = Date.parse(manifest?.reviewed_at), expires = Date.parse(manifest?.expires_at);
  add(typeof manifest?.reviewed_by === "string" && Boolean(manifest.reviewed_by.trim()) && Number.isFinite(reviewed) && reviewed <= now && expires > now && expires - reviewed <= 86400000, "corpus_review_missing_or_expired");
  const sites = Array.isArray(manifest?.sites) ? manifest.sites : [];
  add(sites.length === 50, "corpus_requires_50_sites");
  for (const [key, code] of [["site_id", "duplicate_site_id"], ["request_id", "duplicate_request_id"], ["project_id", "duplicate_project_id"]]) add(new Set(sites.map(row => row?.[key])).size === sites.length, code);
  const hosts = new Set();
  for (const site of sites) {
    add(identifier(site?.owner_user_id) && identifier(site?.project_id) && identifier(site?.request_id) && typeof site?.site_id === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(site.site_id), "corpus_site_identity_invalid");
    const target = targetUrl(site?.target_url);
    add(Boolean(target) && site.target_url === target, "corpus_target_invalid");
    if (target) hosts.add(new URL(target).hostname.replace(/^www\./, ""));
    add(["ecommerce", "content", "local", "mixed"].includes(site?.site_class), "corpus_site_class_invalid");
    add(["complete_500", "throttled_limited"].includes(site?.expectation), "corpus_expected_outcome_invalid");
    add(site?.reference_marker === null || ["funbooker", "pretto", "center_street_lending", "norris_wines"].includes(site?.reference_marker), "corpus_reference_invalid");
  }
  add(hosts.size === sites.length, "corpus_hosts_not_distinct");
  for (const marker of ["funbooker", "pretto", "center_street_lending", "norris_wines"]) add(sites.filter(site => site?.reference_marker === marker).length === 1, `corpus_reference_missing_or_duplicate:${marker}`);
  for (const siteClass of ["ecommerce", "content", "local", "mixed"]) add(sites.some(site => site?.site_class === siteClass), `corpus_class_missing:${siteClass}`);
  add(sites.some(site => site?.expectation === "throttled_limited"), "corpus_throttling_case_missing");
  return [...new Set(failures)];
}

export async function runCorpus(manifest, { now = Date.now(), execute = false, executeSite } = {}) {
  const report = { schema_version: "staged_scan_corpus_report_v1", source_sha: manifest?.source_sha, release_fingerprint: manifest?.release_fingerprint,
    dry_run: execute !== true, expected_site_count: 50, supplied_site_count: Array.isArray(manifest?.sites) ? manifest.sites.length : 0,
    production_freeze: false, acceptance_verified: false, full_500_gate: false, scans: [], failures: validateCorpusManifest(manifest, now) };
  if (report.failures.length || !execute) return report;
  if (typeof executeSite !== "function") { report.failures.push("corpus_executor_missing"); return report; }
  const scanIds = new Set();
  for (const site of manifest.sites) {
    let scan;
    try { scan = await executeSite(site); } catch { report.failures.push("canary_execution_failed"); break; }
    const entry = { site_id: site.site_id, site_class: site.site_class, reference_marker: site.reference_marker, expected_outcome: site.expectation, report: scan };
    report.scans.push(entry);
    if (scan?.schema_version !== "staged_500_canary_v1" || scan.source_sha !== manifest.source_sha || scan.release_fingerprint !== manifest.release_fingerprint || scan.expected_owner_user_id !== site.owner_user_id || scan.project_id !== site.project_id || scan.request_id !== site.request_id || scan.target_url !== site.target_url || !identifier(scan.scan_id) || scanIds.has(scan.scan_id)) { report.failures.push("scan_report_identity_mismatch"); break; }
    scanIds.add(scan.scan_id);
    if (scan.terminal_outcome_verified !== true || (site.expectation === "complete_500" ? scan.functional_500_verified !== true || scan.outcome !== "complete" : scan.outcome !== "limited_throttled")) { report.failures.push(`scan_outcome_mismatch:${site.site_id}`); break; }
  }
  if (report.scans.length !== 50) report.failures.push("corpus_incomplete");
  // A truthful throttled limited result belongs in the corpus, but is never a
  // successful full-500 proof. Missing resource/runtime producers keep the
  // rollout gate closed even when all functional outcomes are verified.
  // Child report booleans cannot replace the missing raw measurements. Keep
  // this closed until their producers and independent verification exist.
  report.full_500_gate = false;
  report.acceptance_verified = false;
  if (!report.acceptance_verified) report.failures.push("full_500_resource_or_runtime_acceptance_unverified");
  return report;
}

async function executeShell(root, site, manifest, prerequisitesFile, output) {
  const reportPath = path.join(path.dirname(output), `${path.basename(output)}.${site.site_id}.json`);
  if (fs.existsSync(reportPath)) throw new Error("prior_canary_report_exists");
  const status = await new Promise((resolve, reject) => {
    const child = spawn("bash", [path.join(root, "scripts/run-staged-500-canary.sh")], { cwd: root, stdio: ["ignore", "ignore", "ignore"], env: { ...process.env,
      SOURCE_SHA: manifest.source_sha, EXPECTED_OWNER_USER_ID: site.owner_user_id, PROJECT_ID: site.project_id,
      TARGET_URL: site.target_url, REQUEST_ID: site.request_id, PREREQUISITES_FILE: prerequisitesFile, ACCEPTANCE_OUTPUT: reportPath,
      CONFIRM: `RUN-ONE-STAGED-500-CANARY:${manifest.source_sha}:${site.owner_user_id}:${site.project_id}:${site.request_id}` } });
    child.once("error", reject); child.once("exit", resolve);
  });
  if (status !== 0 || !fs.existsSync(reportPath)) throw new Error("canary_failed");
  return JSON.parse(fs.readFileSync(reportPath, "utf8"));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  try {
    const args = process.argv.slice(2), value = name => { const index = args.indexOf(name); return index >= 0 ? args[index + 1] : undefined; };
    if (args.includes("--help")) {
      console.log("Usage: node scripts/run-staged-scan-corpus.mjs --manifest reviewed.json [--output /outside-checkout/report.json] [--prerequisites /fresh/packet.json --execute --confirm RUN-STAGED-CORPUS:<source-sha>:<manifest-sha256>]\nDefault: dry-run; requires exactly 50 distinct reviewed existing projects, stable request IDs, four named reference markers, all site classes and an explicitly throttled case. Prerequisite producers and all-stage memory/completion-request measurements remain required for full acceptance.");
    } else {
      const manifestPath = value("--manifest"), raw = fs.readFileSync(manifestPath, "utf8"), manifest = JSON.parse(raw);
      const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."), execute = args.includes("--execute"), output = value("--output"), prerequisitesFile = value("--prerequisites");
      if (execute) {
        const hash = createHash("sha256").update(raw).digest("hex");
        if (value("--confirm") !== `RUN-STAGED-CORPUS:${manifest.source_sha}:${hash}` || !output || !prerequisitesFile) throw new Error("exact_corpus_confirmation_output_and_prerequisites_required");
        // Validate the packet for every distinct owner before the first scan.
        const packet = JSON.parse(fs.readFileSync(prerequisitesFile, "utf8"));
        for (const ownerId of new Set((manifest.sites || []).map(site => site.owner_user_id))) {
          const expected = localAcceptanceIdentity(root, manifest.source_sha, ownerId);
          if (expected.fingerprint !== manifest.release_fingerprint || !validatePrerequisites(packet, expected).ready) throw new Error("corpus_prerequisites_unverified");
        }
        // Validate output safety before executing any child wrapper.
        if (!path.isAbsolute(output) || fs.existsSync(output) || !fs.existsSync(path.dirname(output)) || fs.realpathSync(path.dirname(output)) !== path.dirname(output)) throw new Error("corpus_output_invalid");
        const relative = path.relative(root, path.dirname(output));
        if (!relative || (relative !== ".." && !relative.startsWith(".." + path.sep))) throw new Error("corpus_output_inside_checkout");
      }
      const report = await runCorpus(manifest, { execute, executeSite: site => executeShell(root, site, manifest, prerequisitesFile, output) });
      if (output) writeNewArtifact(output, report, root);
      console.log(JSON.stringify(report, null, 2));
      if (report.failures.length || (execute && !report.acceptance_verified)) process.exitCode = 1;
    }
  } catch (error) { console.error(`STAGED_CORPUS_BLOCKED: ${error.message}`); process.exitCode = 2; }
}
