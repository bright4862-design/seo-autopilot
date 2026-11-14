#!/usr/bin/env node
// Default: validate and print a plan. Execution requires an exact manifest hash
// confirmation, existing projects/grants and a fresh packet for each site.
// No synthetic or missing sites are generated to satisfy the fifty-site gate.
import fs from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { execFile, spawn } from "node:child_process";
import { parseArgs } from "node:util";
import { writeNewArtifact, localAcceptanceIdentity, validatePrerequisites } from "./staged_scan_acceptance.mjs";

const identifier = value => typeof value === "string" && /^[A-Za-z0-9_-]{6,160}$/.test(value);
const siteIdentifier = value => typeof value === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(value);
const sha256 = value => createHash("sha256").update(value).digest("hex");
const sha256Pattern = /^[a-f0-9]{64}$/;
const workerMemoryLimit = 1024 ** 3;
const workspaceBucket = "fixlist-scan-workspaces-seo-autopilot-501517";
const selectionBaseline = "689a7fb43825f322af70188e7426730552daebd9";

export function verifyReceiptSummary(evidence, report, reportDigest) {
  const provenance = report?.provenance;
  const memory = evidence?.memory;
  const request = evidence?.completion_request;
  const positive = value => Number.isSafeInteger(value) && value > 0;
  const bounded = value => positive(value) && value < workerMemoryLimit;
  const terminalFunction = report?.terminal_status === "complete" ? "persistDurableScanAuthorityV9"
    : report?.terminal_status === "limited" ? "persistLimitedScanResultV9" : null;
  return Boolean(terminalFunction && report?.terminal_outcome_verified === true
    && evidence?.schema_version === "staged_500_receipt_evidence_v1" && evidence.production_freeze === false
    && sha256Pattern.test(reportDigest || "") && evidence.canary_report_sha256 === reportDigest
    && evidence.scan_id === report.scan_id && positive(report.attempt_count) && evidence.attempt_count === report.attempt_count
    && evidence.source_sha === report.source_sha && evidence.release_fingerprint === report.release_fingerprint
    && evidence.worker_revision === provenance?.worker_revision && /^fixlist-standard150-worker-[a-z0-9-]+$/.test(evidence.worker_revision || "")
    && sha256Pattern.test(provenance?.prerequisite_sha256 || "") && evidence.prerequisite_sha256 === provenance.prerequisite_sha256
    && evidence.workspace_bucket === workspaceBucket && evidence.terminal_status === report.terminal_status
    && evidence.worker_runtime_verified === true && evidence.receipt_evidence_verified === true
    && Array.isArray(evidence.unverified) && evidence.unverified.length === 0
    && /^[1-9][0-9]{0,23}$/.test(evidence.frontier_generation || "") && sha256Pattern.test(evidence.receipt_snapshot_sha256 || "")
    && positive(report.committed_batch_count) && evidence.committed_delivery_count === report.committed_batch_count + 2
    && positive(evidence.delivery_count) && evidence.delivery_count <= 256 && evidence.delivery_count >= evidence.committed_delivery_count
    && request?.function === terminalFunction && positive(request.body_bytes) && sha256Pattern.test(request.body_sha256 || "")
    && Number.isInteger(request.status_code) && request.status_code >= 200 && request.status_code < 300
    && memory?.all_stages_verified === true && memory.reviewed_worker_memory_limit_bytes === workerMemoryLimit
    && memory.parent_sampled_delivery_count === evidence.delivery_count && memory.cgroup_measured_delivery_count === evidence.delivery_count
    && positive(memory.review_sampled_delivery_count) && memory.review_sampled_delivery_count <= evidence.delivery_count
    && bounded(memory.sampled_aggregate_rss_peak_bytes) && bounded(memory.cgroup_lifetime_peak_upper_bound_bytes));
}
const targetUrl = value => { try { const url = new URL(value); return url.protocol === "https:" && !url.username && !url.password && !url.hash ? url.href : ""; } catch { return ""; } };

export function validateCorpusManifest(manifest, now = Date.now(), { historical = false } = {}) {
  const failures = [], add = (ok, code) => { if (!ok) failures.push(code); };
  add(manifest?.schema_version === "staged_scan_corpus_v1", "corpus_schema_invalid");
  add(/^[a-f0-9]{40}$/.test(manifest?.source_sha || "") && /^[a-f0-9]{16}$/.test(manifest?.release_fingerprint || ""), "corpus_source_invalid");
  const reviewed = Date.parse(manifest?.reviewed_at), expires = Date.parse(manifest?.expires_at);
  add(typeof manifest?.reviewed_by === "string" && Boolean(manifest.reviewed_by.trim()) && Number.isFinite(reviewed)
    && reviewed <= now && expires > reviewed && (historical || expires > now) && expires - reviewed <= 86400000, "corpus_review_missing_or_expired");
  const sites = Array.isArray(manifest?.sites) ? manifest.sites : [];
  add(sites.length === 50, "corpus_requires_50_sites");
  for (const [key, code] of [["site_id", "duplicate_site_id"], ["request_id", "duplicate_request_id"], ["project_id", "duplicate_project_id"]]) add(new Set(sites.map(row => row?.[key])).size === sites.length, code);
  const hosts = new Set();
  for (const site of sites) {
    add(identifier(site?.owner_user_id) && identifier(site?.project_id) && identifier(site?.request_id) && site.request_id.length >= 8 && siteIdentifier(site?.site_id), "corpus_site_identity_invalid");
    const target = targetUrl(site?.target_url);
    add(Boolean(target) && site.target_url === target, "corpus_target_invalid");
    if (target) hosts.add(new URL(target).hostname.replace(/^www\./, ""));
    add(["ecommerce", "content", "local", "mixed"].includes(site?.site_class), "corpus_site_class_invalid");
    add(["complete_500", "complete_below_cap", "throttled_limited"].includes(site?.expectation), "corpus_expected_outcome_invalid");
    add(site?.reference_marker === null || ["funbooker", "pretto", "center_street_lending", "norris_wines"].includes(site?.reference_marker), "corpus_reference_invalid");
  }
  add(hosts.size === sites.length, "corpus_hosts_not_distinct");
  for (const marker of ["funbooker", "pretto", "center_street_lending", "norris_wines"]) add(sites.filter(site => site?.reference_marker === marker).length === 1, `corpus_reference_missing_or_duplicate:${marker}`);
  for (const siteClass of ["ecommerce", "content", "local", "mixed"]) add(sites.some(site => site?.site_class === siteClass), `corpus_class_missing:${siteClass}`);
  add(sites.some(site => site?.expectation === "throttled_limited"), "corpus_throttling_case_missing");
  add(sites.some(site => site?.expectation === "complete_500"), "corpus_full_cap_case_missing");
  return [...new Set(failures)];
}

export function verifyCorpusSelection(comparison, manifest, manifestDigest, observations) {
  const sites = comparison?.sites;
  if (comparison?.schema_version !== "staged_scan_selection_comparison_v1"
      || comparison.baseline_source_sha !== selectionBaseline || comparison.candidate_source_sha !== manifest.source_sha
      || comparison.release_fingerprint !== manifest.release_fingerprint
      || comparison.evidence_scope !== "offline_replay_of_captured_sitemap_selection" || comparison.live_terminal_evidence_verified !== false
      || !sha256Pattern.test(manifestDigest || "") || comparison.corpus_manifest_sha256 !== manifestDigest
      || !sha256Pattern.test(comparison.captures_sha256 || "") || comparison.selection_comparison_verified !== true
      || !/^[a-z0-9_]{5,120}$/.test(comparison.candidate_sampling_version || "")
      || comparison.site_count !== 50 || !Array.isArray(sites) || sites.length !== 50
      || !Array.isArray(observations) || observations.length !== 50) return null;

  const byId = new Map(sites.map(site => [site?.site_id, site]));
  const observedById = new Map(observations.map(site => [site?.site_id, site]));
  let baselineOmitted = 0, candidateOmitted = 0, signedComparisons = 0;
  for (const site of manifest.sites) {
    const evidence = byId.get(site.site_id), observation = observedById.get(site.site_id);
    const anchor = evidence?.claimed_terminal_anchor, scan = observation?.report, receipt = observation?.receipt;
    const sections = evidence?.sections;
    if (!evidence || evidence.reference_marker !== site.reference_marker || !sha256Pattern.test(evidence.capture_sha256 || "")
        || typeof evidence.inventory_capped !== "boolean" || !observation?.resource_evidence_verified
        || !anchor || anchor.scan_id !== scan?.scan_id || anchor.attempt_count !== scan?.attempt_count
        || anchor.frontier_generation !== receipt?.frontier_generation
        || anchor.receipt_snapshot_sha256 !== receipt?.receipt_snapshot_sha256
        || !Array.isArray(sections) || sections.length > 5000) return null;

    const rows = [], hashes = new Set();
    let discovered = 0, chosenV7 = 0, chosen150 = 0, chosen500 = 0, omitted500 = 0;
    for (const row of sections) {
      const { section_sha256: hash, discovered: count, v7_selected_150: v7,
        candidate_selected_150: sameCap, candidate_selected_500: larger } = row || {};
      const selectedCounts = [v7, sameCap, larger];
      if (!sha256Pattern.test(hash || "") || hashes.has(hash) || !Number.isInteger(count) || count < 1 || count > 5000
          || selectedCounts.some(value => !Number.isInteger(value) || value < 0 || value > count)
          || (site.reference_marker && v7 > 0 && sameCap === 0)) return null;
      hashes.add(hash);
      discovered += count;
      chosenV7 += v7;
      chosen150 += sameCap;
      chosen500 += larger;
      baselineOmitted += Number(v7 === 0);
      candidateOmitted += Number(sameCap === 0);
      omitted500 += Number(larger === 0);
      rows.push([hash, count, larger]);
    }
    if (discovered > 5000 || chosenV7 > 149 || chosen150 > 149 || chosen500 > 499
        || evidence.inventory_urls !== discovered || !Number.isInteger(evidence.candidate_selected_urls_500)
        || evidence.candidate_selected_urls_500 < chosen500 || evidence.candidate_selected_urls_500 > 499) return null;
    if (site.expectation !== "throttled_limited") {
      rows.sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0);
      const live = scan?.selection_coverage;
      if (live?.sampling_version !== comparison.candidate_sampling_version || live.inventory_capped !== evidence.inventory_capped
          || live.pages_checked !== scan.pages_crawled || live.inventory_urls !== discovered
          || live.selected_urls !== evidence.candidate_selected_urls_500
          || live.selected_inventory_urls !== chosen500 || live.sections_discovered !== rows.length
          || live.sections_never_selected !== omitted500 || live.sections_sha256 !== sha256(JSON.stringify(rows))) return null;
      signedComparisons++;
    }
  }
  if (candidateOmitted >= baselineOmitted) return null;
  return { baseline_source_sha: selectionBaseline, captures_sha256: comparison.captures_sha256,
    v7_sections_omitted_at_150: baselineOmitted, candidate_sections_omitted_at_150: candidateOmitted,
    signed_candidate_500_matches: signedComparisons, receipt_bound_plan_matches: observations.length };
}

function matchesExpectedOutcome(scan, expectation) {
  if (scan.terminal_outcome_verified !== true) return false;
  if (expectation === "throttled_limited") return scan.outcome === "limited_throttled";
  if (scan.outcome !== "complete") return false;
  if (expectation === "complete_500") return scan.functional_500_verified === true;
  const planned = scan.pages_planned, sampling = scan.selection_coverage;
  return scan.page_cap === 500 && scan.functional_500_verified === false
    && Number.isSafeInteger(planned) && planned > 0 && planned < scan.page_cap && scan.pages_crawled === planned
    && sampling?.pages_checked === planned && sampling.inventory_capped === false
    && Number.isSafeInteger(sampling.inventory_urls) && sampling.inventory_urls > 0 && sampling.inventory_urls < scan.page_cap
    && sha256Pattern.test(sampling.sections_sha256 || "");
}

export async function runCorpus(manifest, { now = Date.now(), execute = false, executeSite, siteId, readPrior,
  verifyOnly = false, compareCompleted, manifestDigest } = {}) {
  const report = { schema_version: "staged_scan_corpus_report_v1", source_sha: manifest?.source_sha, release_fingerprint: manifest?.release_fingerprint,
    dry_run: execute !== true && verifyOnly !== true, verification_only: verifyOnly === true,
    expected_site_count: 50, supplied_site_count: Array.isArray(manifest?.sites) ? manifest.sites.length : 0,
    requested_site_id: siteId ?? null, requested_site_completed: false, corpus_completed: false,
    resource_verified_sites: 0, corpus_resource_evidence_verified: false, corpus_selection_evidence_verified: false, coverage: null,
    production_freeze: false, acceptance_verified: false, full_500_gate: false, scans: [],
    failures: validateCorpusManifest(manifest, now, { historical: verifyOnly }) };
  if (report.failures.length || (!execute && !verifyOnly)) return report;
  if ((verifyOnly && (execute || siteId || typeof readPrior !== "function")) || (execute && typeof executeSite !== "function")) {
    report.failures.push("corpus_execution_mode_invalid");
    return report;
  }
  if (siteId && !manifest.sites.some(site => site.site_id === siteId)) { report.failures.push("selected_site_not_in_manifest"); return report; }
  const pending = [];
  const scanIds = new Set();
  function record(site, result, reused) {
    const scan = result?.report ?? null;
    report.scans.push({ site_id: site.site_id, site_class: site.site_class, reference_marker: site.reference_marker,
      expected_outcome: site.expectation, reused_report: reused, exit_code: result?.exitCode ?? null,
      exit_signal: result?.exitSignal ?? null, report: scan });
    if (result?.exitCode !== 0 || result.exitSignal) { report.failures.push(`canary_execution_failed:${site.site_id}`); return false; }
    if (scan?.schema_version !== "staged_500_canary_v1" || scan.source_sha !== manifest.source_sha || scan.release_fingerprint !== manifest.release_fingerprint || scan.expected_owner_user_id !== site.owner_user_id || scan.project_id !== site.project_id || scan.request_id !== site.request_id || scan.target_url !== site.target_url || !identifier(scan.scan_id) || scanIds.has(scan.scan_id)) { report.failures.push("scan_report_identity_mismatch"); return false; }
    scanIds.add(scan.scan_id);
    if (verifyOnly) {
      const observed = Date.parse(scan.observed_at);
      if (!Number.isFinite(observed) || observed < Date.parse(manifest.reviewed_at) || observed >= Date.parse(manifest.expires_at)) {
        report.failures.push(`scan_outside_corpus_review:${site.site_id}`);
        return false;
      }
    }
    if (!matchesExpectedOutcome(scan, site.expectation)) { report.failures.push(`scan_outcome_mismatch:${site.site_id}`); return false; }
    const verified = verifyReceiptSummary(result.receipt, scan, result.reportDigest);
    const observation = report.scans.at(-1);
    observation.resource_evidence_verified = verified;
    if (scan.durable_worker_receipt_required === true && !verified) {
      report.failures.push(`limited_worker_receipt_unverified:${site.site_id}`);
      return false;
    }
    if (verified) {
      const receipt = result.receipt;
      observation.receipt = {
        worker_revision: receipt.worker_revision,
        frontier_generation: receipt.frontier_generation,
        receipt_snapshot_sha256: receipt.receipt_snapshot_sha256,
        completion_request_bytes: receipt.completion_request.body_bytes,
        completion_request_sha256: receipt.completion_request.body_sha256,
        completion_http_status: receipt.completion_request.status_code,
        sampled_aggregate_rss_peak_bytes: receipt.memory.sampled_aggregate_rss_peak_bytes,
        cgroup_lifetime_peak_upper_bound_bytes: receipt.memory.cgroup_lifetime_peak_upper_bound_bytes,
      };
    }
    if (verified) report.resource_verified_sites++;
    if (site.site_id === siteId) report.requested_site_completed = true;
    return true;
  }

  // Read every prior marker before allowing a new scan. A hole, conflict or
  // uncertain earlier attempt must be resolved by the operator before resuming.
  for (const site of manifest.sites) {
    let prior;
    try { prior = await readPrior?.(site); } catch {
      report.failures.push(`prior_scan_attempt_unverified:${site.site_id}`);
      return report;
    }
    if (prior == null) pending.push(site);
    else {
      if (pending.length) { report.failures.push(`noncontiguous_prior_report:${site.site_id}`); return report; }
      if (!record(site, prior, true)) return report;
    }
  }
  if (siteId && !report.requested_site_completed && pending[0]?.site_id !== siteId) {
    report.failures.push(`selected_site_is_not_next:${siteId}`);
    return report;
  }
  const selected = verifyOnly ? [] : siteId ? (report.requested_site_completed ? [] : pending.slice(0, 1)) : pending;
  for (const site of selected) {
    let result;
    try { result = await executeSite(site); } catch (error) {
      const reason = error instanceof CorpusEvidenceError ? error.message : "canary_execution_failed";
      report.failures.push(`${reason}:${site.site_id}`);
      break;
    }
    if (!record(site, result, false)) break;
  }
  report.corpus_completed = scanIds.size === 50 && report.failures.length === 0;
  if (!siteId && !report.corpus_completed) report.failures.push("corpus_incomplete");
  report.corpus_resource_evidence_verified = report.corpus_completed && report.resource_verified_sites === 50;
  if (report.corpus_completed && !report.corpus_resource_evidence_verified) {
    report.failures.push("full_500_resource_or_runtime_acceptance_unverified");
  }
  if (verifyOnly && report.corpus_resource_evidence_verified) {
    try {
      const comparison = await compareCompleted?.();
      report.coverage = verifyCorpusSelection(comparison, manifest, manifestDigest, report.scans);
    } catch { /* Avoid printing private workspace data or SDK error output. */ }
    report.corpus_selection_evidence_verified = report.coverage !== null;
    if (!report.corpus_selection_evidence_verified) report.failures.push("corpus_selection_evidence_unverified");
  }
  return report;
}

class CorpusEvidenceError extends Error {}

function exists(file) { return Boolean(fs.lstatSync(file, { throwIfNoEntry: false })); }

function readJsonFile(file) {
  const info = fs.lstatSync(file);
  if (!info.isFile()) throw new CorpusEvidenceError("invalid_evidence_file");
  const bytes = fs.readFileSync(file);
  return { value: JSON.parse(bytes), digest: sha256(bytes) };
}

function writeExclusive(file, value) {
  fs.writeFileSync(file, JSON.stringify(value) + "\n", { flag: "wx", mode: 0o600 });
}

export function readSitePrerequisites(directory, site, expected, now = Date.now()) {
  if (!siteIdentifier(site.site_id)) throw new CorpusEvidenceError("site_prerequisites_path_invalid");
  const file = path.join(directory, `${site.site_id}.json`);
  if (!exists(file)) throw new CorpusEvidenceError("site_prerequisites_missing");
  try {
    const { value: packet } = readJsonFile(file);
    const check = validatePrerequisites(packet, { ...expected, now });
    if (check.ready) return { packet, digest: check.provenance.prerequisite_sha256 };
  } catch { /* Invalid evidence is unverified. Never print evidence contents. */ }
  throw new CorpusEvidenceError("site_prerequisites_unverified");
}

// Start/finish markers survive an interruption. A report without both markers
// cannot establish whether retrying the stable request is safe.
export function openCorpusJournal(directory, manifestHash, { requireExisting = false } = {}) {
  const lock = path.join(directory, ".corpus.lock");
  if (!sha256Pattern.test(manifestHash)) throw new CorpusEvidenceError("corpus_journal_manifest_invalid");
  try { writeExclusive(lock, { pid: process.pid }); } catch (error) {
    if (error.code === "EEXIST") throw new CorpusEvidenceError("corpus_journal_locked");
    throw error;
  }
  let closed = false;
  function close() {
    if (closed) return;
    fs.unlinkSync(lock);
    closed = true;
  }
  try {
    const manifestFile = path.join(directory, "manifest.sha256.json");
    if (exists(manifestFile)) {
      if (readJsonFile(manifestFile).value?.manifest_sha256 !== manifestHash) throw new CorpusEvidenceError("corpus_journal_manifest_mismatch");
    } else if (requireExisting) throw new CorpusEvidenceError("corpus_journal_missing");
    else writeExclusive(manifestFile, { manifest_sha256: manifestHash });
  } catch (error) { close(); throw error; }

  function sitePath(site, kind) {
    if (!siteIdentifier(site.site_id)) throw new CorpusEvidenceError("corpus_journal_site_invalid");
    return path.join(directory, `${site.site_id}.${kind}.json`);
  }
  const reportPath = site => sitePath(site, "report");
  const receiptPath = site => sitePath(site, "receipt");
  const started = site => sitePath(site, "started");
  const finished = site => sitePath(site, "finished");
  function readPrior(site) {
    const files = [started(site), finished(site), reportPath(site)];
    if ([...files, receiptPath(site)].every(file => !exists(file))) return null;
    if (!exists(files[0]) || !exists(files[1])) throw new CorpusEvidenceError("prior_scan_attempt_unverified");
    const start = readJsonFile(files[0]).value, finish = readJsonFile(files[1]).value;
    if (start?.manifest_sha256 !== manifestHash || start.site_id !== site.site_id || start.request_id !== site.request_id
        || !sha256Pattern.test(start.prerequisite_sha256) || finish?.manifest_sha256 !== manifestHash
        || finish.site_id !== site.site_id || finish.request_id !== site.request_id) {
      throw new CorpusEvidenceError("prior_scan_attempt_unverified");
    }
    const scan = exists(files[2]) ? readJsonFile(files[2]) : null;
    if ((scan?.digest ?? null) !== finish.report_sha256) throw new CorpusEvidenceError("prior_scan_report_changed");
    if (scan && scan.value?.provenance?.prerequisite_sha256 !== start.prerequisite_sha256) {
      throw new CorpusEvidenceError("prior_scan_prerequisites_changed");
    }
    const receipt = exists(receiptPath(site)) ? readJsonFile(receiptPath(site)) : null;
    if (finish.receipt_sha256 != null && receipt?.digest !== finish.receipt_sha256) {
      throw new CorpusEvidenceError("prior_scan_receipt_changed");
    }
    return { exitCode: finish.exit_code, exitSignal: finish.exit_signal, report: scan?.value ?? null,
      reportDigest: scan?.digest ?? null, receipt: receipt?.value ?? null };
  }
  function begin(site, prerequisiteDigest) {
    if ([started(site), finished(site), reportPath(site), receiptPath(site)].some(exists)) throw new CorpusEvidenceError("prior_scan_attempt_exists");
    if (!sha256Pattern.test(prerequisiteDigest)) throw new CorpusEvidenceError("site_prerequisites_unverified");
    writeExclusive(started(site), { manifest_sha256: manifestHash, site_id: site.site_id,
      request_id: site.request_id, prerequisite_sha256: prerequisiteDigest, observed_at: new Date().toISOString() });
  }
  function finish(site, exitCode, exitSignal) {
    if (!exists(started(site))) throw new CorpusEvidenceError("prior_scan_attempt_unverified");
    const scan = exists(reportPath(site)) ? readJsonFile(reportPath(site)) : null;
    writeExclusive(finished(site), { manifest_sha256: manifestHash, site_id: site.site_id, request_id: site.request_id,
      exit_code: exitCode, exit_signal: exitSignal, report_sha256: scan?.digest ?? null,
      receipt_sha256: exists(receiptPath(site)) ? readJsonFile(receiptPath(site)).digest : null, observed_at: new Date().toISOString() });
    return readPrior(site);
  }
  return { begin, finish, close, readPrior, reportPath, receiptPath };
}

async function executeShell(root, site, manifest, prerequisitesDirectory, journal) {
  if (Date.parse(manifest.expires_at) <= Date.now()) throw new CorpusEvidenceError("corpus_review_missing_or_expired");
  const expected = localAcceptanceIdentity(root, manifest.source_sha, site.owner_user_id);
  if (expected.fingerprint !== manifest.release_fingerprint) throw new CorpusEvidenceError("corpus_fingerprint_mismatch");
  const { packet, digest } = readSitePrerequisites(prerequisitesDirectory, site, expected);
  // Pin the validated packet for the child while its input may be refreshed.
  // The durable journal retains the digest, never the raw prerequisite data.
  const staged = fs.mkdtempSync(path.join(fs.realpathSync(tmpdir()), "fixlist-staged-corpus-"));
  try {
    const prerequisitesFile = path.join(staged, "prerequisites.json");
    writeExclusive(prerequisitesFile, packet);
    journal.begin(site, digest);
    const { exitCode, exitSignal } = await new Promise((resolve, reject) => {
      const child = spawn("bash", [path.join(root, "scripts/run-staged-500-canary.sh")], { cwd: root, stdio: ["ignore", "ignore", "ignore"], env: { ...process.env,
        SOURCE_SHA: manifest.source_sha, EXPECTED_OWNER_USER_ID: site.owner_user_id, PROJECT_ID: site.project_id,
        TARGET_URL: site.target_url, REQUEST_ID: site.request_id, PREREQUISITES_FILE: prerequisitesFile, ACCEPTANCE_OUTPUT: journal.reportPath(site),
        CONFIRM: `RUN-ONE-STAGED-500-CANARY:${manifest.source_sha}:${site.owner_user_id}:${site.project_id}:${site.request_id}` } });
      child.once("error", reject); child.once("exit", (exitCode, exitSignal) => resolve({ exitCode, exitSignal }));
    });
    if (exitCode === 0 && !exitSignal && exists(journal.reportPath(site))) {
      await collectSiteReceipts(root, journal.reportPath(site), journal.receiptPath(site));
    }
    return journal.finish(site, exitCode, exitSignal);
  } finally {
    fs.rmSync(staged, { recursive: true, force: true });
  }
}

async function collectSiteReceipts(root, reportFile, output) {
  const collector = path.join(root, "scanner-api/scripts/collect_staged_scan_receipts.py");
  // Collection is read-only. A credential failure must leave the terminal
  // scan report usable for reconciliation without starting the scan again.
  await new Promise(resolve => {
    execFile("python3", [collector, "--canary-report", reportFile, "--output", output], {
      cwd: root, timeout: 135000, killSignal: "SIGKILL", maxBuffer: 64 * 1024,
    }, () => resolve());
  });
}

async function replayCompletedCorpus(root, rawManifest, evidenceDirectory) {
  const directory = fs.mkdtempSync(path.join(fs.realpathSync(tmpdir()), "fixlist-selection-replay-"));
  try {
    const manifest = path.join(directory, "manifest.json");
    const captures = path.join(directory, "captures.json");
    const comparison = path.join(directory, "comparison.json");
    fs.writeFileSync(manifest, rawManifest, { flag: "wx", mode: 0o600 });
    const python = (name, args, timeout) => new Promise((resolve, reject) => {
      execFile("python3", [path.join(root, "scanner-api/scripts", name), ...args], {
        cwd: root, timeout, killSignal: "SIGKILL", maxBuffer: 64 * 1024,
      }, error => error ? reject(error) : resolve());
    });
    await python("collect_staged_selection_captures.py", ["--manifest", manifest, "--evidence-dir", evidenceDirectory, "--output", captures], 920000);
    await python("compare_staged_scan_selection.py", ["--manifest", manifest, "--captures", captures, "--output", comparison], 120000);
    return readJsonFile(comparison).value;
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

function isOutside(root, file) {
  const relative = path.relative(root, file);
  return relative === ".." || relative.startsWith(`..${path.sep}`);
}

function externalDirectory(root, directory) {
  if (!path.isAbsolute(directory) || !fs.statSync(directory, { throwIfNoEntry: false })?.isDirectory()
      || fs.realpathSync(directory) !== directory || !isOutside(root, directory)) {
    throw new CorpusEvidenceError("corpus_directory_invalid");
  }
  return directory;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  let journal;
  try {
    const { values } = parseArgs({ options: {
      help: { type: "boolean" }, execute: { type: "boolean" }, manifest: { type: "string" },
      output: { type: "string" }, confirm: { type: "string" }, site: { type: "string" },
      "verify-completed": { type: "boolean" },
      "prerequisites-dir": { type: "string" }, "evidence-dir": { type: "string" },
    } });
    if (values.help) {
      console.log(`Usage: node scripts/run-staged-scan-corpus.mjs --manifest reviewed.json [--output /absolute/report.json]
--execute requires --prerequisites-dir /absolute/packets --evidence-dir /absolute/evidence and --output.
Use RUN-STAGED-CORPUS:<source-sha>:<manifest-sha256> with --confirm.
For one site at a time, add --site <site_id> and append :site:<site_id> to the confirmation.
Supply <site_id>.json in the packets directory. The runner reads and checks each packet just before that site.
Resume with the identical manifest and evidence directory, fresh packets for pending sites, and a new aggregate output.
Before submitting, the runner checks prior reports in manifest order. It stops on a failed, conflicting, or unresolved attempt.
Keep an interrupted or failed attempt's files and reconcile the original request ID before considering another submission.
Remove a stale .corpus.lock only after confirming the original runner and all of its children have stopped.
After a terminal scan, the runner collects private stage receipts with Python and existing GCS application credentials.
A missing receipt leaves that site's resource evidence unverified. Keep the terminal scan report for a separate read-only collection.
Use --verify-completed --evidence-dir /absolute/evidence and a new --output to verify a completed
journal. It reads the exact saved plans from GCS and replays v7 and candidate selection without submitting scans.
Default: dry-run. Corpus evidence does not authorize production acceptance.`);
    } else {
      const raw = fs.readFileSync(values.manifest), manifest = JSON.parse(raw.toString("utf8"));
      const root = fs.realpathSync(path.join(path.dirname(fileURLToPath(import.meta.url)), ".."));
      const { execute, output, site: siteId, "verify-completed": verifyOnly } = values;
      const manifestDigest = sha256(raw);
      let evidenceDirectory;
      let prerequisitesDirectory;
      if (execute || verifyOnly) {
        if (verifyOnly && (execute || siteId || values.confirm || values["prerequisites-dir"])) {
          throw new CorpusEvidenceError("corpus_execution_mode_invalid");
        }
        if (siteId !== undefined && !siteIdentifier(siteId)) throw new CorpusEvidenceError("selected_site_invalid");
        const siteConfirmation = siteId ? `:site:${siteId}` : "";
        if (!output || !values["evidence-dir"] || (execute && (!values["prerequisites-dir"]
            || values.confirm !== `RUN-STAGED-CORPUS:${manifest.source_sha}:${manifestDigest}${siteConfirmation}`))) {
          throw new CorpusEvidenceError("exact_corpus_confirmation_output_and_directories_required");
        }
        if (execute) prerequisitesDirectory = externalDirectory(root, values["prerequisites-dir"]);
        evidenceDirectory = externalDirectory(root, values["evidence-dir"]);
        const outputParent = externalDirectory(root, path.dirname(output));
        if (!path.isAbsolute(output) || exists(output) || prerequisitesDirectory === evidenceDirectory
            || [prerequisitesDirectory, evidenceDirectory].includes(outputParent)) {
          throw new CorpusEvidenceError("corpus_output_invalid");
        }
        if (validateCorpusManifest(manifest, Date.now(), { historical: verifyOnly }).length === 0) {
          journal = openCorpusJournal(evidenceDirectory, manifestDigest, { requireExisting: verifyOnly });
        }
      }
      const report = await runCorpus(manifest, { execute, verifyOnly, manifestDigest, siteId, readPrior: journal?.readPrior,
        compareCompleted: async () => {
          // The collector independently checks the journal on both sides of
          // collection, and refuses an active writer.
          journal.close();
          journal = undefined;
          return replayCompletedCorpus(root, raw, evidenceDirectory);
        },
        executeSite: site => executeShell(root, site, manifest, prerequisitesDirectory, journal) });
      if (output) writeNewArtifact(output, report, root);
      console.log(JSON.stringify(report, null, 2));
      if (report.failures.length || (verifyOnly && !report.corpus_selection_evidence_verified)
          || (execute && (siteId ? !report.requested_site_completed : !report.acceptance_verified))) process.exitCode = 1;
    }
  } catch (error) {
    console.error(`STAGED_CORPUS_BLOCKED: ${error instanceof CorpusEvidenceError ? error.message : "corpus_input_or_artifact_error"}`);
    process.exitCode = 2;
  } finally {
    journal?.close();
  }
}
