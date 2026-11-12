#!/usr/bin/env node
// Offline validation and a self-contained Base44 exec payload. No collector in
// this module deploys, changes a grant/cohort, or calls a cloud API.
//
// Prerequisite packet v1 contains fresh raw observations, not verified:true:
// base44 = existing fixlist_staged_v9_readiness_v1 report;
// schema_readback.entity_sources = exact pulled .jsonc file contents;
// base44_configuration.function_environments = observed staged settings;
// worker/gateway = Cloud Run revision+service exports and bound runtime probes;
// infrastructure = bucket/queue/IAM/existing-task JSON used by the verifier.
// Every observation has observed_at/expires_at, within a 15 minute window.
// A producer assembling these observations is still required. Existing schema,
// Base44 configuration and infrastructure tools do not emit this packet.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { buildManifest, STAGED_RELEASE_FUNCTIONS, STAGED_RELEASE_ENTITIES } from "./base44_release_manifest.mjs";
import { diffEntity } from "./base44_authority_schema.mjs";

export const APP_ID = "6a498732ec779dfaaeab0e53";
export const MISSING_PRODUCERS = ["fresh_prerequisite_packet_collector", "completion_request_byte_measurement", "all_stage_memory_measurement", "per_scan_runtime_revision_receipt"];
const sha256 = value => createHash("sha256").update(value).digest("hex");
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const digest = value => sha256(JSON.stringify(canonical(value)));
const id = value => typeof value === "string" && /^[A-Za-z0-9_-]{6,160}$/.test(value);
const percent = row => row?.percent === undefined ? 0 : Number.isInteger(row.percent) && row.percent >= 0 && row.percent <= 100 ? row.percent : NaN;
const origin = value => { try { const url = new URL(value); return url.protocol === "https:" && !url.username && !url.password && !url.hash ? url.href : ""; } catch { return ""; } };
const workerEnvKeys = ["SCAN_WORKSPACE_BUCKET", "SCAN_TASKS_PROJECT", "SCAN_TASKS_LOCATION", "SCAN_STAGE_QUEUE", "SCAN_STAGE_TASKS_QUEUE_PATH", "SCAN_STAGE_TARGET_URL", "SCAN_STAGE_TOKEN_AUDIENCE", "SCAN_PIPELINE_MODE", "SCAN_STAGED_OWNER_IDS"];

export function validatePrerequisites(packet, expected) {
  const failures = [], add = (condition, code) => { if (!condition) failures.push(code); };
  const now = expected.now ?? Date.now();
  const fresh = (record, code, inheritExpiry = false) => {
    const observed = Date.parse(record?.observed_at), expires = Date.parse(record?.expires_at ?? (inheritExpiry ? packet?.expires_at : ""));
    add(Number.isFinite(observed) && Number.isFinite(expires) && observed <= now + 30000 && observed <= expires && now - observed <= 900000 && expires > now && expires - observed <= 900000, code);
  };
  add(packet?.schema_version === "staged_scan_acceptance_prerequisites_v1", "prerequisite_schema_missing");
  fresh(packet, "prerequisites_stale");
  add(/^[a-f0-9]{40}$/.test(expected.sourceSha) && packet?.source_sha === expected.sourceSha, "prerequisite_source_mismatch");
  add(/^[a-f0-9]{16}$/.test(expected.fingerprint) && packet?.release_fingerprint === expected.fingerprint, "prerequisite_fingerprint_mismatch");
  const base44 = packet?.base44;
  fresh(base44, "base44_runtime_stale", true);
  add(base44?.schema_version === "fixlist_staged_v9_readiness_v1" && base44?.source_sha === expected.sourceSha && base44?.app_id === APP_ID && base44?.candidate_fingerprint === expected.fingerprint, "base44_readiness_identity_mismatch");
  const functions = Array.isArray(base44?.functions) ? base44.functions : [];
  add(functions.length === STAGED_RELEASE_FUNCTIONS.length && new Set(functions.map(row => row?.name)).size === functions.length, "base44_function_inventory_mismatch");
  for (const name of STAGED_RELEASE_FUNCTIONS) {
    const actual = functions.find(row => row?.name === name), local = expected.functions?.[name];
    add(Boolean(local) && actual?.build_id === local.build_id && actual?.package_digest === local.package_digest && actual?.runtime_activation_id === local.runtime_activation_id && actual?.http_status === 405, `base44_package_mismatch:${name}`);
  }
  fresh(packet?.schema_readback, "schema_readback_missing_or_stale");
  add(packet?.schema_readback?.source_sha === expected.sourceSha && packet?.schema_readback?.app_id === APP_ID, "schema_readback_identity_mismatch");
  for (const name of STAGED_RELEASE_ENTITIES) {
    let matches = false;
    try {
      const parse = source => JSON.parse(source.replace(/^\s*\/\/.*$/gm, ""));
      const local = parse(expected.entitySources[name]), observed = parse(packet.schema_readback.entity_sources[name]);
      // Use the same schema contract as the migration verifier. Raw JSON
      // formatting, server annotations and documented metadata omissions must
      // not be mistaken for deployment drift; RLS and fields still compare.
      matches = local.name === name && observed.name === name && diffEntity(name, local, observed).status === "match";
    } catch { /* Missing or malformed raw schema observations fail closed. */ }
    add(matches, `schema_readback_mismatch:${name}`);
  }
  fresh(packet?.base44_configuration, "base44_configuration_missing_or_stale");
  add(packet?.base44_configuration?.source_sha === expected.sourceSha, "base44_configuration_source_mismatch");
  const environments = {};
  for (const component of ["worker", "gateway"]) {
    const observation = packet?.[component], revision = observation?.revision;
    fresh(observation, `${component}_observation_missing_or_stale`);
    const rows = revision?.spec?.containers?.[0]?.env || [];
    const env = Object.fromEntries(rows.filter(row => typeof row?.value === "string").map(row => [row.name, row.value]));
    environments[component] = env;
    add(typeof revision?.metadata?.name === "string" && revision.metadata.name.startsWith(component === "worker" ? "fixlist-standard150-worker-" : "fixlist-dispatch-gateway-"), `${component}_revision_missing`);
    add(revision?.status?.conditions?.some(row => row.type === "Ready" && row.status === "True") && /@sha256:[a-f0-9]{64}$/.test(revision?.status?.imageDigest || ""), `${component}_revision_not_ready`);
    add(env[component === "worker" ? "FIXLIST_WORKER_SOURCE_SHA" : "FIXLIST_GATEWAY_SOURCE_SHA"] === expected.sourceSha && observation?.runtime?.source_sha === expected.sourceSha, `${component}_source_mismatch`);
  }
  const worker = packet?.worker, gateway = packet?.gateway, workerEnv = environments.worker || {}, gatewayEnv = environments.gateway || {};
  const ownerIds = String(workerEnv.SCAN_STAGED_OWNER_IDS || "").split(",").filter(Boolean).sort();
  const cohort = sha256(JSON.stringify(ownerIds));
  add(ownerIds.length >= 1 && ownerIds.length <= 5 && new Set(ownerIds).size === ownerIds.length && ownerIds.every(id) && ownerIds.includes(expected.ownerId) && workerEnv.SCAN_PIPELINE_MODE === "staged", "worker_cohort_mismatch");
  add(gatewayEnv.SCAN_PIPELINE_MODE === "staged" && JSON.stringify(String(gatewayEnv.SCAN_STAGED_OWNER_IDS || "").split(",").filter(Boolean).sort()) === JSON.stringify(ownerIds), "gateway_cohort_mismatch");
  for (const name of STAGED_RELEASE_FUNCTIONS) {
    const observed = packet?.base44_configuration?.function_environments?.[name];
    add(observed?.SCAN_PIPELINE_MODE === "staged" && JSON.stringify(String(observed?.SCAN_STAGED_OWNER_IDS || "").split(",").filter(Boolean).sort()) === JSON.stringify(ownerIds), `base44_cohort_mismatch:${name}`);
  }
  const config = Object.fromEntries(workerEnvKeys.map(key => [key, workerEnv[key]]));
  const configDigest = digest({ source_sha: expected.sourceSha, environment: config });
  add(workerEnvKeys.every(key => typeof workerEnv[key] === "string" && workerEnv[key]) && workerEnv.FIXLIST_STAGED_CONFIG_SHA256 === configDigest, "worker_configuration_digest_mismatch");
  const traffic = worker?.service?.status?.traffic || [];
  add(Boolean(origin(worker?.probe_url)) && traffic.every(row => Number.isFinite(percent(row))) && traffic.some(row => row.revisionName === worker?.revision?.metadata?.name && row.url === worker?.probe_url && percent(row) === 0) && !traffic.some(row => row.revisionName === worker?.revision?.metadata?.name && percent(row) !== 0), "worker_tag_mapping_mismatch");
  add(traffic.some(row => row.revisionName === worker?.revision?.metadata?.name && row.url === workerEnv.SCAN_STAGE_TARGET_URL), "stage_target_mapping_mismatch");
  add(workerEnv.SCAN_STAGE_TOKEN_AUDIENCE === worker?.service?.status?.url && Boolean(origin(worker?.service?.status?.url)) && workerEnv.SCAN_STAGE_TASKS_QUEUE_PATH === `projects/${workerEnv.SCAN_TASKS_PROJECT}/locations/${workerEnv.SCAN_TASKS_LOCATION}/queues/${workerEnv.SCAN_STAGE_QUEUE}`, "worker_stage_resource_identity_mismatch");
  add((worker?.runtime?.fingerprint || worker?.runtime?.beta_revision_fingerprint) === expected.fingerprint, "worker_fingerprint_mismatch");
  const health = gateway?.runtime || {};
  add(health.ok === true && health.revision === gateway?.revision?.metadata?.name && health.pipeline_mode === "staged" && health.staged_owner_count === ownerIds.length && health.staged_owner_cohort_sha256 === cohort, "gateway_runtime_identity_mismatch");
  const gatewayTraffic = gateway?.service?.status?.traffic || [];
  add(gatewayTraffic.every(row => Number.isFinite(percent(row))) && gatewayTraffic.reduce((total, row) => total + percent(row), 0) === 100 && gatewayTraffic.filter(row => row.revisionName === health.revision).reduce((total, row) => total + percent(row), 0) === 100, "gateway_serving_revision_mismatch");
  add(health.canary_worker_origin === worker?.probe_url && health.canary_owner_count === ownerIds.length && gatewayEnv.SCAN_CANARY_WORKER_ORIGIN === worker?.probe_url && JSON.stringify(String(gatewayEnv.SCAN_CANARY_OWNER_USER_IDS || "").split(",").filter(Boolean).sort()) === JSON.stringify(ownerIds), "gateway_canary_route_mismatch");
  const infra = packet?.infrastructure, stageQueue = infra?.queue, bucket = infra?.bucket;
  fresh(infra, "infrastructure_missing_or_stale");
  add(stageQueue?.name === workerEnv.SCAN_STAGE_TASKS_QUEUE_PATH && stageQueue?.state === "RUNNING" && stageQueue?.rateLimits?.maxConcurrentDispatches === 40 && stageQueue?.retryConfig?.maxAttempts === 10 && stageQueue?.retryConfig?.minBackoff === "10s" && stageQueue?.retryConfig?.maxBackoff === "120s" && stageQueue?.retryConfig?.maxDoublings === 4 && stageQueue?.retryConfig?.maxRetryDuration === "1800s" && !stageQueue?.httpTarget, "stage_queue_contract_mismatch");
  const bucketUniform = bucket?.uniform_bucket_level_access ?? bucket?.iamConfiguration?.uniformBucketLevelAccess?.enabled;
  const bucketPublic = bucket?.public_access_prevention ?? bucket?.iamConfiguration?.publicAccessPrevention;
  const bucketRules = bucket?.lifecycle_config?.rule ?? bucket?.lifecycle?.rule;
  add(bucket?.name === workerEnv.SCAN_WORKSPACE_BUCKET && bucketUniform === true && bucketPublic === "enforced" && Array.isArray(bucketRules) && bucketRules.some(row => row?.action?.type === "Delete" && Object.keys(row.action).length === 1 && row?.condition?.age === 30 && Object.keys(row.condition).length === 1), "workspace_bucket_contract_mismatch");
  const workerSa = worker?.revision?.spec?.serviceAccountName;
  for (const [policy, role] of [[infra?.bucket_policy, "roles/storage.objectUser"], [infra?.queue_policy, "roles/cloudtasks.enqueuer"], [infra?.invoker_policy, "roles/iam.serviceAccountUser"]]) {
    add(typeof workerSa === "string" && policy?.bindings?.some(row => row.role === role && !row.condition && row.members?.includes(`serviceAccount:${workerSa}`)) && !policy?.bindings?.some(row => row.members?.some(member => ["allUsers", "allAuthenticatedUsers"].includes(member))), `infrastructure_iam_mismatch:${role}`);
  }
  const request = infra?.task?.httpRequest;
  add(infra?.task?.dispatchDeadline === "480s" && request?.httpMethod === "POST" && ["/scan-batch", "/scan-finalize"].some(suffix => request?.url === workerEnv.SCAN_STAGE_TARGET_URL + suffix) && request?.oidcToken?.serviceAccountEmail === infra?.invoker_service_account && request?.oidcToken?.audience === workerEnv.SCAN_STAGE_TOKEN_AUDIENCE, "stage_task_contract_mismatch");
  return { ready: failures.length === 0, failures: [...new Set(failures)], missing_producers: MISSING_PRODUCERS, provenance: failures.length ? null : {
    source_sha: expected.sourceSha, release_fingerprint: expected.fingerprint, observed_at: packet.observed_at, expires_at: packet.expires_at,
    worker_revision: worker.revision.metadata.name, gateway_revision: gateway.revision.metadata.name,
    worker_config_sha256: configDigest, staged_owner_cohort_sha256: cohort,
    base44_functions: functions.map(({ name, build_id, package_digest, runtime_activation_id }) => ({ name, build_id, package_digest, runtime_activation_id })),
    schema_readback_sha256: digest(packet.schema_readback.entity_sources), infrastructure_sha256: digest(infra), prerequisite_sha256: digest(packet),
  } };
}

// This function must remain self-contained: it also runs inside Base44 exec.
export async function executeStaged500Canary(base44, config, now = Date.now, sleep = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  const report = { schema_version: "staged_500_canary_v1", production_freeze: false, source_sha: config.sourceSha,
    expected_owner_user_id: config.ownerId, project_id: config.projectId, target_url: config.targetUrl, request_id: config.requestId,
    release_fingerprint: null, provenance: config.provenance, observed_at: new Date(now()).toISOString(), scan_id: null,
    terminal_outcome_verified: false, functional_500_verified: false, full_500_gate: false, acceptance_verified: false,
    outcome: "unverified", progress: [], payload_bytes: { customer_projection: null, completion_request: null },
    memory: { finalize_peak_bytes: null, scope: "finalize_only", all_stages_verified: false }, unverified: ["completion_request_byte_measurement", "all_stage_memory_measurement", "per_scan_runtime_revision_receipt"], failure_code: null };
  const deadline = now() + config.maxWait * 1000;
  class CanaryCheckError extends Error {}
  const require = (value, code) => { if (!value) throw new CanaryCheckError(code); };
  const unwrap = value => value?.data && typeof value.data === "object" ? value.data : value;
  const integer = value => Number.isInteger(value) && value >= 0;
  const url = value => { try { return new URL(String(value)).href; } catch { return ""; } };
  async function bounded(operation) {
    const remaining = Math.min(30000, deadline - now()); require(remaining > 0, "scan_timeout");
    let timer; try { return await Promise.race([Promise.resolve().then(operation), new Promise((_, reject) => { timer = setTimeout(() => reject(new CanaryCheckError("operation_timeout")), remaining); })]); } finally { clearTimeout(timer); }
  }
  try {
    require(config.appId === "6a498732ec779dfaaeab0e53" && config.provenance?.source_sha === config.sourceSha && config.provenance?.release_fingerprint === config.expectedFingerprint && Date.parse(config.provenance?.expires_at) > now(), "prerequisites_invalid_or_expired");
    const me = await bounded(() => base44.auth.me());
    require(me?.id === config.ownerId && me.role === "admin", "authenticated_owner_not_admin");
    const email = String(me.email || "").trim().toLowerCase(); require(email, "owner_email_missing");
    const project = await bounded(() => base44.entities.BusinessProject.get(config.projectId));
    require(project?.id === config.projectId && project.owner_user_id === config.ownerId && url(project.website_url) === config.targetUrl, "project_identity_mismatch");
    const byOwner = await bounded(() => base44.entities.Access.filter({ owner_user_id: config.ownerId }));
    const byEmail = await bounded(() => base44.entities.Access.filter({ user_email: email }));
    require(Array.isArray(byOwner) && Array.isArray(byEmail), "access_records_unavailable");
    const grants = [...new Map([...byOwner, ...byEmail].filter(row => row?.id).map(row => [String(row.id), row])).values()];
    require(grants.length === 1, "access_record_not_unique");
    const grant = grants[0];
    require(grant.owner_user_id === config.ownerId && String(grant.user_email || "").trim().toLowerCase() === email && grant.app_id === config.appId && grant.has_full_access === true && grant.access_status === "active" && grant.plan_id === "standard150_lifetime" && grant.page_cap === 500, "existing_entitlement_not_500");
    const dated = Number.isFinite(Date.parse(grant.granted_at || ""));
    require((grant.grant_source === "manual_grant" && dated) || (grant.grant_source === "stripe_checkout" && Boolean(grant.stripe_checkout_session_id) && Number.isFinite(Date.parse(grant.paid_at || ""))) || (grant.grant_source === "owner_test" && dated && me.id === "6a498da58ef5cec1f5cd4486" && email === "bright4862@gmail.com"), "access_grant_unverified");
    const accepted = unwrap(await bounded(() => base44.functions.invoke("startStandardScanJobV9", { request_id: config.requestId, idempotency_key: config.requestId, project_id: config.projectId, website_url: config.targetUrl, submitted_url: config.targetUrl, scan_mode: "standard_500", source: "staged_500_acceptance" })));
    require(accepted?.success === true && accepted.accepted === true && accepted.scan_mode === "standard_500" && accepted.page_cap === 500 && accepted.pipeline_mode === "staged", "scan_not_accepted_as_staged_500");
    report.scan_id = String(accepted.scan_id || accepted.scan_run_id || ""); require(/^[A-Za-z0-9_-]{6,160}$/.test(report.scan_id), "scan_id_missing");
    let run, projection;
    while (now() < deadline) {
      projection = unwrap(await bounded(() => base44.functions.invoke("getCustomerScanResultV9", { scan_id: report.scan_id })));
      run = await bounded(() => base44.entities.ScanRun.get(report.scan_id));
      require(projection?.success === true && projection.scan_id === report.scan_id && run?.id === report.scan_id && run.owner_user_id === config.ownerId && run.project_id === config.projectId && run.request_id === config.requestId && (run.idempotency_key || run.request_id) === config.requestId && url(run.website_url) === config.targetUrl, "scan_identity_mismatch");
      require(run.page_cap === 500 && run.scan_mode === "standard_500" && run.pipeline_mode === "staged", "scan_contract_mismatch");
      const pending = ["queued", "crawling", "reviewing"].includes(run.status);
      // The admission row has no progress counters yet. A plan can retain its
      // first page before any batch is committed. Unknown progress is allowed
      // only while pending and must never become terminal evidence.
      const crawled = pending && run.pages_crawled == null ? 0 : run.pages_crawled;
      const planned = pending && run.pages_planned == null ? 0 : run.pages_planned;
      const batch = pending && run.last_committed_batch == null ? null : run.last_committed_batch;
      require(integer(crawled) && integer(planned) && crawled <= planned && planned <= 500 && ((pending && batch === null) || (integer(batch) && batch <= 10000)), "scan_progress_invalid");
      const sample = { status: String(run.status), pages_crawled: crawled, pages_planned: planned, last_committed_batch: batch };
      const previous = report.progress.at(-1);
      require(!previous || (sample.pages_crawled >= previous.pages_crawled && sample.pages_planned >= previous.pages_planned && (sample.last_committed_batch ?? -1) >= (previous.last_committed_batch ?? -1)), "scan_progress_regressed");
      if (!previous || JSON.stringify(previous) !== JSON.stringify(sample)) report.progress.push(sample);
      if (["complete", "limited", "failed", "cancelled"].includes(run.status) && projection.run?.status === run.status) break;
      await sleep(Math.min(config.pollSeconds * 1000, Math.max(1, deadline - now())));
    }
    require(["complete", "limited", "failed", "cancelled"].includes(run?.status) && projection.run?.status === run.status, now() >= deadline ? "scan_timeout" : "scan_not_successfully_terminal");
    require(["complete", "limited"].includes(run?.status), "scan_not_successfully_terminal");
    report.terminal_status = run.status; report.page_cap = run.page_cap; report.pages_crawled = run.pages_crawled;
    report.pages_planned = run.pages_planned; report.committed_batch_count = run.last_committed_batch + 1;
    require(report.committed_batch_count > 0 && run.pages_crawled > 0 && run.pages_crawled <= report.committed_batch_count * 50, "committed_evidence_missing");
    require(projection.release_contract_current === true && projection.run.beta_revision_fingerprint === config.expectedFingerprint && run.beta_revision_fingerprint === config.expectedFingerprint, "release_fingerprint_mismatch");
    report.release_fingerprint = projection.run.beta_revision_fingerprint;
    require(projection.run.advanced_scan_backend === "python_scanner_api" && projection.run.deno_fallback_used === false && projection.run.ai_review_backend === "python_review_api" && projection.run.python_review_fallback_used === false, "durable_worker_evidence_missing");
    report.payload_bytes.customer_projection = new TextEncoder().encode(JSON.stringify(projection)).byteLength;
    const memory = projection.run.worker_peak_memory_bytes ?? projection.run.peak_memory_bytes;
    report.memory.finalize_peak_bytes = typeof memory === "number" && Number.isFinite(memory) && memory > 0 ? memory : null;
    report.duration_ms = Date.parse(run.completed_at || "") - Date.parse(run.started_at || "");
    require(Number.isFinite(report.duration_ms) && report.duration_ms > 0 && report.duration_ms <= 1800000, "duration_unverified");
    if (run.status === "complete") {
      require(projection.authority_verified === true && /^[a-f0-9]{64}$/.test(run.authority_proof || "") && Boolean(run.authority_seal_version), "complete_authority_unverified");
      // Slow batches may end at the stage work fuse before retaining 50 pages.
      // Such a terminal result is valid, but does not prove the ten-batch case.
      require(run.pages_crawled === run.pages_planned && report.committed_batch_count >= Math.ceil(run.pages_crawled / 50), "completed_batch_count_mismatch");
      report.outcome = "complete";
      report.functional_500_verified = run.pages_crawled === 500 && report.committed_batch_count === 10;
    } else {
      require(projection.result_integrity_verified === true && /^[a-f0-9]{64}$/.test(run.result_integrity_proof || "") && Boolean(run.result_integrity_version), "limited_integrity_unverified");
      require(projection.authority_verified !== true && projection.run.score_is_provisional === true && projection.run.release_gate_eligible === false && ["limited_coverage", "access_limited", "inventory_unproven"].includes(projection.run.coverage_state) && Boolean(projection.run.limitation) && Array.isArray(projection.fixItems) && projection.fixItems.length > 0, "limited_coverage_untruthful");
      const fixIds = new Set(projection.fixItems.map(fix => String(fix?.fix_id || fix?.issue_id || fix?.id || "")).filter(Boolean));
      require(Array.isArray(projection.top_fix_ids) && projection.top_fix_ids.length >= 1 && projection.top_fix_ids.length <= 3 && new Set(projection.top_fix_ids).size === projection.top_fix_ids.length && projection.top_fix_ids.every(id => typeof id === "string" && fixIds.has(id)), "limited_priorities_missing_or_invalid");
      const reasons = Array.isArray(projection.run.coverage_reasons) ? projection.run.coverage_reasons : [];
      const throttled = reasons.some(reason => ["rate_limit", "rate_limited", "throttled", "staged_rate_limit"].includes(reason));
      const budget = reasons.includes("staged_wall_budget");
      require(throttled || budget || reasons.includes("staged_partial_evidence"), "limited_termination_reason_missing");
      report.termination_reasons = reasons.filter(reason => ["rate_limit", "rate_limited", "throttled", "staged_rate_limit", "staged_wall_budget", "staged_partial_evidence"].includes(reason));
      report.outcome = throttled ? "limited_throttled" : budget ? "limited_budget" : "limited_partial";
    }
    report.durable_worker_owned = true; report.terminal_outcome_verified = true;
    if (!report.memory.finalize_peak_bytes) report.unverified.push("finalize_memory_measurement");
    // These producers do not exist yet. A finalize metric or response size must
    // never be relabelled as all-stage memory or completion request evidence.
  } catch (error) {
    // SDK errors may contain credentials or private evidence even when their
    // text looks like a lowercase error code. Only our own checks are public.
    report.failure_code = error instanceof CanaryCheckError ? error.message : "remote_operation_failed";
    report.unverified.push(report.failure_code);
  }
  return report;
}

export function renderRemoteCanary(config) {
  return `const config = ${JSON.stringify(config)};\nconsole.log('FIXLIST_STAGED_500_CANARY=' + JSON.stringify(await (${executeStaged500Canary.toString()})(base44, config)));\n`;
}

export function localAcceptanceIdentity(root, sourceSha, ownerId) {
  const manifest = buildManifest(STAGED_RELEASE_FUNCTIONS, path.join(root, "base44/functions"), STAGED_RELEASE_ENTITIES, path.join(root, "base44/entities"));
  const functions = {};
  for (const name of STAGED_RELEASE_FUNCTIONS) {
    const directory = path.join(root, "base44/functions", name), identity = createHash("sha256");
    for (const file of fs.readdirSync(directory).sort().filter(file => file !== "generatedBuildId.js" && fs.statSync(path.join(directory, file)).isFile())) identity.update(file).update("\0").update(fs.readFileSync(path.join(directory, file))).update("\0");
    const entry = fs.readFileSync(path.join(directory, manifest.functions[name].entry), "utf8");
    functions[name] = { build_id: identity.digest("hex"), package_digest: manifest.functions[name].packageDigest, runtime_activation_id: entry.match(/BASE44_RUNTIME_ACTIVATION_ID\s*=\s*"([^"]+)"/)?.[1] };
  }
  return { sourceSha, ownerId, fingerprint: JSON.parse(fs.readFileSync(path.join(root, "data/beta-crawler-revision.json"), "utf8")).fingerprint, functions, entitySources: Object.fromEntries(STAGED_RELEASE_ENTITIES.map(name => [name, fs.readFileSync(path.join(root, "base44/entities", `${name}.jsonc`), "utf8")])) };
}

export function writeNewArtifact(output, value, root) {
  if (!path.isAbsolute(output) || !fs.existsSync(path.dirname(output)) || fs.realpathSync(path.dirname(output)) !== path.dirname(output)) throw new Error("artifact_path_invalid");
  const relative = path.relative(fs.realpathSync(root), path.dirname(output));
  if (!relative || (!relative.startsWith(`..${path.sep}`) && relative !== "..")) throw new Error("artifact_must_be_outside_checkout");
  fs.writeFileSync(output, JSON.stringify(value, null, 2) + "\n", { flag: "wx", mode: 0o600 });
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  try {
    const mode = process.argv[2];
    if (mode === "describe-prerequisites") console.log(JSON.stringify({ schema_version: "staged_scan_acceptance_prerequisites_v1", missing_producers: MISSING_PRODUCERS, required_observations: ["base44", "schema_readback", "base44_configuration", "worker", "gateway", "infrastructure"], freshness_seconds: 900 }, null, 2));
    else if (mode === "render") {
      const env = process.env, root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
      const expected = localAcceptanceIdentity(root, env.SOURCE_SHA, env.EXPECTED_OWNER_USER_ID);
      const packet = JSON.parse(fs.readFileSync(env.PREREQUISITES_FILE, "utf8"));
      const validation = validatePrerequisites(packet, expected);
      if (!validation.ready) throw new Error(validation.failures.join(","));
      if (!id(env.EXPECTED_OWNER_USER_ID) || !id(env.PROJECT_ID) || !id(env.REQUEST_ID) || !origin(env.TARGET_URL)) throw new Error("scan_input_invalid");
      const maxWait = Number(env.MAX_WAIT_SECONDS || 900), pollSeconds = Number(env.POLL_SECONDS || 5);
      if (!Number.isInteger(maxWait) || maxWait < 1 || maxWait > 1800 || !Number.isInteger(pollSeconds) || pollSeconds < 1 || pollSeconds > 60) throw new Error("scan_timeout_invalid");
      process.stdout.write(renderRemoteCanary({ appId: APP_ID, sourceSha: env.SOURCE_SHA, ownerId: env.EXPECTED_OWNER_USER_ID, projectId: env.PROJECT_ID, requestId: env.REQUEST_ID, targetUrl: origin(env.TARGET_URL), expectedFingerprint: expected.fingerprint, maxWait, pollSeconds, provenance: validation.provenance }));
    } else if (mode === "collect") {
      const [input, output, cliStatus] = process.argv.slice(3), prefix = "FIXLIST_STAGED_500_CANARY=";
      const lines = fs.readFileSync(input, "utf8").split("\n").filter(line => line.startsWith(prefix));
      if (lines.length !== 1) throw new Error("cli_report_missing_or_ambiguous");
      const report = JSON.parse(lines[0].slice(prefix.length)), env = process.env;
      if (report.schema_version !== "staged_500_canary_v1" || report.source_sha !== env.SOURCE_SHA || report.expected_owner_user_id !== env.EXPECTED_OWNER_USER_ID || report.project_id !== env.PROJECT_ID || report.request_id !== env.REQUEST_ID || report.target_url !== origin(env.TARGET_URL)) throw new Error("cli_report_identity_mismatch");
      if (Number(cliStatus) !== 0) { report.terminal_outcome_verified = false; report.failure_code = "cli_execution_failed"; }
      writeNewArtifact(output, report, path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."));
      console.log(`STAGED_500_REPORT_SAVED outcome=${report.outcome} acceptance_verified=${report.acceptance_verified === true}`);
      if (!report.terminal_outcome_verified) process.exitCode = 1;
    } else throw new Error("Use render, collect, or describe-prerequisites");
  } catch (error) { console.error(`STAGED_500_ACCEPTANCE_BLOCKED: ${error.message}`); process.exitCode = 2; }
}
