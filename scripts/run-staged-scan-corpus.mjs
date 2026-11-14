#!/usr/bin/env node
// Default: validate and print a plan. Execution requires an exact manifest hash
// confirmation, existing projects/grants and a fresh packet for each site.
// No synthetic or missing sites are generated to satisfy the fifty-site gate.
import fs from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { parseArgs } from "node:util";
import { writeNewArtifact, localAcceptanceIdentity, validatePrerequisites } from "./staged_scan_acceptance.mjs";

const identifier = value => typeof value === "string" && /^[A-Za-z0-9_-]{6,160}$/.test(value);
const siteIdentifier = value => typeof value === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(value);
const sha256 = value => createHash("sha256").update(value).digest("hex");
const sha256Pattern = /^[a-f0-9]{64}$/;
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
    add(identifier(site?.owner_user_id) && identifier(site?.project_id) && identifier(site?.request_id) && site.request_id.length >= 8 && siteIdentifier(site?.site_id), "corpus_site_identity_invalid");
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

export async function runCorpus(manifest, { now = Date.now(), execute = false, executeSite, siteId, readPrior } = {}) {
  const report = { schema_version: "staged_scan_corpus_report_v1", source_sha: manifest?.source_sha, release_fingerprint: manifest?.release_fingerprint,
    dry_run: execute !== true, expected_site_count: 50, supplied_site_count: Array.isArray(manifest?.sites) ? manifest.sites.length : 0,
    requested_site_id: siteId ?? null, requested_site_completed: false, corpus_completed: false,
    production_freeze: false, acceptance_verified: false, full_500_gate: false, scans: [], failures: validateCorpusManifest(manifest, now) };
  if (report.failures.length || !execute) return report;
  if (typeof executeSite !== "function") { report.failures.push("corpus_executor_missing"); return report; }
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
    if (scan.terminal_outcome_verified !== true || (site.expectation === "complete_500" ? scan.functional_500_verified !== true || scan.outcome !== "complete" : scan.outcome !== "limited_throttled")) { report.failures.push(`scan_outcome_mismatch:${site.site_id}`); return false; }
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
  const selected = siteId ? (report.requested_site_completed ? [] : pending.slice(0, 1)) : pending;
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
  // A truthful throttled limited result belongs in the corpus, but is never a
  // successful full-500 proof. Missing resource/runtime producers keep the
  // rollout gate closed even when all functional outcomes are verified.
  // Child report booleans cannot replace the missing raw measurements. Keep
  // this closed until their producers and independent verification exist.
  report.full_500_gate = false;
  report.acceptance_verified = false;
  if (report.corpus_completed) report.failures.push("full_500_resource_or_runtime_acceptance_unverified");
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
export function openCorpusJournal(directory, manifestHash) {
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
    } else writeExclusive(manifestFile, { manifest_sha256: manifestHash });
  } catch (error) { close(); throw error; }

  function sitePath(site, kind) {
    if (!siteIdentifier(site.site_id)) throw new CorpusEvidenceError("corpus_journal_site_invalid");
    return path.join(directory, `${site.site_id}.${kind}.json`);
  }
  const reportPath = site => sitePath(site, "report");
  const started = site => sitePath(site, "started");
  const finished = site => sitePath(site, "finished");
  function readPrior(site) {
    const files = [started(site), finished(site), reportPath(site)];
    if (files.every(file => !exists(file))) return null;
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
    return { exitCode: finish.exit_code, exitSignal: finish.exit_signal, report: scan?.value ?? null };
  }
  function begin(site, prerequisiteDigest) {
    if ([started(site), finished(site), reportPath(site)].some(exists)) throw new CorpusEvidenceError("prior_scan_attempt_exists");
    if (!sha256Pattern.test(prerequisiteDigest)) throw new CorpusEvidenceError("site_prerequisites_unverified");
    writeExclusive(started(site), { manifest_sha256: manifestHash, site_id: site.site_id,
      request_id: site.request_id, prerequisite_sha256: prerequisiteDigest, observed_at: new Date().toISOString() });
  }
  function finish(site, exitCode, exitSignal) {
    if (!exists(started(site))) throw new CorpusEvidenceError("prior_scan_attempt_unverified");
    const scan = exists(reportPath(site)) ? readJsonFile(reportPath(site)) : null;
    writeExclusive(finished(site), { manifest_sha256: manifestHash, site_id: site.site_id, request_id: site.request_id,
      exit_code: exitCode, exit_signal: exitSignal, report_sha256: scan?.digest ?? null, observed_at: new Date().toISOString() });
    return readPrior(site);
  }
  return { begin, finish, close, readPrior, reportPath };
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
    return journal.finish(site, exitCode, exitSignal);
  } finally {
    fs.rmSync(staged, { recursive: true, force: true });
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
Default: dry-run. Full 500 acceptance requires independent runtime and resource measurements.`);
    } else {
      const raw = fs.readFileSync(values.manifest, "utf8"), manifest = JSON.parse(raw);
      const root = fs.realpathSync(path.join(path.dirname(fileURLToPath(import.meta.url)), ".."));
      const { execute, output, site: siteId } = values;
      let prerequisitesDirectory;
      if (execute) {
        const hash = sha256(raw);
        if (siteId !== undefined && !siteIdentifier(siteId)) throw new CorpusEvidenceError("selected_site_invalid");
        const siteConfirmation = siteId ? `:site:${siteId}` : "";
        if (values.confirm !== `RUN-STAGED-CORPUS:${manifest.source_sha}:${hash}${siteConfirmation}`
            || !output || !values["prerequisites-dir"] || !values["evidence-dir"]) {
          throw new CorpusEvidenceError("exact_corpus_confirmation_output_and_directories_required");
        }
        prerequisitesDirectory = externalDirectory(root, values["prerequisites-dir"]);
        const evidenceDirectory = externalDirectory(root, values["evidence-dir"]);
        const outputParent = externalDirectory(root, path.dirname(output));
        if (!path.isAbsolute(output) || exists(output) || prerequisitesDirectory === evidenceDirectory
            || [prerequisitesDirectory, evidenceDirectory].includes(outputParent)) {
          throw new CorpusEvidenceError("corpus_output_invalid");
        }
        if (validateCorpusManifest(manifest).length === 0) journal = openCorpusJournal(evidenceDirectory, hash);
      }
      const report = await runCorpus(manifest, { execute, siteId, readPrior: journal?.readPrior,
        executeSite: site => executeShell(root, site, manifest, prerequisitesDirectory, journal) });
      if (output) writeNewArtifact(output, report, root);
      console.log(JSON.stringify(report, null, 2));
      if (report.failures.length || (execute && (siteId ? !report.requested_site_completed : !report.acceptance_verified))) process.exitCode = 1;
    }
  } catch (error) {
    console.error(`STAGED_CORPUS_BLOCKED: ${error instanceof CorpusEvidenceError ? error.message : "corpus_input_or_artifact_error"}`);
    process.exitCode = 2;
  } finally {
    journal?.close();
  }
}
