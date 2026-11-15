import assert from "node:assert/strict";
import test from "node:test";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { assemblePrerequisites, localAcceptanceIdentity, validatePrerequisites, executeStaged500Canary, observeOrdinaryPilotRun, renderOrdinaryReadback, renderRemoteCanary } from "../../scripts/staged_scan_acceptance.mjs";
import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResultV9/projection.js";
import { RELEASE_FINGERPRINT as fingerprint } from "../../base44/functions/getCustomerScanResultV9/generatedReleaseContract.js";
import { emptyGeoReadiness } from "../../base44/functions/getCustomerScanResultV9/geoReadiness.js";
import { openCorpusJournal, readSitePrerequisites, validateCorpusManifest, runCorpus, verifyReceiptSummary } from "../../scripts/run-staged-scan-corpus.mjs";

const now = Date.parse("2026-11-12T10:00:00.000Z");
const sha = "a".repeat(40), owner = "owner_123", project = "project_123";
const names = ["startStandardScanJobV9", "durableScanWorkerControlV9", "persistDurableScanAuthorityV9", "persistLimitedScanResultV9", "getCustomerScanResultV9", "deleteCustomerScanDataV9"];
const routeManifest = "data/generated-staged-v9-routes.json";
const { functions: stagedFunctions } = JSON.parse(readFileSync(new URL("../../" + routeManifest, import.meta.url), "utf8"));
const launchRoute = stagedFunctions.startStandardScanJobV9.route_name;
const resultRoute = stagedFunctions.getCustomerScanResultV9.route_name;
const hash = value => createHash("sha256").update(value).digest("hex");
const stable = value => JSON.stringify(value, Object.keys(value).sort());
const stamp = { observed_at: new Date(now - 1000).toISOString(), expires_at: new Date(now + 600000).toISOString() };
const queue = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-scan-stages";
const workerUrl = "https://canary-00105-abc---worker.run.app";
const stageTag = `staged-${sha.slice(0, 12)}`, stageUrl = `https://${stageTag}---worker.run.app`;
const pilotOperator = "6a498732ec779dfaaeab0e54";

function workerBase44Runtime(expected, revision) {
  return {
    source_sha: expected.sourceSha, worker_revision: revision, transport: "worker_signed_post",
    base44_app_id: "6a498732ec779dfaaeab0e53", base44_origin: "https://base44.app",
    release_fingerprint: expected.fingerprint,
    functions: names.slice(1, 4).map(function_name => ({
      protocol: "fixlist_worker_runtime_v1", function_name, route_name: expected.functions[function_name].route_name,
      action: "identity", http_status: 200,
      release_fingerprint: expected.fingerprint, build_id: expected.functions[function_name].build_id,
      runtime_activation_id: expected.functions[function_name].runtime_activation_id,
    })),
  };
}

function prerequisites() {
  const env = { FIXLIST_WORKER_SOURCE_SHA: sha, SCAN_PIPELINE_MODE: "staged", SCAN_STAGED_OWNER_IDS: owner, SCAN_TASKS_PROJECT: "seo-autopilot-501517", SCAN_TASKS_LOCATION: "europe-west1", SCAN_STAGE_QUEUE: "fixlist-scan-stages", SCAN_STAGE_TASKS_QUEUE_PATH: queue, SCAN_STAGE_TARGET_URL: stageUrl, SCAN_STAGE_TOKEN_AUDIENCE: "https://worker.run.app", SCAN_WORKSPACE_BUCKET: "fixlist-scan-workspaces-seo-autopilot-501517" };
  const observedConfig = Object.fromEntries(Object.entries(env).filter(([key]) => key !== "FIXLIST_WORKER_SOURCE_SHA"));
  const inactiveConfig = { ...observedConfig, SCAN_PIPELINE_MODE: "monolith", SCAN_STAGED_OWNER_IDS: "" };
  const configDigest = hash(JSON.stringify({ environment: JSON.parse(stable(inactiveConfig)), source_sha: sha }));
  env.FIXLIST_STAGED_CONFIG_SHA256 = configDigest;
  const revision = (name, environment) => ({ metadata: { name }, spec: { serviceAccountName: "fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com", containers: [{ env: Object.entries(environment).map(([name, value]) => ({ name, value })) }] }, status: { imageDigest: `image@sha256:${"c".repeat(64)}`, conditions: [{ type: "Ready", status: "True" }] } });
  const local = { sourceSha: sha, fingerprint, ownerId: owner, now,
    functions: structuredClone(stagedFunctions),
    entitySources: Object.fromEntries(["ScanRun", "FixList", "FixItem", "Access"].map(name => [name, JSON.stringify({ name })])),
  };
  const data = { schema_version: "staged_scan_acceptance_prerequisites_v1", ...stamp, source_sha: sha, release_fingerprint: fingerprint,
    base44: { schema_version: "fixlist_staged_v9_readiness_v2", source_sha: sha, app_id: "6a498732ec779dfaaeab0e53", candidate_fingerprint: fingerprint, observed_at: stamp.observed_at,
      functions: names.map(name => ({ name, ...local.functions[name], http_status: 405 })),
      runtime_probe_transport: "base44_native_authenticated_sdk_get",
      anonymous_probe: {
        transport: "base44_legacy_anonymous_get",
        functions: names.map(name => {
          const { route_name, build_id, runtime_activation_id } = local.functions[name];
          return { name, route_name, build_id, runtime_activation_id, state: "matched", http_status: 405 };
        }),
      } },
    schema_readback: { ...stamp, source_sha: sha, app_id: "6a498732ec779dfaaeab0e53", entity_sources: { ...local.entitySources } },
    base44_configuration: { ...stamp, source_sha: sha, intake_route: {
      schema_version: "fixlist_staged_v9_intake_readback_v1", success: true, observed_at: stamp.observed_at,
      build_id: local.functions[names[0]].build_id, runtime_activation_id: local.functions[names[0]].runtime_activation_id,
      release_fingerprint: fingerprint, configured_pipeline_mode: "staged", pipeline_mode: "staged",
      staged_owner_cohort_state: "explicit", staged_owner_count: 1, staged_owner_cohort_sha256: hash(JSON.stringify([owner])),
      staged_owner_enabled: true, intake_gate: "enabled", admission_gate: "enabled",
    } },
    worker: { ...stamp, revision: revision("fixlist-standard150-worker-00105-abc", env), service: { status: { url: "https://worker.run.app", traffic: [{ revisionName: "fixlist-standard150-worker-00105-abc", tag: "canary-00105-abc", url: workerUrl, percent: 0 }, { revisionName: "fixlist-standard150-worker-00105-abc", tag: stageTag, url: stageUrl, percent: 0 }] } }, probe_url: workerUrl, runtime: { source_sha: sha, fingerprint } },
    gateway: { ...stamp, revision: revision("fixlist-dispatch-gateway-g123", { FIXLIST_GATEWAY_SOURCE_SHA: sha, SCAN_PIPELINE_MODE: "staged", SCAN_STAGED_OWNER_IDS: owner, SCAN_CANARY_OWNER_USER_IDS: owner, SCAN_CANARY_WORKER_ORIGIN: workerUrl }), service: { status: { traffic: [{ revisionName: "fixlist-dispatch-gateway-g123", percent: 100 }] } }, runtime: { ok: true, revision: "fixlist-dispatch-gateway-g123", source_sha: sha, pipeline_mode: "staged", staged_owner_count: 1, staged_owner_cohort_sha256: hash(JSON.stringify([owner])), canary_worker_origin: workerUrl, canary_owner_count: 1 } },
    infrastructure: { ...stamp, queue: { name: queue, state: "RUNNING", rateLimits: { maxConcurrentDispatches: 40 }, retryConfig: { maxAttempts: 10, minBackoff: "10s", maxBackoff: "120s", maxDoublings: 4, maxRetryDuration: "1800s" } }, bucket: { name: env.SCAN_WORKSPACE_BUCKET, iamConfiguration: { uniformBucketLevelAccess: { enabled: true }, publicAccessPrevention: "enforced" }, lifecycle: { rule: [{ action: { type: "Delete" }, condition: { age: 30 } }] } }, task: { schema_version: "staged_scan_task_observation_v1", status: "verified_task_metadata",
      source_sha: sha, worker_revision: "fixlist-standard150-worker-00105-abc", worker_config_sha256: configDigest, queue_path: queue,
      observed_at: new Date(now - 3600_000).toISOString(),
      sample: { task_id: "scan-" + "1".repeat(64), stage: "batch", target: stageUrl + "/scan-batch",
        oidc_invoker: "fixlist-standard150-invoker@seo-autopilot-501517.iam.gserviceaccount.com",
        oidc_audience: "https://worker.run.app", dispatch_deadline_seconds: 480, method: "POST" } },
      bucket_policy: { bindings: [{ role: "roles/storage.objectUser", members: ["serviceAccount:fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com"] }] }, queue_policy: { bindings: [{ role: "roles/cloudtasks.enqueuer", members: ["serviceAccount:fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com"] }] }, invoker_policy: { bindings: [{ role: "roles/iam.serviceAccountUser", members: ["serviceAccount:fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com"] }] } },
  };
  data.worker.base44_runtime = workerBase44Runtime(local, data.worker.revision.metadata.name);
  return { data, local };
}

function fakeSdk(scenario = "complete") {
  const calls = [];
  const run = { id: "scan_123456", owner_user_id: owner, project_id: project, request_id: "request_500_123", idempotency_key: "request_500_123", website_url: "https://example.com/", scan_mode: "standard_500", page_cap: 500, pipeline_mode: "staged", status: "complete", pages_crawled: 500, pages_planned: 500, last_committed_batch: 9, attempt_count: 2, started_at: new Date(now - 25000).toISOString(), completed_at: new Date(now).toISOString(), beta_revision_fingerprint: fingerprint, authority_proof: "f".repeat(64), authority_seal_version: "standard_review_snapshot_hmac_identity_v1" };
  const projection = { success: true, scan_id: run.id, authority_verified: true, release_contract_current: true, top_fix_ids: ["fix_1"], run: { ...run, advanced_scan_backend: "python_scanner_api", deno_fallback_used: false, ai_review_backend: "python_review_api", python_review_fallback_used: false, worker_peak_memory_bytes: 123456, private_text: "never-print-private" }, fixItems: [{ fix_id: "fix_1", canonical_action_rank: 1 }] };
  const grant = { id: "grant_123", owner_user_id: owner, user_email: "private@example.com", has_full_access: true, access_status: "active", plan_id: "standard150_lifetime", app_id: "6a498732ec779dfaaeab0e53", grant_source: "manual_grant", granted_at: new Date(now - 86400000).toISOString(), page_cap: 500 };
  if (scenario === "grant150") grant.page_cap = 150;
  if (scenario === "nineBatches") run.last_committed_batch = 8;
  if (scenario === "overCap") run.pages_crawled = 501;
  if (scenario.startsWith("limited")) {
    Object.assign(run, { status: "limited", pages_crawled: 100, last_committed_batch: 1, result_integrity_proof: "f".repeat(64), result_integrity_version: "standard_limited_result_integrity_v5_report_evidence" });
    Object.assign(projection, { authority_verified: false, result_integrity_verified: scenario !== "limitedUnsigned" });
    Object.assign(projection.run, { ...run, score_is_provisional: true, release_gate_eligible: false, coverage_state: "limited_coverage", coverage_reasons: ["staged_wall_budget"], limitation: "Only checked pages are represented." });
    if (scenario === "limitedNoReason") projection.run.coverage_reasons = [];
    if (scenario === "limitedNoPriorities") delete projection.top_fix_ids;
  }
  const track = (name, value) => { calls.push({ name, value }); };
  const sdk = { auth: { me: async () => { track("auth"); return { id: owner, email: "private@example.com", role: ["notAdmin", "ordinary150"].includes(scenario) ? "user" : "admin" }; } }, entities: {
    BusinessProject: { get: async id => { track("project", id); return { id, owner_user_id: owner, website_url: "https://example.com/" }; } },
    Access: { filter: async query => { track("access", query); return scenario === "duplicateGrant" ? [grant, { ...grant, id: "grant_456" }] : [scenario === "ordinary150" ? { ...grant, page_cap: 150 } : grant]; } },
    ScanRun: { get: async () => { track("run"); return run; } },
  }, functions: { invoke: async (name, body) => {
    track(name, body);
    if (name === launchRoute) return { data: { success: true, accepted: true, scan_id: run.id, scan_mode: "standard_500", page_cap: 500, pipeline_mode: "staged" } };
    if (name === resultRoute) return { data: projection };
    throw new Error("unexpected scan route");
  } } };
  return { sdk, calls, run, projection };
}

function config() {
  const { data, local } = prerequisites();
  const prerequisite = validatePrerequisites(data, local);
  assert.equal(prerequisite.ready, true, prerequisite.failures.join(","));
  return { appId: "6a498732ec779dfaaeab0e53", sourceSha: sha, ownerId: owner, projectId: project, targetUrl: "https://example.com/", requestId: "request_500_123", expectedFingerprint: fingerprint, maxWait: 600, pollSeconds: 1, provenance: prerequisite.provenance, launchRoute, resultRoute };
}

function ordinaryPacket(at = now, entitySources) {
  const { data, local } = prerequisites();
  if (entitySources) {
    local.entitySources = entitySources;
    data.schema_readback.entity_sources = entitySources;
  }
  const fresh = { observed_at: new Date(at - 1000).toISOString(), expires_at: new Date(at + 600000).toISOString() };
  Object.assign(data, fresh);
  for (const key of ["base44", "schema_readback", "base44_configuration", "worker", "gateway", "infrastructure"]) {
    Object.assign(data[key], fresh);
  }
  data.infrastructure.task.observed_at = new Date(at - 3600_000).toISOString();
  Object.assign(data.base44_configuration.intake_route, {
    observer_user_id: pilotOperator, route_name: launchRoute, observed_at: fresh.observed_at,
    pipeline_mode: "monolith", staged_owner_enabled: false,
    staged_rollout_scope: "off", staged_500_entitled_enabled: false,
  });
  return { data, local: { ...local, now: at }, expected: { ...local, now: at, ordinaryOperatorId: pilotOperator } };
}

test("the ordinary-user packet verifies the separate operator readback for only the target cohort", () => {
  const { data, local, expected } = ordinaryPacket();
  const check = validatePrerequisites(data, expected);
  assert.equal(check.ready, true, check.failures.join(","));
  assert.deepEqual(check.provenance.ordinary_pilot, { operator_user_id: pilotOperator, owner_user_id: owner });
  assert.equal(validatePrerequisites(data, local).ready, false);
  for (const mutate of [
    v => { v.observer_user_id = owner; },
    v => { delete v.observer_user_id; },
    v => { v.route_name = "startStandardScanJobV9"; },
    v => { delete v.route_name; },
    v => { v.staged_owner_enabled = true; },
    v => { v.pipeline_mode = "staged"; },
    v => { v.staged_owner_cohort_sha256 = hash(JSON.stringify([pilotOperator])); },
  ]) {
    const altered = structuredClone(data);
    mutate(altered.base44_configuration.intake_route);
    assert.equal(validatePrerequisites(altered, expected).ready, false);
  }
  const legacyPacket = structuredClone(data);
  legacyPacket.base44.schema_version = "fixlist_staged_v9_readiness_v1";
  assert.ok(validatePrerequisites(legacyPacket, expected).failures.includes("base44_readiness_identity_mismatch"));
});

test("the authenticated ordinary account can verify a completed native V9 scan without launching work", async t => {
  const receiptTime = Date.now();
  const observationTime = receiptTime - 20 * 60_000;
  const { entitySources } = localAcceptanceIdentity(process.cwd(), sha, owner);
  const { data, expected } = ordinaryPacket(observationTime, entitySources);
  const { provenance } = validatePrerequisites(data, expected);
  assert.ok(provenance);
  assert.ok(Date.parse(data.expires_at) < receiptTime);
  const fake = fakeSdk("notAdmin");
  fake.run.started_at = new Date(observationTime - 25_000).toISOString();
  fake.run.completed_at = new Date(receiptTime - 1_000).toISOString();
  fake.run.admission_mode = "acceptance_only";
  fake.run.admission_acceptance_source_sha = sha;
  fake.run.admission_cohort_evidence_version = "admission_claim_evidence_v1";
  fake.run.admission_cohort_evidence_proof = "e".repeat(64);
  const ordinary = { ...config(), provenance, ordinaryScanId: fake.run.id };
  const operator = {
    auth: { me: async () => ({ id: pilotOperator, email: "londonparisbrussels@gmail.com", role: "admin" }) },
    entities: { ScanRun: { get: async id => { assert.equal(id, fake.run.id); return fake.run; } } },
  };
  await assert.rejects(observeOrdinaryPilotRun({
    auth: { me: async () => ({ id: pilotOperator, email: "londonparisbrussels@gmail.com", role: "user" }) },
  }, ordinary, () => observationTime), /ordinary_operator_identity_mismatch/);
  const observationTimes = [observationTime, receiptTime];
  const operatorReadback = await observeOrdinaryPilotRun(operator, ordinary, () => observationTimes.shift());
  assert.equal(operatorReadback.run.authority_proof_present, true);
  assert.doesNotMatch(JSON.stringify(operatorReadback), /f{64}|e{64}|londonparisbrussels|never-print-private/);
  ordinary.operatorReadback = operatorReadback;
  const run = { ...fake.run, advanced_scan_backend: "python_scanner_api", deno_fallback_used: false,
    ai_review_backend: "python_review_api", python_review_fallback_used: false, geo_readiness: emptyGeoReadiness() };
  const projection = buildCustomerProjection({ run, fullAccess: true, authorityVerified: true });
  assert.equal(projection.run.last_committed_batch, undefined);
  assert.equal(projection.run.authority_proof, undefined);
  fake.sdk.functions.invoke = async (name, payload) => {
    fake.calls.push({ name });
    assert.equal(name, resultRoute);
    assert.deepEqual(payload, { scan_id: fake.run.id });
    return { data: projection };
  };
  delete fake.sdk.entities.ScanRun;
  const report = await executeStaged500Canary(fake.sdk, ordinary, () => receiptTime);
  assert.equal(report.terminal_outcome_verified, true, report.failure_code);
  assert.equal(report.execution_mode, "ordinary_user_readback");
  assert.equal(report.scan_id, fake.run.id);
  assert.equal(report.functional_500_verified, true);
  assert.equal(report.full_500_gate, false);
  assert.equal(report.observed_at, operatorReadback.observed_at);
  assert.equal(report.committed_batch_count, 10);
  assert.ok(fake.calls.some(call => call.name === resultRoute));
  assert.ok(!fake.calls.some(call => call.name === launchRoute));
  const unversioned = await executeStaged500Canary({}, { ...ordinary, resultRoute: "getCustomerScanResultV9" }, () => receiptTime);
  assert.equal(unversioned.failure_code, "staged_scan_routes_unverified");
  projection.run.pages_crawled = 499;
  const discrepant = await executeStaged500Canary(fake.sdk, ordinary, () => receiptTime);
  assert.equal(discrepant.failure_code, "ordinary_customer_projection_mismatch");
  projection.run.pages_crawled = 500;

  const importReadback = config => import(`data:text/javascript;base64,${Buffer.from(renderOrdinaryReadback(config)).toString("base64")}`);
  const browser = await importReadback(ordinary);
  assert.deepEqual(await browser.verifyOrdinaryStaged500Readback(fake.sdk), report);

  const staleConfig = { ...ordinary, provenance: { ...provenance, expires_at: "1970-01-01T00:00:00.000Z" } };
  const module = await importReadback(staleConfig);
  const expired = await module.verifyOrdinaryStaged500Readback({});
  assert.equal(expired.failure_code, "prerequisites_invalid_or_expired");

  const directory = realpathSync(mkdtempSync(path.join(tmpdir(), "ordinary-pilot-")));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const operatorExec = path.join(directory, "operator.log");
  const operatorFile = path.join(directory, "operator.json");
  const browserFile = path.join(directory, "browser.json");
  const reportFile = path.join(directory, "report.json");
  const prerequisitesFile = path.join(directory, "prerequisites.json");
  writeFileSync(prerequisitesFile, JSON.stringify(data));
  const env = { ...process.env, SOURCE_SHA: sha, EXPECTED_OWNER_USER_ID: owner, EXPECTED_OPERATOR_USER_ID: pilotOperator,
    PROJECT_ID: project, REQUEST_ID: fake.run.request_id, TARGET_URL: fake.run.website_url,
    ORDINARY_SCAN_ID: fake.run.id, ORDINARY_OPERATOR_READBACK_FILE: operatorFile, PREREQUISITES_FILE: prerequisitesFile };
  const collect = (mode, input, output) => spawnSync(process.execPath,
    ["scripts/staged_scan_acceptance.mjs", mode, input, output], { env, encoding: "utf8" });
  writeFileSync(operatorExec, "CLI banner\nFIXLIST_STAGED_500_ORDINARY_OPERATOR=" + JSON.stringify(operatorReadback) + "\n");
  const collected = collect("collect-ordinary-operator-readback", operatorExec, operatorFile);
  assert.equal(collected.status, 0, collected.stderr);
  const rendered = spawnSync(process.execPath, ["scripts/staged_scan_acceptance.mjs", "render-ordinary-readback"], { env, encoding: "utf8" });
  assert.equal(rendered.status, 0, rendered.stderr);
  assert.ok(rendered.stdout.includes(resultRoute));
  for (const change of [{ committed_batch_count: 9 }, { terminal_outcome_verified: "yes" }, { full_500_gate: true },
    { acceptance_verified: true }, { production_freeze: true }, { duration_ms: 1 }, { release_fingerprint: "b".repeat(16) }]) {
    writeFileSync(browserFile, JSON.stringify({ ...report, ...change }));
    assert.match(collect("collect-ordinary-readback", browserFile, reportFile).stderr, /ordinary_operator_report_mismatch/);
  }
  const fullOperator = JSON.parse(readFileSync(operatorFile, "utf8"));
  const smallOperator = structuredClone(fullOperator);
  Object.assign(smallOperator.run, { pages_crawled: 22, pages_planned: 22, last_committed_batch: 0 });
  writeFileSync(operatorFile, JSON.stringify(smallOperator));
  writeFileSync(browserFile, JSON.stringify({ ...report, pages_crawled: 22, pages_planned: 22, committed_batch_count: 1,
    progress: [{ status: "complete", pages_crawled: 22, pages_planned: 22, last_committed_batch: 0 }] }));
  assert.match(collect("collect-ordinary-readback", browserFile, reportFile).stderr, /ordinary_operator_report_mismatch/);
  smallOperator.run.last_committed_batch = null;
  writeFileSync(operatorFile, JSON.stringify(smallOperator));
  writeFileSync(browserFile, JSON.stringify({ ...report, functional_500_verified: false,
    pages_crawled: 22, pages_planned: 22, committed_batch_count: 1,
    progress: [{ status: "complete", pages_crawled: 22, pages_planned: 22, last_committed_batch: null }] }));
  assert.match(collect("collect-ordinary-readback", browserFile, reportFile).stderr, /ordinary_operator_readback_identity_mismatch/);
  const limitedOperator = structuredClone(fullOperator);
  Object.assign(limitedOperator.run, { status: "limited", pages_crawled: 22, pages_planned: 100, last_committed_batch: 0,
    result_integrity_proof_present: true, result_integrity_version: "standard_limited_result_integrity_v5_report_evidence",
    termination_reasons: ["staged_wall_budget"] });
  writeFileSync(operatorFile, JSON.stringify(limitedOperator));
  const limitedReport = { ...report, terminal_status: "limited", functional_500_verified: false, pages_crawled: 22,
    pages_planned: 100, committed_batch_count: 1, durable_worker_owned: false, durable_worker_receipt_required: true,
    progress: [{ status: "limited", pages_crawled: 22, pages_planned: 100, last_committed_batch: 0 }] };
  writeFileSync(browserFile, JSON.stringify({ ...limitedReport, outcome: "limited_throttled",
    termination_reasons: ["staged_rate_limit"], throttled_priority_summary: ["critical"] }));
  assert.match(collect("collect-ordinary-readback", browserFile, reportFile).stderr, /ordinary_customer_terminal_evidence_invalid/);
  writeFileSync(browserFile, JSON.stringify({ ...limitedReport, outcome: "limited_budget", termination_reasons: ["staged_wall_budget"] }));
  const limitedReceipt = collect("collect-ordinary-readback", browserFile, path.join(directory, "limited.json"));
  assert.equal(limitedReceipt.status, 0, limitedReceipt.stderr);
  writeFileSync(operatorFile, JSON.stringify({ ...fullOperator, terminal_observed_at: new Date(observationTime).toISOString() }));
  assert.match(collect("collect-ordinary-readback", browserFile, reportFile).stderr, /ordinary_operator_window_invalid/);
  writeFileSync(operatorFile, JSON.stringify(fullOperator));
  writeFileSync(browserFile, JSON.stringify({ ...report, private_extra: "ignore-me", memory: { ...report.memory, private_extra: "ignore-me" } }));
  const combined = collect("collect-ordinary-readback", browserFile, reportFile);
  assert.equal(combined.status, 0, combined.stderr);
  assert.deepEqual(JSON.parse(readFileSync(reportFile, "utf8")), report);
});

test("ordinary readback refuses wrong role, grant, scan, claim, or operator without starting a scan", async () => {
  const { data, expected } = ordinaryPacket();
  const { provenance } = validatePrerequisites(data, expected);
  for (const [scenario, change, failure] of [
    ["complete", {}, "authenticated_ordinary_user_mismatch"],
    ["ordinary150", {}, "existing_entitlement_not_500"],
    ["notAdmin", { request_id: "different_request" }, "scan_identity_mismatch"],
    ["notAdmin", { admission_mode: "open" }, "ordinary_acceptance_claim_mismatch"],
  ]) {
    const fake = fakeSdk(scenario);
    Object.assign(fake.run, { admission_mode: "acceptance_only", admission_acceptance_source_sha: sha, admission_claim_proof_present: true, ...change });
    const operatorReadback = { schema_version: "staged_500_ordinary_operator_readback_v1", operator_user_id: pilotOperator,
      source_sha: sha, prerequisite_sha256: provenance.prerequisite_sha256, observed_at: new Date(now).toISOString(),
      terminal_observed_at: new Date(now).toISOString(), run: fake.run };
    const ordinary = { ...config(), provenance, ordinaryScanId: fake.run.id, operatorReadback };
    delete fake.sdk.entities.ScanRun;
    const result = await executeStaged500Canary(fake.sdk, ordinary, () => now);
    assert.equal(result.failure_code, failure);
    assert.equal(result.terminal_outcome_verified, false);
    assert.ok(!fake.calls.some(call => call.name === launchRoute));
    operatorReadback.operator_user_id = owner;
    assert.equal((await executeStaged500Canary({}, ordinary, () => now)).failure_code, "ordinary_operator_run_missing_or_mismatched");
  }
});

test("prerequisites bind fresh runtime, package, schema, cohort and infrastructure facts", () => {
  const { data, local } = prerequisites();
  assert.equal(validatePrerequisites(data, local).ready, true);
  for (const mutate of [v => { v.expires_at = new Date(now - 1).toISOString(); }, v => { v.worker.runtime.source_sha = "1".repeat(40); }, v => { v.gateway.runtime.staged_owner_cohort_sha256 = "0".repeat(64); }, v => { v.base44.functions[0].build_id = "0".repeat(64); }, v => { v.schema_readback.entity_sources.Access = "{}"; }, v => { v.infrastructure.queue.state = "PAUSED"; }, v => { delete v.base44_configuration; }, v => { v.worker.revision.spec.containers[0].env.find(e => e.name === "SCAN_PIPELINE_MODE").value = "monolith"; }]) {
    const invalid = structuredClone(data); mutate(invalid);
    assert.equal(validatePrerequisites(invalid, local).ready, false);
  }
  assert.equal(validatePrerequisites({ verified: true }, local).ready, false);
});

test("prerequisites require identical versioned routes on SDK and anonymous HTTP runtime evidence", () => {
  const { data, local } = prerequisites();
  for (const [mutate, failure] of [
    [base44 => { base44.schema_version = "fixlist_staged_v9_readiness_v1"; }, "base44_readiness_identity_mismatch"],
    [base44 => { base44.functions[0].route_name = names[0]; }, `base44_package_mismatch:${names[0]}`],
    [base44 => { base44.anonymous_probe.transport = "sdk"; }, "base44_readiness_identity_mismatch"],
    [base44 => { base44.anonymous_probe.functions.pop(); }, "base44_external_inventory_mismatch"],
    [base44 => { base44.anonymous_probe.functions[0].route_name = names[0]; }, `base44_external_runtime_mismatch:${names[0]}`],
    [base44 => { base44.anonymous_probe.functions[0].build_id = "0".repeat(64); }, `base44_external_runtime_mismatch:${names[0]}`],
    [base44 => { base44.anonymous_probe.functions[0].runtime_activation_id = "previous-activation"; }, `base44_external_runtime_mismatch:${names[0]}`],
    [base44 => { base44.anonymous_probe.functions[0].state = "mismatch"; }, `base44_external_runtime_mismatch:${names[0]}`],
    [base44 => { base44.anonymous_probe.functions[0].http_status = 200; }, `base44_external_runtime_mismatch:${names[0]}`],
  ]) {
    const invalid = structuredClone(data);
    mutate(invalid.base44);
    assert.ok(validatePrerequisites(invalid, local).failures.includes(failure));
  }
});

test("prerequisites require an exact worker-signed POST observation for all three runtime routes", () => {
  const { data, local } = prerequisites();
  for (const corrupt of [
    worker => { delete worker.base44_runtime; },
    worker => { worker.base44_runtime.transport = "public_get"; },
    worker => { worker.base44_runtime.base44_origin = "https://staging.example"; },
    worker => { worker.base44_runtime.base44_app_id = "other-app"; },
    worker => { worker.base44_runtime.source_sha = "0".repeat(40); },
    worker => { worker.base44_runtime.worker_revision = "fixlist-standard150-worker-99999-other"; },
    worker => { worker.base44_runtime.release_fingerprint = "0".repeat(16); },
    worker => { worker.base44_runtime.functions.pop(); },
    worker => { worker.base44_runtime.functions[0].route_name = names[1]; },
    worker => { worker.base44_runtime.functions[0].build_id = "0".repeat(64); },
    worker => { worker.base44_runtime.functions[1].runtime_activation_id = "previous-activation"; },
    worker => { worker.base44_runtime.functions[2].http_status = 405; },
    worker => { worker.base44_runtime.functions[2].release_fingerprint = "0".repeat(16); },
  ]) {
    const invalid = structuredClone(data);
    corrupt(invalid.worker);
    assert.ok(validatePrerequisites(invalid, local).failures.includes("worker_base44_runtime_mismatch"));
  }
});

test("the worker stamp binds inactive settings while active owner and route agree independently", () => {
  const { data, local } = prerequisites();
  const env = (packet, component, name) => packet[component].revision.spec.containers[0].env.find(row => row.name === name);
  const check = validatePrerequisites(data, local);
  assert.equal(check.provenance.worker_config_sha256, env(data, "worker", "FIXLIST_STAGED_CONFIG_SHA256").value);
  assert.equal(check.provenance.staged_owner_cohort_sha256, hash(JSON.stringify([owner])));

  for (const [key, value, code] of [
    ["SCAN_STAGE_QUEUE", "other-queue", "worker_configuration_drift"],
    ["SCAN_STAGED_OWNER_IDS", "other_owner", "worker_cohort_mismatch"],
    ["SCAN_STAGED_OWNER_IDS", `${owner},`, "worker_cohort_mismatch"],
    ["SCAN_PIPELINE_MODE", "monolith", "worker_cohort_mismatch"],
  ]) {
    const altered = structuredClone(data);
    env(altered, "worker", key).value = value;
    assert.ok(validatePrerequisites(altered, local).failures.includes(code));
  }
  const activeStamp = structuredClone(data);
  const activeValues = Object.fromEntries(activeStamp.worker.revision.spec.containers[0].env
    .filter(row => row.name.startsWith("SCAN_")).map(row => [row.name, row.value]));
  env(activeStamp, "worker", "FIXLIST_STAGED_CONFIG_SHA256").value = hash(JSON.stringify({
    environment: JSON.parse(stable(activeValues)), source_sha: sha,
  }));
  assert.ok(validatePrerequisites(activeStamp, local).failures.includes("worker_configuration_digest_mismatch"));

  const gateway = structuredClone(data);
  env(gateway, "gateway", "SCAN_STAGED_OWNER_IDS").value = ` ${owner}`;
  assert.ok(validatePrerequisites(gateway, local).failures.includes("gateway_cohort_mismatch"));
  const readback = structuredClone(data);
  readback.base44_configuration.intake_route.staged_owner_cohort_sha256 = hash(JSON.stringify(["other_owner"]));
  assert.ok(validatePrerequisites(readback, local).failures.includes("base44_intake_cohort_mismatch"));
});

test("prerequisites reject coerced traffic, conditional retention and mismatched stage resources", () => {
  const { data, local } = prerequisites();
  for (const value of [false, null, "0", -1, 0.5]) {
    const invalid = structuredClone(data); invalid.worker.service.status.traffic[0].percent = value;
    assert.ok(validatePrerequisites(invalid, local).failures.includes("worker_tag_mapping_mismatch"));
  }
  for (const mutate of [
    v => { v.gateway.service.status.traffic.push({ revisionName: "other-revision", percent: 1 }); },
    v => { v.infrastructure.bucket.lifecycle.rule[0].condition.matchesPrefix = ["only-some-pages/"]; },
    v => { v.worker.service.status.url = "https://another-service.run.app"; },
  ]) {
    const invalid = structuredClone(data); mutate(invalid);
    assert.equal(validatePrerequisites(invalid, local).ready, false);
  }
  const native = structuredClone(data), bucket = native.infrastructure.bucket;
  bucket.uniform_bucket_level_access = true; bucket.public_access_prevention = "enforced"; bucket.lifecycle_config = bucket.lifecycle;
  delete bucket.iamConfiguration; delete bucket.lifecycle;
  assert.equal(validatePrerequisites(native, local).ready, true);
});

test("prerequisite assembly uses fresh live reports and preserves the actual task observation time", () => {
  const { data, local } = prerequisites();
  const schema = {
    schema_version: "fixlist_staged_schema_v1", action: "verify", status: "live_match", live_verified: true,
    readback_verified: true, local_source_verified: true, execution_environment: "production",
    source_sha: sha, app_id: data.base44.app_id, observed_at: stamp.observed_at,
    before_schemas: Object.fromEntries(Object.entries(local.entitySources).map(([name, contents]) => [name, JSON.parse(contents)])),
  };
  const input = { base44: data.base44, schema, intake: data.base44_configuration.intake_route,
    cloud: { ...stamp, schema_version: "staged_scan_gcp_observations_v1", source_sha: sha, release_fingerprint: fingerprint,
      worker: data.worker, gateway: data.gateway, infrastructure: data.infrastructure },
    task: data.infrastructure.task };
  const packet = assemblePrerequisites(input, local, now);
  assert.equal(packet.expires_at, stamp.expires_at);
  assert.deepEqual(packet.worker.base44_runtime, data.worker.base44_runtime);
  assert.equal(packet.infrastructure.task.observed_at, data.infrastructure.task.observed_at);
  for (const [key, value] of [
    ["observed_at", new Date(now - 25 * 3600_000).toISOString()],
    ["worker_revision", "fixlist-standard150-worker-99999-bbb"],
    ["worker_config_sha256", "0".repeat(64)],
  ]) {
    assert.throws(() => assemblePrerequisites({ ...input, task: { ...input.task, [key]: value } }, local, now),
      /stage_task_contract_mismatch/);
  }
  assert.throws(() => assemblePrerequisites({ ...input, schema: { ...schema, live_verified: false } }, local, now),
    /live_observations_unverified/);
  assert.throws(() => assemblePrerequisites({ ...input, intake: { ...input.intake, intake_gate: "disabled" } }, local, now),
    /base44_intake_cohort_mismatch/);
  assert.throws(() => assemblePrerequisites({ ...input, cloud: { ...input.cloud, expires_at: stamp.observed_at } }, local, now),
    /live_observations_stale/);
});

test("raw schema readbacks compare the migration contract rather than JSON formatting", () => {
  const { data, local } = prerequisites();
  const schema = { name: "Access", type: "object", properties: { page_cap: { type: "integer", default: 150, description: "Server-owned cap" } }, rls: { read: { owner_user_id: "{{user.id}}" } } };
  local.entitySources.Access = JSON.stringify(schema, null, 2);
  const remote = structuredClone(schema); delete remote.properties.page_cap.description;
  remote.server_annotation = "preserved by migration";
  data.schema_readback.entity_sources.Access = JSON.stringify(remote);
  assert.equal(validatePrerequisites(data, local).ready, true);
  remote.rls.read = {};
  data.schema_readback.entity_sources.Access = JSON.stringify(remote);
  assert.ok(validatePrerequisites(data, local).failures.includes("schema_readback_mismatch:Access"));
});

test("complete500 requires ten committed batches and retains truthful measurement limits", async () => {
  const fake = fakeSdk();
  const report = await executeStaged500Canary(fake.sdk, config(), () => now);
  assert.equal(report.terminal_outcome_verified, true);
  assert.equal(report.functional_500_verified, true);
  assert.equal(report.production_freeze, false);
  assert.equal(report.full_500_gate, false);
  assert.equal(report.acceptance_verified, false);
  assert.equal(report.scan_id, fake.run.id);
  assert.equal(report.attempt_count, fake.run.attempt_count);
  assert.equal(report.scan_started_at, fake.run.started_at);
  assert.equal(report.scan_completed_at, fake.run.completed_at);
  assert.equal(report.committed_batch_count, 10);
  assert.ok(report.payload_bytes.customer_projection > 0);
  assert.equal(report.payload_bytes.completion_request, null);
  assert.equal(report.memory.scope, "finalize_only");
  assert.equal(report.memory.all_stages_verified, false);
  const starts = fake.calls.filter(call => call.name === launchRoute);
  assert.equal(starts.length, 1);
  assert.equal(starts[0].value.scan_mode, "standard_500");
  assert.equal("page_cap" in starts[0].value, false);
  assert.doesNotMatch(JSON.stringify(report), /private@example|never-print-private|authority_proof/);
});

test("the current signed result carries a private digest of planned sections and a separate checked-page count", async () => {
  const fake = fakeSdk();
  const sampling = {
    sampling_version: "balanced_sitemap_buckets_v9_feasible_ceiling_hub_reservations",
    inventory_capped: true,
    sitemap_urls_discovered: 505, sitemap_urls_selected: 499, pages_checked: 500,
    sections_discovered: { "/set": 502, "/private-section": 3 },
    sections_selected: { "/private-section": 0, "/set": 497 },
    sections_never_selected: ["/private-section"],
  };
  fake.projection.run.sampling_evidence = sampling;
  const report = await executeStaged500Canary(fake.sdk, config(), () => now);
  assert.equal(report.terminal_outcome_verified, true);
  assert.deepEqual(report.selection_coverage, {
    sampling_version: sampling.sampling_version, inventory_capped: true,
    inventory_urls: 505, selected_urls: 499, selected_inventory_urls: 497, pages_checked: 500,
    sections_discovered: 2, sections_never_selected: 1,
    sections_sha256: hash(JSON.stringify([[hash("/set"), 502, 497], [hash("/private-section"), 3, 0]]
      .sort(([left], [right]) => left.localeCompare(right)))),
  });
  assert.doesNotMatch(JSON.stringify(report), /private-section/);

  for (const invalid of [
    { sections_never_selected: ["/set"] }, { pages_checked: 499 },
    { sections_selected: { "/private-section": 0, "/set": 500 } },
    { inventory_capped: 1 },
  ]) {
    fake.projection.run.sampling_evidence = { ...sampling, ...invalid };
    const rejected = await executeStaged500Canary(fake.sdk, config(), () => now);
    assert.equal(rejected.terminal_outcome_verified, true);
    assert.equal(rejected.selection_coverage, null);
    assert.ok(rejected.unverified.includes("signed_selection_coverage"));
  }
  fake.projection.run.sampling_evidence = sampling;
  fake.run.authority_seal_version = "standard_review_snapshot_hmac_v1";
  const historical = await executeStaged500Canary(fake.sdk, config(), () => now);
  assert.equal(historical.terminal_outcome_verified, true);
  assert.equal(historical.selection_coverage, null);
});

test("terminal receipt identity comes from the persisted scan row without coercion or projection fallback", async () => {
  const valid = fakeSdk();
  valid.run.started_at = "2026-11-12T10:59:35+01:00";
  valid.projection.run.attempt_count = 999;
  valid.projection.run.started_at = "2026-11-12T09:40:00.000Z";
  const report = await executeStaged500Canary(valid.sdk, config(), () => now);
  assert.equal(report.terminal_outcome_verified, true);
  assert.equal(report.attempt_count, 2);
  assert.equal(report.scan_started_at, "2026-11-12T10:59:35+01:00");
  assert.equal(report.scan_completed_at, valid.run.completed_at);
  assert.equal(report.duration_ms, 25000);
  for (const [field, value, code] of [
    ["attempt_count", undefined, "scan_attempt_unverified"],
    ["attempt_count", "2", "scan_attempt_unverified"],
    ["attempt_count", 0, "scan_attempt_unverified"],
    ["attempt_count", 2 ** 31, "scan_attempt_unverified"],
    ["started_at", "2026-11-12T09:59:35", "duration_unverified"],
    ["started_at", "2026-02-30T09:59:35Z", "duration_unverified"],
    ["completed_at", "invalid-private-value", "duration_unverified"],
    ["completed_at", "2026-11-12T09:59:34Z", "duration_unverified"],
  ]) {
    const fake = fakeSdk();
    fake.run[field] = value;
    const invalid = await executeStaged500Canary(fake.sdk, config(), () => now);
    assert.equal(invalid.terminal_outcome_verified, false, field);
    assert.equal(invalid.failure_code, code, field);
    assert.equal(invalid.production_freeze, false);
    assert.equal(invalid.full_500_gate, false);
    assert.equal(invalid.acceptance_verified, false);
    assert.doesNotMatch(JSON.stringify(invalid), /invalid-private-value/);
  }
});

for (const scenario of ["grant150", "duplicateGrant", "notAdmin", "nineBatches", "overCap"]) test(`${scenario} cannot satisfy entitled500 acceptance`, async () => {
  const fake = fakeSdk(scenario);
  const report = await executeStaged500Canary(fake.sdk, config(), () => now);
  assert.equal(report.terminal_outcome_verified, false);
  assert.equal(report.full_500_gate, false);
  if (["grant150", "duplicateGrant", "notAdmin"].includes(scenario)) assert.equal(fake.calls.some(call => call.name === launchRoute), false);
});

test("integrity-verified limited evidence is classified separately and cannot pass the full500 gate", async () => {
  const fake = fakeSdk("limited");
  const report = await executeStaged500Canary(fake.sdk, config(), () => now);
  assert.equal(report.terminal_outcome_verified, true);
  assert.equal(report.outcome, "limited_budget");
  assert.equal(report.terminal_status, "limited");
  assert.equal(report.attempt_count, fake.run.attempt_count);
  assert.equal(report.scan_started_at, fake.run.started_at);
  assert.equal(report.scan_completed_at, fake.run.completed_at);
  assert.equal(report.production_freeze, false);
  assert.equal(report.committed_batch_count, 2);
  assert.equal(report.functional_500_verified, false);
  assert.equal(report.full_500_gate, false);
  for (const scenario of ["limitedUnsigned", "limitedNoReason", "limitedNoPriorities"]) {
    assert.equal((await executeStaged500Canary(fakeSdk(scenario).sdk, config(), () => now)).terminal_outcome_verified, false);
  }
});

test("verified throttling needs its causal reason, ranked fixes and exact worker receipt", async () => {
  const fake = fakeSdk("limited");
  for (const key of ["advanced_scan_backend", "ai_review_backend", "python_review_fallback_used"]) delete fake.projection.run[key];
  fake.projection.run.coverage_reasons = ["staged_rate_limit"];
  fake.projection.fixItems = [{ fix_id: "low", priority: "low" }, { fix_id: "high", priority: "high" }];
  fake.projection.top_fix_ids = ["high", "low"];
  const report = await executeStaged500Canary(fake.sdk, config(), () => now);
  assert.equal(report.terminal_outcome_verified, true);
  assert.equal(report.outcome, "limited_throttled");
  assert.equal(report.durable_worker_owned, false);
  assert.equal(report.durable_worker_receipt_required, true);
  assert.deepEqual(report.throttled_priority_summary, ["high", "low"]);
  fake.projection.top_fix_ids.reverse();
  assert.equal((await executeStaged500Canary(fake.sdk, config(), () => now)).failure_code, "throttled_priorities_unverified");
  fake.projection.top_fix_ids.reverse();
  fake.run.result_integrity_version = "standard_limited_result_integrity_v1";
  assert.equal((await executeStaged500Canary(fake.sdk, config(), () => now)).failure_code, "throttled_proof_version_unverified");
  fake.projection.run.coverage_reasons = ["rate_limited"];
  assert.equal((await executeStaged500Canary(fake.sdk, config(), () => now)).failure_code, "limited_termination_reason_missing");

  const input = manifest();
  const result = await runCorpus(input, { execute: true, now, executeSite: async site => ({ exitCode: 0,
    report: { ...corpusScan(site), durable_worker_receipt_required: site.expectation === "throttled_limited" } }) });
  assert.ok(result.failures.includes("limited_worker_receipt_unverified:site_49"));
  assert.equal(result.corpus_completed, false);
});

test("queued progress can precede the first committed batch without being mistaken for terminal evidence", async () => {
  const fake = fakeSdk();
  let observations = 0, time = now;
  fake.sdk.entities.ScanRun.get = async () => observations++ === 0
    ? { ...fake.run, status: "queued", pages_crawled: 0, pages_planned: undefined, last_committed_batch: undefined }
    : fake.run;
  const report = await executeStaged500Canary(fake.sdk, config(), () => time, async ms => { time += ms; });
  assert.equal(report.terminal_outcome_verified, true);
  assert.equal(report.progress[0].last_committed_batch, null);
  assert.equal(report.progress.length, 2);
});

test("pending progress cannot regress and terminal counters cannot be absent", async () => {
  const fake = fakeSdk();
  let observations = 0, time = now;
  fake.sdk.entities.ScanRun.get = async () => ({ ...fake.run, status: "crawling", pages_crawled: observations++ === 0 ? 50 : 49, last_committed_batch: 0 });
  const report = await executeStaged500Canary(fake.sdk, config(), () => time, async ms => { time += ms; });
  assert.equal(report.failure_code, "scan_progress_regressed");
  for (const field of ["pages_crawled", "pages_planned", "last_committed_batch"]) {
    const terminal = fakeSdk(); terminal.run[field] = null;
    const result = await executeStaged500Canary(terminal.sdk, config(), () => now);
    assert.equal(result.terminal_outcome_verified, false);
    assert.equal(result.failure_code, "scan_progress_invalid");
  }
});

test("slow extra batches can verify a terminal result without proving the ten-batch case", async () => {
  const fake = fakeSdk(); fake.run.last_committed_batch = 10;
  const report = await executeStaged500Canary(fake.sdk, config(), () => now);
  assert.equal(report.terminal_outcome_verified, true);
  assert.equal(report.committed_batch_count, 11);
  assert.equal(report.functional_500_verified, false);
});

test("polling timeout preserves one accepted request and does not start another scan", async () => {
  const fake = fakeSdk(); let time = now;
  Object.assign(fake.run, { status: "crawling", pages_crawled: 1, last_committed_batch: undefined });
  fake.projection.run.status = "crawling";
  const report = await executeStaged500Canary(fake.sdk, { ...config(), maxWait: 2 }, () => time, async ms => { time += ms; });
  assert.equal(report.failure_code, "scan_timeout");
  assert.equal(report.scan_id, fake.run.id);
  assert.equal(report.attempt_count, null);
  assert.equal(report.scan_completed_at, null);
  assert.equal(fake.calls.filter(call => call.name === launchRoute).length, 1);
  assert.equal(report.terminal_outcome_verified, false);
});

test("a stalled SDK operation is bounded before scan admission", async () => {
  const fake = fakeSdk(); fake.sdk.auth.me = () => new Promise(() => {});
  const report = await executeStaged500Canary(fake.sdk, { ...config(), maxWait: 1 }, () => now);
  assert.equal(report.failure_code, "operation_timeout");
  assert.equal(fake.calls.some(call => call.name === launchRoute), false);
});

test("a stale versioned launcher or reader is rejected before any SDK call", async () => {
  const fake = fakeSdk();
  for (const [key, logicalName] of [["launchRoute", names[0]], ["resultRoute", names[4]]]) {
    const report = await executeStaged500Canary(fake.sdk, { ...config(), [key]: logicalName + "B" + "0".repeat(16) }, () => now);
    assert.equal(report.failure_code, "staged_scan_routes_unverified");
    assert.equal(report.scan_id, null);
  }
  assert.deepEqual(fake.calls, []);
});

test("SDK exceptions never copy private error strings into acceptance reports", async () => {
  const fake = fakeSdk();
  fake.sdk.auth.me = async () => { throw new Error("never_print_private"); };
  const report = await executeStaged500Canary(fake.sdk, config(), () => now);
  assert.equal(report.failure_code, "remote_operation_failed");
  assert.doesNotMatch(JSON.stringify(report), /never_print_private/);
});

test("rendered remote payload executes the same SDK contract without module imports", async () => {
  const fake = fakeSdk();
  let captured;
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  await new AsyncFunction("base44", "console", "Date", renderRemoteCanary(config()))(fake.sdk, { log(value) { captured = value; } }, class extends Date { static now() { return now; } });
  assert.match(captured, /^FIXLIST_STAGED_500_CANARY=/);
  assert.equal(JSON.parse(captured.split("=").slice(1).join("=")).functional_500_verified, true);
});

function manifest(count = 50) {
  return { schema_version: "staged_scan_corpus_v1", source_sha: sha, release_fingerprint: fingerprint, reviewed_by: "reviewer", reviewed_at: stamp.observed_at, expires_at: stamp.expires_at, sites: Array.from({ length: count }, (_, i) => ({ site_id: `site_${i}`, site_class: ["ecommerce", "content", "local", "mixed"][i % 4], reference_marker: ["funbooker", "pretto", "center_street_lending", "norris_wines"][i] || null, owner_user_id: owner, project_id: `project_${i}`, target_url: `https://site-${i}.example/`, request_id: `corpus_request_${i}`, expectation: i === 49 ? "throttled_limited" : "complete_500" })) };
}

function corpusScan(site, index = Number(site.site_id.split("_").at(-1))) {
  return {
    schema_version: "staged_500_canary_v1", source_sha: sha, release_fingerprint: fingerprint,
    expected_owner_user_id: site.owner_user_id, project_id: site.project_id, request_id: site.request_id,
    target_url: site.target_url, scan_id: `scan_${index}`, terminal_outcome_verified: true,
    observed_at: stamp.observed_at,
    functional_500_verified: site.expectation === "complete_500", full_500_gate: false,
    outcome: site.expectation === "throttled_limited" ? "limited_throttled" : "complete", acceptance_verified: false,
    provenance: { prerequisite_sha256: "d".repeat(64) },
  };
}

test("a corpus requires fifty reviewed distinct sites, references, classes and explicit requests", () => {
  assert.deepEqual(validateCorpusManifest(manifest(), now), []);
  assert.ok(validateCorpusManifest(manifest(4), now).includes("corpus_requires_50_sites"));
  const duplicate = manifest(); duplicate.sites[1].request_id = duplicate.sites[0].request_id;
  assert.ok(validateCorpusManifest(duplicate, now).includes("duplicate_request_id"));
});

test("corpus dry-run starts no scans and complete execution remains sequential and fail-closed", async () => {
  const input = manifest();
  let active = 0, peak = 0, calls = 0;
  const executeSite = async site => { active++; peak = Math.max(peak, active); calls++; await Promise.resolve(); active--; return { exitCode: 0, report: corpusScan(site) }; };
  assert.equal((await runCorpus(input, { now, executeSite })).dry_run, true);
  assert.equal(calls, 0);
  const report = await runCorpus(input, { now, execute: true, executeSite });
  assert.equal(calls, 50); assert.equal(peak, 1);
  assert.equal(report.acceptance_verified, false);
  assert.equal(report.full_500_gate, false);
  assert.equal(report.scans.length, 50);
  const flagsOnly = await runCorpus(input, { now, execute: true, executeSite: async site => ({ exitCode: 0, report: { ...corpusScan(site), full_500_gate: true, acceptance_verified: true } }) });
  assert.equal(flagsOnly.acceptance_verified, false, "Child booleans must not substitute for missing measurement producers");
  const bad = await runCorpus(input, { now, execute: true, executeSite: async site => ({ exitCode: 0, report: { ...corpusScan(site), source_sha: "0".repeat(40) } }) });
  assert.equal(bad.scans.length, 1);
  assert.ok(bad.failures.includes("scan_report_identity_mismatch"));
});

function measuredCorpusScan(site) {
  const limited = site.expectation === "throttled_limited";
  const workerRevision = "fixlist-standard150-worker-00123-abc";
  const report = { ...corpusScan(site), attempt_count: 1, committed_batch_count: limited ? 3 : 10,
    terminal_status: limited ? "limited" : "complete",
    provenance: { prerequisite_sha256: "d".repeat(64), worker_revision: workerRevision } };
  const reportDigest = hash(JSON.stringify(report));
  const deliveryCount = report.committed_batch_count + 2;
  const receipt = {
    schema_version: "staged_500_receipt_evidence_v1", production_freeze: false, canary_report_sha256: reportDigest,
    scan_id: report.scan_id, attempt_count: 1, source_sha: sha, release_fingerprint: fingerprint, worker_revision: workerRevision,
    workspace_bucket: "fixlist-scan-workspaces-seo-autopilot-501517",
    prerequisite_sha256: report.provenance.prerequisite_sha256, terminal_status: report.terminal_status,
    worker_runtime_verified: true, receipt_evidence_verified: true, unverified: [],
    frontier_generation: "157", receipt_snapshot_sha256: "a".repeat(64),
    delivery_count: deliveryCount, committed_delivery_count: deliveryCount,
    completion_request: { function: limited ? "persistLimitedScanResultV9" : "persistDurableScanAuthorityV9",
      body_bytes: 7_172_726, body_sha256: "b".repeat(64), status_code: 200 },
    memory: { all_stages_verified: true, reviewed_worker_memory_limit_bytes: 1024 ** 3,
      parent_sampled_delivery_count: deliveryCount, cgroup_measured_delivery_count: deliveryCount,
      review_sampled_delivery_count: 1, sampled_aggregate_rss_peak_bytes: 200_000_000,
      cgroup_lifetime_peak_upper_bound_bytes: 210_000_000 },
  };
  return { exitCode: 0, report, reportDigest, receipt };
}

test("completed coverage verification joins exact receipt attempts to signed section plans without submitting", async () => {
  const input = manifest();
  input.sites[0].expectation = "complete_below_cap";
  const manifestDigest = hash(JSON.stringify(input));
  const samplingVersion = "balanced_sitemap_buckets_v9_feasible_ceiling_hub_reservations";
  const results = new Map();
  const sites = input.sites.map(site => {
    const original = measuredCorpusScan(site);
    const section = (name, discovered, v7, sameCap, larger) => ({ section_sha256: hash(name), discovered,
      v7_selected_150: v7, candidate_selected_150: sameCap, candidate_selected_500: larger });
    const small = site.expectation === "complete_below_cap";
    const sections = [section("/first", small ? 19 : 502, 1, 1, small ? 19 : 497), section("/second", 3, 0, 1, 2)];
    const receipt = { ...original.receipt };
    const [first, second] = sections;
    const rows = sections.map(row => [row.section_sha256, row.discovered, row.candidate_selected_500])
      .sort(([left], [right]) => left.localeCompare(right));
    const report = { ...original.report, page_cap: 500, pages_crawled: small ? 22 : 500, pages_planned: small ? 22 : 500,
      selection_coverage: site.expectation === "throttled_limited" ? null : {
        sampling_version: samplingVersion, inventory_capped: false, pages_checked: small ? 22 : 500,
        inventory_urls: first.discovered + second.discovered, selected_urls: first.candidate_selected_500 + second.candidate_selected_500,
        selected_inventory_urls: first.candidate_selected_500 + second.candidate_selected_500,
        sections_discovered: 2, sections_never_selected: 0, sections_sha256: hash(JSON.stringify(rows)),
      } };
    if (small) {
      report.committed_batch_count = 1;
      receipt.committed_delivery_count = 3;
    }
    const reportDigest = hash(JSON.stringify(report));
    receipt.canary_report_sha256 = reportDigest;
    results.set(site.site_id, { ...original, report, receipt, reportDigest });
    return { site_id: site.site_id, reference_marker: site.reference_marker, capture_sha256: "d".repeat(64), inventory_capped: false,
      inventory_urls: first.discovered + second.discovered, candidate_selected_urls_500: first.candidate_selected_500 + second.candidate_selected_500, sections,
      claimed_terminal_anchor: { scan_id: report.scan_id, attempt_count: report.attempt_count,
        frontier_generation: receipt.frontier_generation, receipt_snapshot_sha256: receipt.receipt_snapshot_sha256 } };
  });
  const comparison = { schema_version: "staged_scan_selection_comparison_v1", evidence_scope: "offline_replay_of_captured_sitemap_selection",
    baseline_source_sha: "689a7fb43825f322af70188e7426730552daebd9", candidate_source_sha: sha,
    candidate_sampling_version: samplingVersion, release_fingerprint: fingerprint, corpus_manifest_sha256: manifestDigest,
    captures_sha256: "c".repeat(64), site_count: 50, selection_comparison_verified: true, live_terminal_evidence_verified: false, sites };
  let submissions = 0;
  const options = { now, manifestDigest, verifyOnly: true, readPrior: site => results.get(site.site_id),
    executeSite: async () => { submissions++; } };
  const validated = await runCorpus(input, { ...options, compareCompleted: () => comparison });
  assert.equal(validated.corpus_resource_evidence_verified, true);
  assert.equal(validated.corpus_selection_evidence_verified, true);
  assert.deepEqual(validated.coverage, { baseline_source_sha: comparison.baseline_source_sha,
    captures_sha256: comparison.captures_sha256, v7_sections_omitted_at_150: 50, candidate_sections_omitted_at_150: 0,
    signed_candidate_500_matches: 49, receipt_bound_plan_matches: 50 });
  assert.equal(validated.acceptance_verified, false);
  const historical = await runCorpus(input, { ...options, now: now + 60 * 60 * 1000, compareCompleted: () => comparison });
  assert.equal(historical.corpus_selection_evidence_verified, true);
  for (const alter of [
    value => { value.sites[0].sections[0].candidate_selected_150 = 0; },
    value => { value.sites[1].sections[1].candidate_selected_500 = 0; },
    value => { value.sites.at(-1).claimed_terminal_anchor.frontier_generation = "158"; },
    value => { value.corpus_manifest_sha256 = "0".repeat(64); },
  ]) {
    const invalid = structuredClone(comparison); alter(invalid);
    const rejected = await runCorpus(input, { ...options, compareCompleted: () => invalid });
    assert.equal(rejected.corpus_selection_evidence_verified, false);
    assert.ok(rejected.failures.includes("corpus_selection_evidence_unverified"));
  }
  const missing = await runCorpus(input, { ...options, compareCompleted: () => comparison, readPrior: site => site === input.sites.at(-1) ? null : results.get(site.site_id) });
  assert.ok(missing.failures.includes("corpus_incomplete"));
  const uninventoried = await runCorpus(input, { ...options, compareCompleted: () => comparison,
    readPrior: site => {
      const result = structuredClone(results.get(site.site_id));
      if (site === input.sites[0]) result.report.selection_coverage.inventory_urls = 0;
      return result;
    } });
  assert.ok(uninventoried.failures.includes("scan_outcome_mismatch:site_0"));
  assert.equal(submissions, 0);
});

test("the corpus counts receipt evidence only when the trusted collector binds the exact terminal report", async () => {
  const input = manifest();
  const evidence = await runCorpus(input, { now, execute: true, executeSite: async site => measuredCorpusScan(site) });
  assert.equal(evidence.corpus_resource_evidence_verified, true);
  assert.equal(evidence.resource_verified_sites, 50);
  assert.equal(evidence.acceptance_verified, false);
  assert.equal(evidence.full_500_gate, false);
  assert.equal(evidence.scans.at(-1).receipt.completion_request_bytes, 7_172_726);

  const { receipt, report, reportDigest } = measuredCorpusScan(input.sites[0]);
  assert.equal(verifyReceiptSummary(receipt, report, "f".repeat(64)), false);
  assert.equal(verifyReceiptSummary({ ...receipt, attempt_count: 2 }, report, reportDigest), false);
  assert.equal(verifyReceiptSummary({ ...receipt, completion_request: { ...receipt.completion_request, status_code: 413 } }, report, reportDigest), false);
  assert.equal(verifyReceiptSummary({ ...receipt, memory: { ...receipt.memory, cgroup_measured_delivery_count: 0 } }, report, reportDigest), false);
  const incomplete = await runCorpus(input, { now, execute: true, executeSite: async site => {
    const row = measuredCorpusScan(site);
    if (site === input.sites[1]) {
      row.receipt.canary_report_sha256 = "0".repeat(64);
      row.receipt.privatePayload = "do_not_print";
    }
    return row;
  } });
  assert.equal(incomplete.corpus_completed, true);
  assert.equal(incomplete.corpus_resource_evidence_verified, false);
  assert.equal(incomplete.resource_verified_sites, 49);
  assert.ok(incomplete.failures.includes("full_500_resource_or_runtime_acceptance_unverified"));
  assert.doesNotMatch(JSON.stringify(incomplete), /do_not_print/);
});

test("a nonzero child report survives in the aggregate and stops all later sites", async () => {
  let calls = 0;
  const result = await runCorpus(manifest(), { now, execute: true, executeSite: async site => {
    calls++;
    return { exitCode: 1, report: { ...corpusScan(site), terminal_outcome_verified: false, failure_code: "operation_timeout" } };
  } });
  assert.equal(calls, 1);
  assert.equal(result.scans[0].report.failure_code, "operation_timeout");
  assert.equal(result.scans[0].exit_code, 1);
  assert.ok(result.failures.includes("canary_execution_failed:site_0"));
  assert.equal(result.acceptance_verified, false);
});

test("on resume only a verified prefix is skipped and the next site can be selected", async () => {
  const input = manifest(), visited = [], saved = new Map([[input.sites[0].site_id, { exitCode: 0, report: corpusScan(input.sites[0]) }]]);
  const readPrior = async site => saved.get(site.site_id) ?? null;
  const executeSite = async site => { visited.push(site.site_id); return { exitCode: 0, report: corpusScan(site) }; };
  const resumed = await runCorpus(input, { now, siteId: "site_1", readPrior, execute: true, executeSite });
  assert.deepEqual(visited, ["site_1"]);
  assert.deepEqual(resumed.scans.map(row => row.reused_report), [true, false]);
  assert.equal(resumed.requested_site_completed, true);
  const blocked = await runCorpus(input, { now, siteId: "site_3", readPrior, execute: true, executeSite });
  assert.ok(blocked.failures.includes("selected_site_is_not_next:site_3"));
  assert.deepEqual(visited, ["site_1"]);
  saved.set(input.sites[2].site_id, { exitCode: 0, report: corpusScan(input.sites[2]) });
  const gap = await runCorpus(input, { now, readPrior, execute: true, executeSite });
  assert.ok(gap.failures.includes("noncontiguous_prior_report:site_2"));
  assert.deepEqual(visited, ["site_1"]);
  saved.delete(input.sites[2].site_id);
  saved.set(input.sites[1].site_id, { exitCode: 0, report: { ...corpusScan(input.sites[1]), request_id: "different_request" } });
  const conflict = await runCorpus(input, { now, readPrior, execute: true, executeSite });
  assert.ok(conflict.failures.includes("scan_report_identity_mismatch"));
  saved.set(input.sites[1].site_id, { exitCode: 1, report: corpusScan(input.sites[1]) });
  const failed = await runCorpus(input, { now, readPrior, execute: true, executeSite });
  assert.ok(failed.failures.includes("canary_execution_failed:site_1"));
  assert.deepEqual(visited, ["site_1"]);
});

test("a fresh per-site packet can be replaced after expiry without reusing stale evidence", t => {
  const dir = mkdtempSync(path.join(realpathSync(tmpdir()), "fixlist-corpus-prereq-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const { data, local } = prerequisites();
  const [first, second] = manifest().sites;
  writeFileSync(path.join(dir, first.site_id + ".json"), JSON.stringify(data));
  assert.equal(readSitePrerequisites(dir, first, local, now).packet.source_sha, sha);
  assert.throws(() => readSitePrerequisites(dir, second, local, now), /site_prerequisites_missing/);
  writeFileSync(path.join(dir, second.site_id + ".json"), JSON.stringify(data));
  const later = Date.parse(stamp.expires_at) + 2000;
  assert.throws(() => readSitePrerequisites(dir, second, local, later), /site_prerequisites_unverified/);
  const updated = {
    ...data, observed_at: new Date(later - 1000).toISOString(), expires_at: new Date(later + 600000).toISOString(),
  };
  for (const name of ["base44", "schema_readback", "base44_configuration", "worker", "gateway", "infrastructure"]) {
    updated[name] = { ...data[name], observed_at: updated.observed_at, expires_at: updated.expires_at };
  }
  updated.base44_configuration.intake_route = { ...data.base44_configuration.intake_route, observed_at: updated.observed_at };
  writeFileSync(path.join(dir, second.site_id + ".json"), JSON.stringify(updated));
  assert.equal(readSitePrerequisites(dir, second, local, later).packet.observed_at, updated.observed_at);
});

test("the journal refuses concurrent execution or damaged prior attempts without overwriting them", t => {
  const dir = mkdtempSync(path.join(realpathSync(tmpdir()), "fixlist-corpus-journal-"));
  let resumed;
  t.after(() => { resumed?.close(); rmSync(dir, { recursive: true, force: true }); });
  const input = manifest(), manifestHash = hash(JSON.stringify(input)), [first, second] = input.sites;
  const journal = openCorpusJournal(dir, manifestHash);
  assert.throws(() => openCorpusJournal(dir, manifestHash), /corpus_journal_locked/);
  assert.equal(journal.readPrior(first), null);
  journal.begin(first, "d".repeat(64));
  writeFileSync(journal.reportPath(first), JSON.stringify(corpusScan(first)));
  assert.throws(() => journal.readPrior(first), /prior_scan_attempt_unverified/);
  journal.finish(first, 0, null);
  assert.equal(journal.readPrior(first).report.scan_id, "scan_0");
  assert.throws(() => journal.begin(first, "e".repeat(64)), /prior_scan_attempt_exists/);
  writeFileSync(journal.reportPath(second), JSON.stringify(corpusScan(second)));
  assert.throws(() => journal.readPrior(second), /prior_scan_attempt_unverified/);
  journal.close();
  assert.throws(() => openCorpusJournal(dir, "0".repeat(64)), /corpus_journal_manifest_mismatch/);
  resumed = openCorpusJournal(dir, manifestHash);
  assert.equal(resumed.readPrior(first).exitCode, 0);
  writeFileSync(resumed.reportPath(first), JSON.stringify({ ...corpusScan(first), scan_id: "different_scan" }));
  assert.throws(() => resumed.readPrior(first), /prior_scan_report_changed/);
});

test("the corpus CLI journals a failed child and preserves its report across a resume", t => {
  const dir = mkdtempSync(path.join(realpathSync(tmpdir()), "fixlist-corpus-cli-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const repo = path.join(dir, "checkout");
  for (const child of ["checkout/scripts", "checkout/data", "packets", "evidence"]) {
    mkdirSync(path.join(dir, child), { recursive: true });
  }
  for (const script of ["run-staged-scan-corpus.mjs", "staged_scan_acceptance.mjs", "base44_release_manifest.mjs", "base44_authority_schema.mjs"]) {
    copyFileSync(path.join("scripts", script), path.join(repo, "scripts", script));
  }
  symlinkSync(path.resolve("base44"), path.join(repo, "base44"), "dir");
  copyFileSync(routeManifest, path.join(repo, routeManifest));
  writeFileSync(path.join(repo, "data/beta-crawler-revision.json"), JSON.stringify({ fingerprint }));
  const input = manifest(), [first] = input.sites;
  input.reviewed_at = new Date(Date.now() - 1000).toISOString();
  input.expires_at = new Date(Date.now() + 600000).toISOString();
  const raw = JSON.stringify(input);
  const manifestPath = path.join(dir, "reviewed.json");
  writeFileSync(manifestPath, raw);
  const expected = localAcceptanceIdentity(repo, sha, owner);
  const { data } = prerequisites();
  const freshness = { observed_at: input.reviewed_at, expires_at: input.expires_at };
  for (const key of ["base44", "schema_readback", "base44_configuration", "worker", "gateway", "infrastructure"]) {
    Object.assign(data[key], freshness);
  }
  Object.assign(data, freshness);
  data.infrastructure.task.observed_at = new Date(Date.now() - 3600_000).toISOString();
  data.base44.functions = names.map(name => ({ name, ...expected.functions[name], http_status: 405 }));
  data.worker.base44_runtime = workerBase44Runtime(expected, data.worker.revision.metadata.name);
  data.schema_readback.entity_sources = expected.entitySources;
  Object.assign(data.base44_configuration.intake_route, { observed_at: freshness.observed_at,
    build_id: expected.functions[names[0]].build_id, runtime_activation_id: expected.functions[names[0]].runtime_activation_id });
  const check = validatePrerequisites(data, expected);
  assert.equal(check.ready, true, check.failures.join(","));
  writeFileSync(path.join(dir, "packets", first.site_id + ".json"), JSON.stringify(data));
  const report = {
    ...corpusScan(first), scan_id: null, release_fingerprint: null, terminal_outcome_verified: false,
    failure_code: "operation_timeout", provenance: check.provenance,
  };
  const shell = [
    '#!/bin/bash',
    'set -e',
    'test "$REQUEST_ID" = corpus_request_0',
    'cat > "$ACCEPTANCE_OUTPUT" <<\'REPORT\'',
    JSON.stringify(report),
    'REPORT',
    'exit 1',
  ].join("\n");
  writeFileSync(path.join(repo, "scripts/run-staged-500-canary.sh"), shell);
  const run = output => spawnSync(process.execPath, [
    path.join(repo, "scripts/run-staged-scan-corpus.mjs"), "--execute", "--manifest", manifestPath,
    "--prerequisites-dir", path.join(dir, "packets"), "--evidence-dir", path.join(dir, "evidence"),
    "--output", path.join(dir, output), "--site", first.site_id,
    "--confirm", `RUN-STAGED-CORPUS:${sha}:${hash(raw)}:site:${first.site_id}`,
  ], { encoding: "utf8" });
  const firstRun = run("initial.json");
  assert.equal(firstRun.status, 1, firstRun.stderr);
  const original = JSON.parse(readFileSync(path.join(dir, "initial.json")));
  assert.equal(original.scans[0].report.failure_code, "operation_timeout");
  assert.equal(original.scans[0].exit_code, 1);
  assert.equal(original.scans[0].reused_report, false);
  const secondRun = run("resumed.json");
  assert.equal(secondRun.status, 1, secondRun.stderr);
  const resumed = JSON.parse(readFileSync(path.join(dir, "resumed.json")));
  assert.equal(resumed.scans[0].reused_report, true);
  assert.deepEqual(resumed.scans[0].report, original.scans[0].report);
  assert.equal(resumed.acceptance_verified, false);
});

test("500 shell wrapper refuses execution without its exact confirmation", () => {
  const result = spawnSync("bash", ["scripts/run-staged-500-canary.sh"], { encoding: "utf8", env: { ...process.env, CONFIRM: "", SOURCE_SHA: sha } });
  assert.notEqual(result.status, 0);
  assert.doesNotMatch(result.stdout, /CANARY_VERIFIED/);
  assert.match(readFileSync("scripts/run-staged-owner-canary.sh", "utf8"), /EXPECTED_PAGE_CAP.*150/);
});

test("ordinary operator readback does not fall through to the admin launch confirmation", () => {
  const request = "request_500_123";
  const result = spawnSync("bash", ["scripts/run-staged-500-canary.sh"], { encoding: "utf8", env: {
    ...process.env, SOURCE_SHA: sha, EXPECTED_OPERATOR_USER_ID: pilotOperator, EXPECTED_OWNER_USER_ID: owner,
    PROJECT_ID: project, REQUEST_ID: request, ORDINARY_SCAN_ID: "scan_123456",
    CONFIRM: `RUN-ONE-STAGED-500-CANARY:${sha}:${owner}:${project}:${request}`,
  } });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /action-specific confirmation/);
  assert.equal(result.stdout, "");
});
