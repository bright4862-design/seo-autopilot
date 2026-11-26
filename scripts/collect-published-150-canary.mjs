#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  APP_ID, localAcceptanceIdentity, operatorReadbackFromExec, ordinaryReadbackContext,
  renderOrdinaryOperatorReadback, validatePrerequisites, writeNewArtifact,
} from "./staged_scan_acceptance.mjs";

const FIXTURE = "https://fixlist-staged-fixture-919035207432.europe-west1.run.app/";
const PUBLIC_ORIGIN = "https://getfixlist.com";
const safeId = value => typeof value === "string" && /^[A-Za-z0-9_-]{6,160}$/.test(value);

function requireEvidence(condition, code) {
  if (!condition) throw new Error(code);
}

function publishedPage(value, pathname) {
  if (typeof value !== "string" || value.length > 500) return null;
  try {
    const url = new URL(value);
    return url.origin === PUBLIC_ORIGIN && url.pathname === pathname
      && !url.username && !url.password && !url.hash ? url : null;
  } catch {
    return null;
  }
}

function hasTerminalProjection(projection, run) {
  const saved = projection?.run;
  let target;
  try {
    target = new URL(saved?.website_url).href;
  } catch {
    return false;
  }
  return projection?.success === true && ["preview", "full"].includes(projection.access)
    && projection.authority_verified === true && projection.release_contract_current === true
    && projection.scan_id === run.id && safeId(projection.fix_list_id)
    && saved?.id === run.id && saved.project_id === run.project_id && target === FIXTURE
    && saved.scan_mode === "standard_150" && saved.page_cap === 150 && saved.pipeline_mode === "staged"
    && saved.status === "complete" && saved.pages_crawled === 150 && saved.pages_planned === 150
    && saved.beta_revision_fingerprint === run.beta_revision_fingerprint;
}

// The inputs are field-only observations from the actual authenticated browser.
// These comparisons cannot establish events that were not observed there.
export function collectPublished150Canary(context, browser) {
  const { operator, provenance } = context;
  const run = operator.run;
  const saved = browser?.saved_projection;
  const reopened = browser?.history_projection;
  const history = publishedPage(browser?.history_url, "/dashboard");
  const historyId = history?.searchParams.getAll("scan_id");
  const requiredRoutes = Object.fromEntries(provenance.base44_functions.map(row => [row.name, row.route_name]));
  const reopenedAt = Date.parse(browser?.history_reopened_at);
  const completedAt = Date.parse(run.completed_at);
  requireEvidence(browser?.schema_version === "published_150_browser_readback_v1"
    && browser.source_sha === provenance.source_sha && browser.owner_user_id === run.owner_user_id
    && browser.role === "user" && browser.launched_by_form === true
    && publishedPage(browser.launch_url, "/onboarding")?.search === ""
    && browser.displayed_page_cap === 150 && browser.launch?.accepted === true
    && browser.launch_route === requiredRoutes.startStandardScanJobV9
    && browser.launch.scan_id === run.id && browser.launch.request_id === run.request_id
    && browser.launch.page_cap === 150 && browser.launch.scan_mode === "standard_150"
    && browser.launch.pipeline_mode === "staged" && browser.refreshed_during_progress === true,
  "published_browser_launch_unverified");
  requireEvidence(historyId?.length === 1 && historyId[0] === run.id && browser.reopened_from_history === true
    && browser.result_route === requiredRoutes.getCustomerScanResultV9
    && browser.reopened_after_sign_in === true && Number.isFinite(reopenedAt)
    && reopenedAt >= completedAt && reopenedAt <= Date.now() + 30_000
    && hasTerminalProjection(saved, run) && hasTerminalProjection(reopened, run)
    && saved.fix_list_id === reopened.fix_list_id && saved.access === reopened.access,
  "published_browser_history_unverified");
  requireEvidence(context.complete === true && context.batches === 3
    && run.target_cooldown_publication !== "unconfirmed", "published_fixture_terminal_state_unverified");
  return {
    schema_version: "staged_150_published_canary_v1",
    execution_mode: "ordinary_user_readback",
    production_freeze: false,
    acceptance_verified: false,
    terminal_outcome_verified: true,
    durable_worker_owned: true,
    authority_verified: true,
    terminal_status: "complete",
    page_cap: 150,
    pages_crawled: 150,
    pages_planned: 150,
    committed_batch_count: 3,
    scan_id: run.id,
    attempt_count: run.attempt_count,
    request_id: run.request_id,
    expected_owner_user_id: run.owner_user_id,
    project_id: run.project_id,
    target_url: FIXTURE,
    source_sha: provenance.source_sha,
    release_fingerprint: provenance.release_fingerprint,
    observed_at: operator.observed_at,
    scan_started_at: run.started_at,
    scan_completed_at: run.completed_at,
    provenance,
    browser: {
      host: PUBLIC_ORIGIN,
      access: saved.access,
      history_reopened_at: browser.history_reopened_at,
      evidence_sha256: createHash("sha256").update(JSON.stringify(browser)).digest("hex"),
    },
  };
}

function readJSON(filename) {
  try {
    requireEvidence(path.isAbsolute(filename) && fs.realpathSync(filename) === filename, "invalid_path");
    const file = fs.statSync(filename);
    requireEvidence(file.isFile() && file.size <= 2 * 1024 * 1024, "invalid_file");
    return JSON.parse(fs.readFileSync(filename, "utf8"));
  } catch {
    throw new Error("readback_input_unavailable");
  }
}

function candidateIdentity(root, env) {
  requireEvidence(path.isAbsolute(root) && fs.realpathSync(root) === root
    && typeof env.SOURCE_SHA === "string" && /^[a-f0-9]{40}$/.test(env.SOURCE_SHA)
    && safeId(env.EXPECTED_OWNER_USER_ID) && safeId(env.EXPECTED_OPERATOR_USER_ID)
    && safeId(env.ORDINARY_SCAN_ID) && safeId(env.PROJECT_ID) && safeId(env.REQUEST_ID),
  "published_fixture_input_invalid");
  const git = (...args) => execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  requireEvidence(git("rev-parse", "--show-toplevel") === root && git("rev-parse", "HEAD") === env.SOURCE_SHA
    && !git("status", "--porcelain", "--untracked-files=all"), "candidate_checkout_not_pinned");
  return {
    ...localAcceptanceIdentity(root, env.SOURCE_SHA, env.EXPECTED_OWNER_USER_ID),
    ordinaryOperatorId: env.EXPECTED_OPERATOR_USER_ID,
    allowDeferredOrdinaryTask: true,
  };
}

function main([mode, root, prereq, ...args], env) {
  requireEvidence((mode === "render-operator" && args.length === 0)
    || (mode === "collect" && args.length === 3), "published_fixture_operation_invalid");
  const expected = candidateIdentity(root, env);
  const packet = readJSON(prereq);
  if (mode === "render-operator") {
    const validation = validatePrerequisites(packet, expected);
    requireEvidence(validation.ready, validation.failures.join(","));
    process.stdout.write(renderOrdinaryOperatorReadback({
      appId: APP_ID, sourceSha: expected.sourceSha, ownerId: expected.ownerId,
      projectId: env.PROJECT_ID, requestId: env.REQUEST_ID, targetUrl: FIXTURE,
      ordinaryScanId: env.ORDINARY_SCAN_ID, ordinaryPageCap: 150,
      provenance: validation.provenance, maxWait: 1_800, pollSeconds: 5,
    }));
    return;
  }
  const [operatorLog, browserFile, output] = args;
  const context = ordinaryReadbackContext(packet, expected, operatorReadbackFromExec(operatorLog, 150),
    { ...env, TARGET_URL: FIXTURE }, { cap: 150, verifyTask: true });
  const report = collectPublished150Canary(context, readJSON(browserFile));
  writeNewArtifact(output, report, root);
  console.log("PUBLISHED_150_CANARY_EVIDENCE_SAVED receipt_verification_pending=true");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main(process.argv.slice(2), process.env);
  } catch (error) {
    const code = /^[a-z0-9_,:-]{1,400}$/.test(error?.message || "") ? error.message : "verification_failed";
    console.error(`PUBLISHED_150_CANARY_BLOCKED: ${code}`);
    process.exitCode = 2;
  }
}
