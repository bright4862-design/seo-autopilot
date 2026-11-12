import assert from "node:assert/strict";
import test from "node:test";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { validatePrerequisites, executeStaged500Canary, renderRemoteCanary } from "../../scripts/staged_scan_acceptance.mjs";
import { validateCorpusManifest, runCorpus } from "../../scripts/run-staged-scan-corpus.mjs";

const now = Date.parse("2026-11-12T10:00:00.000Z");
const sha = "a".repeat(40), fingerprint = "b".repeat(16), owner = "owner_123", project = "project_123";
const names = ["startStandardScanJobV9", "durableScanWorkerControlV9", "persistDurableScanAuthorityV9", "persistLimitedScanResultV9", "getCustomerScanResultV9", "deleteCustomerScanDataV9"];
const hash = value => createHash("sha256").update(value).digest("hex");
const stable = value => JSON.stringify(value, Object.keys(value).sort());
const stamp = { observed_at: new Date(now - 1000).toISOString(), expires_at: new Date(now + 600000).toISOString() };
const queue = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-scan-stages";
const workerUrl = "https://canary-00105-abc---worker.run.app";

function prerequisites() {
  const env = { FIXLIST_WORKER_SOURCE_SHA: sha, SCAN_PIPELINE_MODE: "staged", SCAN_STAGED_OWNER_IDS: owner, SCAN_TASKS_PROJECT: "seo-autopilot-501517", SCAN_TASKS_LOCATION: "europe-west1", SCAN_STAGE_QUEUE: "fixlist-scan-stages", SCAN_STAGE_TASKS_QUEUE_PATH: queue, SCAN_STAGE_TARGET_URL: workerUrl, SCAN_STAGE_TOKEN_AUDIENCE: "https://worker.run.app", SCAN_WORKSPACE_BUCKET: "fixlist-scan-workspaces-seo-autopilot-501517" };
  const observedConfig = Object.fromEntries(Object.entries(env).filter(([key]) => key !== "FIXLIST_WORKER_SOURCE_SHA"));
  const configDigest = hash(JSON.stringify({ environment: JSON.parse(stable(observedConfig)), source_sha: sha }));
  env.FIXLIST_STAGED_CONFIG_SHA256 = configDigest;
  const revision = (name, environment) => ({ metadata: { name }, spec: { serviceAccountName: "worker@example.iam.gserviceaccount.com", containers: [{ env: Object.entries(environment).map(([name, value]) => ({ name, value })) }] }, status: { imageDigest: `image@sha256:${"c".repeat(64)}`, conditions: [{ type: "Ready", status: "True" }] } });
  const local = { sourceSha: sha, fingerprint, ownerId: owner, now,
    functions: Object.fromEntries(names.map(name => [name, { build_id: "d".repeat(64), package_digest: "e".repeat(64), runtime_activation_id: `${name}-runtime` }])),
    entitySources: Object.fromEntries(["ScanRun", "FixList", "FixItem", "Access"].map(name => [name, JSON.stringify({ name })])),
  };
  const data = { schema_version: "staged_scan_acceptance_prerequisites_v1", ...stamp, source_sha: sha, release_fingerprint: fingerprint,
    base44: { schema_version: "fixlist_staged_v9_readiness_v1", source_sha: sha, app_id: "6a498732ec779dfaaeab0e53", candidate_fingerprint: fingerprint, observed_at: stamp.observed_at,
      functions: names.map(name => ({ name, ...local.functions[name], http_status: 405 })) },
    schema_readback: { ...stamp, source_sha: sha, app_id: "6a498732ec779dfaaeab0e53", entity_sources: { ...local.entitySources } },
    base44_configuration: { ...stamp, source_sha: sha, function_environments: Object.fromEntries(names.map(name => [name, { SCAN_PIPELINE_MODE: "staged", SCAN_STAGED_OWNER_IDS: owner }])) },
    worker: { ...stamp, revision: revision("fixlist-standard150-worker-00105-abc", env), service: { status: { url: "https://worker.run.app", traffic: [{ revisionName: "fixlist-standard150-worker-00105-abc", tag: "canary-00105-abc", url: workerUrl, percent: 0 }] } }, probe_url: workerUrl, runtime: { source_sha: sha, fingerprint } },
    gateway: { ...stamp, revision: revision("fixlist-dispatch-gateway-g123", { FIXLIST_GATEWAY_SOURCE_SHA: sha, SCAN_PIPELINE_MODE: "staged", SCAN_STAGED_OWNER_IDS: owner, SCAN_CANARY_OWNER_USER_IDS: owner, SCAN_CANARY_WORKER_ORIGIN: workerUrl }), service: { status: { traffic: [{ revisionName: "fixlist-dispatch-gateway-g123", percent: 100 }] } }, runtime: { ok: true, revision: "fixlist-dispatch-gateway-g123", source_sha: sha, pipeline_mode: "staged", staged_owner_count: 1, staged_owner_cohort_sha256: hash(JSON.stringify([owner])), canary_worker_origin: workerUrl, canary_owner_count: 1 } },
    infrastructure: { ...stamp, queue: { name: queue, state: "RUNNING", rateLimits: { maxConcurrentDispatches: 40 }, retryConfig: { maxAttempts: 10, minBackoff: "10s", maxBackoff: "120s", maxDoublings: 4, maxRetryDuration: "1800s" } }, bucket: { name: env.SCAN_WORKSPACE_BUCKET, iamConfiguration: { uniformBucketLevelAccess: { enabled: true }, publicAccessPrevention: "enforced" }, lifecycle: { rule: [{ action: { type: "Delete" }, condition: { age: 30 } }] } }, task: { httpRequest: { httpMethod: "POST", url: workerUrl + "/scan-batch", oidcToken: { serviceAccountEmail: "invoker@example.iam.gserviceaccount.com", audience: "https://worker.run.app" } }, dispatchDeadline: "480s" }, invoker_service_account: "invoker@example.iam.gserviceaccount.com",
      bucket_policy: { bindings: [{ role: "roles/storage.objectUser", members: ["serviceAccount:worker@example.iam.gserviceaccount.com"] }] }, queue_policy: { bindings: [{ role: "roles/cloudtasks.enqueuer", members: ["serviceAccount:worker@example.iam.gserviceaccount.com"] }] }, invoker_policy: { bindings: [{ role: "roles/iam.serviceAccountUser", members: ["serviceAccount:worker@example.iam.gserviceaccount.com"] }] } },
  };
  return { data, local };
}

function fakeSdk(scenario = "complete") {
  const calls = [];
  const run = { id: "scan_123456", owner_user_id: owner, project_id: project, request_id: "request_500_123", idempotency_key: "request_500_123", website_url: "https://example.com/", scan_mode: "standard_500", page_cap: 500, pipeline_mode: "staged", status: "complete", pages_crawled: 500, pages_planned: 500, last_committed_batch: 9, started_at: new Date(now - 60000).toISOString(), completed_at: new Date(now).toISOString(), beta_revision_fingerprint: fingerprint, authority_proof: "f".repeat(64), authority_seal_version: "standard_review_snapshot_hmac_identity_v1" };
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
  const sdk = { auth: { me: async () => { track("auth"); return { id: owner, email: "private@example.com", role: scenario === "notAdmin" ? "user" : "admin" }; } }, entities: {
    BusinessProject: { get: async id => { track("project", id); return { id, owner_user_id: owner, website_url: "https://example.com/" }; } },
    Access: { filter: async query => { track("access", query); return scenario === "duplicateGrant" ? [grant, { ...grant, id: "grant_456" }] : [grant]; } },
    ScanRun: { get: async () => { track("run"); return run; } },
  }, functions: { invoke: async (name, body) => { track(name, body); return name === "startStandardScanJobV9" ? { data: { success: true, accepted: true, scan_id: run.id, scan_mode: "standard_500", page_cap: 500, pipeline_mode: "staged" } } : { data: projection }; } } };
  return { sdk, calls, run, projection };
}

function config() {
  const { data, local } = prerequisites();
  const prerequisite = validatePrerequisites(data, local);
  assert.equal(prerequisite.ready, true, prerequisite.failures.join(","));
  return { appId: "6a498732ec779dfaaeab0e53", sourceSha: sha, ownerId: owner, projectId: project, targetUrl: "https://example.com/", requestId: "request_500_123", expectedFingerprint: fingerprint, maxWait: 600, pollSeconds: 1, provenance: prerequisite.provenance };
}

test("prerequisites bind fresh runtime, package, schema, cohort and infrastructure facts", () => {
  const { data, local } = prerequisites();
  assert.equal(validatePrerequisites(data, local).ready, true);
  for (const mutate of [v => { v.expires_at = new Date(now - 1).toISOString(); }, v => { v.worker.runtime.source_sha = "1".repeat(40); }, v => { v.gateway.runtime.staged_owner_cohort_sha256 = "0".repeat(64); }, v => { v.base44.functions[0].build_id = "0".repeat(64); }, v => { v.schema_readback.entity_sources.Access = "{}"; }, v => { v.infrastructure.queue.state = "PAUSED"; }, v => { delete v.base44_configuration; }, v => { v.worker.revision.spec.containers[0].env.find(e => e.name === "SCAN_PIPELINE_MODE").value = "monolith"; }]) {
    const invalid = structuredClone(data); mutate(invalid);
    assert.equal(validatePrerequisites(invalid, local).ready, false);
  }
  assert.equal(validatePrerequisites({ verified: true }, local).ready, false);
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
  assert.equal(report.full_500_gate, false);
  assert.equal(report.acceptance_verified, false);
  assert.equal(report.committed_batch_count, 10);
  assert.ok(report.payload_bytes.customer_projection > 0);
  assert.equal(report.payload_bytes.completion_request, null);
  assert.equal(report.memory.scope, "finalize_only");
  assert.equal(report.memory.all_stages_verified, false);
  const starts = fake.calls.filter(call => call.name === "startStandardScanJobV9");
  assert.equal(starts.length, 1);
  assert.equal(starts[0].value.scan_mode, "standard_500");
  assert.equal("page_cap" in starts[0].value, false);
  assert.doesNotMatch(JSON.stringify(report), /private@example|never-print-private|authority_proof/);
});

for (const scenario of ["grant150", "duplicateGrant", "notAdmin", "nineBatches", "overCap"]) test(`${scenario} cannot satisfy entitled500 acceptance`, async () => {
  const fake = fakeSdk(scenario);
  const report = await executeStaged500Canary(fake.sdk, config(), () => now);
  assert.equal(report.terminal_outcome_verified, false);
  assert.equal(report.full_500_gate, false);
  if (["grant150", "duplicateGrant", "notAdmin"].includes(scenario)) assert.equal(fake.calls.some(call => call.name === "startStandardScanJobV9"), false);
});

test("integrity-verified limited evidence is classified separately and cannot pass the full500 gate", async () => {
  const fake = fakeSdk("limited");
  const report = await executeStaged500Canary(fake.sdk, config(), () => now);
  assert.equal(report.terminal_outcome_verified, true);
  assert.equal(report.outcome, "limited_budget");
  assert.equal(report.committed_batch_count, 2);
  assert.equal(report.functional_500_verified, false);
  assert.equal(report.full_500_gate, false);
  for (const scenario of ["limitedUnsigned", "limitedNoReason", "limitedNoPriorities"]) {
    assert.equal((await executeStaged500Canary(fakeSdk(scenario).sdk, config(), () => now)).terminal_outcome_verified, false);
  }
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
  assert.equal(fake.calls.filter(call => call.name === "startStandardScanJobV9").length, 1);
  assert.equal(report.terminal_outcome_verified, false);
});

test("a stalled SDK operation is bounded before scan admission", async () => {
  const fake = fakeSdk(); fake.sdk.auth.me = () => new Promise(() => {});
  const report = await executeStaged500Canary(fake.sdk, { ...config(), maxWait: 1 }, () => now);
  assert.equal(report.failure_code, "operation_timeout");
  assert.equal(fake.calls.some(call => call.name === "startStandardScanJobV9"), false);
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

test("a corpus requires fifty reviewed distinct sites, references, classes and explicit requests", () => {
  assert.deepEqual(validateCorpusManifest(manifest(), now), []);
  assert.ok(validateCorpusManifest(manifest(4), now).includes("corpus_requires_50_sites"));
  const duplicate = manifest(); duplicate.sites[1].request_id = duplicate.sites[0].request_id;
  assert.ok(validateCorpusManifest(duplicate, now).includes("duplicate_request_id"));
});

test("corpus dry-run starts no scans and complete execution remains sequential and fail-closed", async () => {
  const input = manifest();
  let active = 0, peak = 0, calls = 0;
  const executeSite = async site => { active++; peak = Math.max(peak, active); calls++; await Promise.resolve(); active--; return { schema_version: "staged_500_canary_v1", source_sha: sha, release_fingerprint: fingerprint, expected_owner_user_id: site.owner_user_id, project_id: site.project_id, request_id: site.request_id, target_url: site.target_url, scan_id: `scan_${calls}`, terminal_outcome_verified: true, functional_500_verified: true, full_500_gate: false, outcome: site.expectation === "throttled_limited" ? "limited_throttled" : "complete", acceptance_verified: false }; };
  assert.equal((await runCorpus(input, { now, executeSite })).dry_run, true);
  assert.equal(calls, 0);
  const report = await runCorpus(input, { now, execute: true, executeSite });
  assert.equal(calls, 50); assert.equal(peak, 1);
  assert.equal(report.acceptance_verified, false);
  assert.equal(report.full_500_gate, false);
  assert.equal(report.scans.length, 50);
  const flagsOnly = await runCorpus(input, { now, execute: true, executeSite: async site => ({ ...await executeSite(site), full_500_gate: true, acceptance_verified: true }) });
  assert.equal(flagsOnly.acceptance_verified, false, "Child booleans must not substitute for missing measurement producers");
  const bad = await runCorpus(input, { now, execute: true, executeSite: async site => ({ ...await executeSite(site), source_sha: "0".repeat(40) }) });
  assert.equal(bad.scans.length, 1);
  assert.ok(bad.failures.includes("scan_report_identity_mismatch"));
});

test("500 shell wrapper refuses execution without its exact confirmation", () => {
  const result = spawnSync("bash", ["scripts/run-staged-500-canary.sh"], { encoding: "utf8", env: { ...process.env, CONFIRM: "", SOURCE_SHA: sha } });
  assert.notEqual(result.status, 0);
  assert.doesNotMatch(result.stdout, /CANARY_VERIFIED/);
  assert.match(readFileSync("scripts/run-staged-owner-canary.sh", "utf8"), /EXPECTED_PAGE_CAP.*150/);
});
