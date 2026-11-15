#!/usr/bin/env node
// Offline validation and a self-contained Base44 exec payload. No collector in
// this module deploys, changes a grant/cohort, or calls a cloud API.
//
// Prerequisite packet v1 contains fresh raw observations, not verified:true:
// base44 = exact versioned publication's fixlist_staged_v9_readiness_v2 report;
// schema_readback.entity_sources = exact pulled .jsonc file contents;
// base44_configuration.intake_route = authenticated V9 intake configuration;
// worker/gateway = Cloud Run revision+service exports and bound runtime probes;
// worker.base44_runtime = authenticated worker readback of signed V9 POST receipts;
// infrastructure = fresh bucket/queue/IAM plus a source-bound task observation.
// Every observation has observed_at/expires_at, within a 15 minute window.
// Assembly validates independent live observations and preserves their capture times.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { STAGED_RELEASE_FUNCTIONS, STAGED_RELEASE_ENTITIES } from "./base44_release_manifest.mjs";
import { diffEntity } from "./base44_authority_schema.mjs";

export const APP_ID = "6a498732ec779dfaaeab0e53";
const REQUIRED_OBSERVATIONS = ["base44", "schema_readback", "base44_configuration", "worker", "worker_base44_runtime", "gateway", "infrastructure", "stage_task"];
const WORKER_V9_FUNCTIONS = ["durableScanWorkerControlV9", "persistDurableScanAuthorityV9", "persistLimitedScanResultV9"];
const sha256 = value => createHash("sha256").update(value).digest("hex");
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const digest = value => sha256(JSON.stringify(canonical(value)));
const id = value => typeof value === "string" && /^[A-Za-z0-9_-]{6,160}$/.test(value);
const percent = row => row?.percent === undefined ? 0 : Number.isInteger(row.percent) && row.percent >= 0 && row.percent <= 100 ? row.percent : NaN;
const origin = value => { try { const url = new URL(value); return url.protocol === "https:" && !url.username && !url.password && !url.hash ? url.href : ""; } catch { return ""; } };
const ownerIdPattern = /^[A-Za-z0-9_-]{6,64}$/;
const workerProject = "seo-autopilot-501517";
const workerRegion = "europe-west1";
const stageQueueName = "fixlist-scan-stages";
const invokerAccount = `fixlist-standard150-invoker@${workerProject}.iam.gserviceaccount.com`;
const workerAccount = `fixlist-standard150-worker@${workerProject}.iam.gserviceaccount.com`;
const taskSampleLifetimeMs = 24 * 3600 * 1000;

function reviewedWorkerEnvironment(sourceSha, workerOrigin) {
  if (typeof workerOrigin !== "string" || !/^https:\/\/[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.run\.app$/.test(workerOrigin) || workerOrigin.includes("---")) return null;
  const target = `https://staged-${sourceSha.slice(0, 12)}---${workerOrigin.slice("https://".length)}`;
  if (new URL(target).hostname.split(".").some(label => !label || label.length > 63)) return null;
  return {
    SCAN_WORKSPACE_BUCKET: `fixlist-scan-workspaces-${workerProject}`,
    SCAN_TASKS_PROJECT: workerProject,
    SCAN_TASKS_LOCATION: workerRegion,
    SCAN_STAGE_QUEUE: stageQueueName,
    SCAN_STAGE_TASKS_QUEUE_PATH: `projects/${workerProject}/locations/${workerRegion}/queues/${stageQueueName}`,
    SCAN_STAGE_TARGET_URL: target,
    SCAN_STAGE_TOKEN_AUDIENCE: workerOrigin,
    SCAN_PIPELINE_MODE: "monolith",
    SCAN_STAGED_OWNER_IDS: "",
  };
}

function matchesWorkerBase44Runtime(worker, expected) {
  if (!worker?.base44_runtime || !WORKER_V9_FUNCTIONS.every(name => expected.functions?.[name])) return false;
  const observation = {
    source_sha: expected.sourceSha,
    worker_revision: worker.revision?.metadata?.name,
    transport: "worker_signed_post",
    base44_app_id: APP_ID,
    base44_origin: "https://base44.app",
    release_fingerprint: expected.fingerprint,
    functions: WORKER_V9_FUNCTIONS.map(name => ({
      protocol: "fixlist_worker_runtime_v1",
      function_name: name,
      route_name: expected.functions[name].route_name,
      action: "identity",
      http_status: 200,
      release_fingerprint: expected.fingerprint,
      build_id: expected.functions[name].build_id,
      runtime_activation_id: expected.functions[name].runtime_activation_id,
    })),
  };
  return JSON.stringify(canonical(worker.base44_runtime)) === JSON.stringify(canonical(observation));
}

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
  add(base44?.schema_version === "fixlist_staged_v9_readiness_v2" && base44?.source_sha === expected.sourceSha
    && base44?.app_id === APP_ID && base44?.candidate_fingerprint === expected.fingerprint
    && base44?.runtime_probe_transport === "base44_native_authenticated_sdk_get"
    && base44?.anonymous_probe?.transport === "base44_legacy_anonymous_get", "base44_readiness_identity_mismatch");
  const functions = Array.isArray(base44?.functions) ? base44.functions : [];
  const external = Array.isArray(base44?.anonymous_probe?.functions) ? base44.anonymous_probe.functions : [];
  add(functions.length === STAGED_RELEASE_FUNCTIONS.length && new Set(functions.map(row => row?.name)).size === functions.length, "base44_function_inventory_mismatch");
  add(external.length === STAGED_RELEASE_FUNCTIONS.length && new Set(external.map(row => row?.name)).size === external.length, "base44_external_inventory_mismatch");
  for (const name of STAGED_RELEASE_FUNCTIONS) {
    const actual = functions.find(row => row?.name === name), local = expected.functions?.[name];
    const direct = external.find(row => row?.name === name);
    add(Boolean(local) && actual?.route_name === local.route_name && actual?.build_id === local.build_id
      && actual?.package_digest === local.package_digest && actual?.runtime_activation_id === local.runtime_activation_id
      && actual?.http_status === 405, `base44_package_mismatch:${name}`);
    add(Boolean(local) && direct?.route_name === local.route_name && direct?.state === "matched"
      && direct?.build_id === local.build_id && direct?.runtime_activation_id === local.runtime_activation_id
      && direct?.http_status === 405, `base44_external_runtime_mismatch:${name}`);
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
  const owner = expected.ownerId;
  const cohort = sha256(JSON.stringify([owner]));
  add(typeof owner === "string" && ownerIdPattern.test(owner) && workerEnv.SCAN_STAGED_OWNER_IDS === owner
    && workerEnv.SCAN_PIPELINE_MODE === "staged" && !workerEnv.SCAN_PIPELINE_OWNER_IDS, "worker_cohort_mismatch");
  add(gatewayEnv.SCAN_PIPELINE_MODE === "staged" && gatewayEnv.SCAN_STAGED_OWNER_IDS === owner, "gateway_cohort_mismatch");
  const intake = packet?.base44_configuration?.intake_route;
  const intakeIdentity = expected.functions?.startStandardScanJobV9;
  fresh(intake, "base44_intake_runtime_stale", true);
  add(intake?.schema_version === "fixlist_staged_v9_intake_readback_v1" && intake.success === true
    && Boolean(intakeIdentity) && intake.build_id === intakeIdentity.build_id
    && intake.runtime_activation_id === intakeIdentity.runtime_activation_id
    && intake.release_fingerprint === expected.fingerprint, "base44_intake_identity_mismatch");
  add(intake?.configured_pipeline_mode === "staged" && intake?.pipeline_mode === "staged"
    && intake?.staged_owner_cohort_state === "explicit" && intake?.staged_owner_count === 1
    && intake?.staged_owner_cohort_sha256 === cohort && intake?.staged_owner_enabled === true
    && intake?.intake_gate === "enabled" && intake?.admission_gate === "enabled", "base44_intake_cohort_mismatch");
  // The worker stamp binds the reviewed inactive environment. Only mode and
  // cohort may differ on the active revision, and both were checked above.
  const reviewed = /^[a-f0-9]{40}$/.test(expected.sourceSha) ? reviewedWorkerEnvironment(expected.sourceSha, worker?.service?.status?.url) : null;
  const configDigest = reviewed ? digest({ source_sha: expected.sourceSha, environment: reviewed }) : null;
  add(Boolean(configDigest) && workerEnv.FIXLIST_STAGED_CONFIG_SHA256 === configDigest, "worker_configuration_digest_mismatch");
  add(Boolean(reviewed) && Object.entries(reviewed).every(([key, value]) =>
    key === "SCAN_PIPELINE_MODE" || key === "SCAN_STAGED_OWNER_IDS" || workerEnv[key] === value), "worker_configuration_drift");
  const traffic = worker?.service?.status?.traffic || [];
  add(Boolean(origin(worker?.probe_url)) && traffic.every(row => Number.isFinite(percent(row))) && traffic.some(row => row.revisionName === worker?.revision?.metadata?.name && row.url === worker?.probe_url && percent(row) === 0) && !traffic.some(row => row.revisionName === worker?.revision?.metadata?.name && percent(row) !== 0), "worker_tag_mapping_mismatch");
  add(traffic.some(row => row.revisionName === worker?.revision?.metadata?.name
    && row.tag === `staged-${expected.sourceSha?.slice(0, 12)}` && row.url === workerEnv.SCAN_STAGE_TARGET_URL), "stage_target_mapping_mismatch");
  add(workerEnv.SCAN_STAGE_TOKEN_AUDIENCE === worker?.service?.status?.url && Boolean(origin(worker?.service?.status?.url)) && workerEnv.SCAN_STAGE_TASKS_QUEUE_PATH === `projects/${workerEnv.SCAN_TASKS_PROJECT}/locations/${workerEnv.SCAN_TASKS_LOCATION}/queues/${workerEnv.SCAN_STAGE_QUEUE}`, "worker_stage_resource_identity_mismatch");
  add((worker?.runtime?.fingerprint || worker?.runtime?.beta_revision_fingerprint) === expected.fingerprint, "worker_fingerprint_mismatch");
  add(matchesWorkerBase44Runtime(worker, expected), "worker_base44_runtime_mismatch");
  const health = gateway?.runtime || {};
  add(health.ok === true && health.revision === gateway?.revision?.metadata?.name && health.pipeline_mode === "staged" && health.staged_owner_count === 1 && health.staged_owner_cohort_sha256 === cohort, "gateway_runtime_identity_mismatch");
  const gatewayTraffic = gateway?.service?.status?.traffic || [];
  add(gatewayTraffic.every(row => Number.isFinite(percent(row))) && gatewayTraffic.reduce((total, row) => total + percent(row), 0) === 100 && gatewayTraffic.filter(row => row.revisionName === health.revision).reduce((total, row) => total + percent(row), 0) === 100, "gateway_serving_revision_mismatch");
  add(health.canary_worker_origin === worker?.probe_url && health.canary_owner_count === 1 && gatewayEnv.SCAN_CANARY_WORKER_ORIGIN === worker?.probe_url && gatewayEnv.SCAN_CANARY_OWNER_USER_IDS === owner, "gateway_canary_route_mismatch");
  const infra = packet?.infrastructure, stageQueue = infra?.queue, bucket = infra?.bucket;
  fresh(infra, "infrastructure_missing_or_stale");
  add(stageQueue?.name === workerEnv.SCAN_STAGE_TASKS_QUEUE_PATH && stageQueue?.state === "RUNNING" && stageQueue?.rateLimits?.maxConcurrentDispatches === 40 && stageQueue?.retryConfig?.maxAttempts === 10 && stageQueue?.retryConfig?.minBackoff === "10s" && stageQueue?.retryConfig?.maxBackoff === "120s" && stageQueue?.retryConfig?.maxDoublings === 4 && stageQueue?.retryConfig?.maxRetryDuration === "1800s" && !stageQueue?.httpTarget, "stage_queue_contract_mismatch");
  const bucketUniform = bucket?.uniform_bucket_level_access ?? bucket?.iamConfiguration?.uniformBucketLevelAccess?.enabled;
  const bucketPublic = bucket?.public_access_prevention ?? bucket?.iamConfiguration?.publicAccessPrevention;
  const bucketRules = bucket?.lifecycle_config?.rule ?? bucket?.lifecycle?.rule;
  add(bucket?.name === workerEnv.SCAN_WORKSPACE_BUCKET && bucketUniform === true && bucketPublic === "enforced" && Array.isArray(bucketRules) && bucketRules.some(row => row?.action?.type === "Delete" && Object.keys(row.action).length === 1 && row?.condition?.age === 30 && Object.keys(row.condition).length === 1), "workspace_bucket_contract_mismatch");
  const workerSa = worker?.revision?.spec?.serviceAccountName;
  add(workerSa === workerAccount, "worker_service_identity_mismatch");
  for (const [policy, role] of [[infra?.bucket_policy, "roles/storage.objectUser"], [infra?.queue_policy, "roles/cloudtasks.enqueuer"], [infra?.invoker_policy, "roles/iam.serviceAccountUser"]]) {
    add(typeof workerSa === "string" && policy?.bindings?.some(row => row.role === role && !row.condition && row.members?.includes(`serviceAccount:${workerSa}`)) && !policy?.bindings?.some(row => row.members?.some(member => ["allUsers", "allAuthenticatedUsers"].includes(member))), `infrastructure_iam_mismatch:${role}`);
  }
  const task = infra?.task;
  const sample = task?.sample;
  const taskObserved = Date.parse(task?.observed_at);
  add(task?.schema_version === "staged_scan_task_observation_v1" && task.status === "verified_task_metadata"
    && task.source_sha === expected.sourceSha && task.worker_revision === worker?.revision?.metadata?.name
    && task.worker_config_sha256 === configDigest && task.queue_path === stageQueue?.name
    && Number.isFinite(taskObserved) && taskObserved <= now && now - taskObserved <= taskSampleLifetimeMs
    && /^scan-[a-f0-9]{64}$/.test(sample?.task_id || "")
    && ["batch", "finalize"].includes(sample?.stage)
    && sample?.target === `${workerEnv.SCAN_STAGE_TARGET_URL}/scan-${sample?.stage}`
    && sample?.dispatch_deadline_seconds === 480 && sample?.method === "POST"
    && sample?.oidc_invoker === invokerAccount && sample?.oidc_audience === workerEnv.SCAN_STAGE_TOKEN_AUDIENCE,
  "stage_task_contract_mismatch");
  return { ready: failures.length === 0, failures: [...new Set(failures)], provenance: failures.length ? null : {
    source_sha: expected.sourceSha, release_fingerprint: expected.fingerprint, observed_at: packet.observed_at, expires_at: packet.expires_at,
    worker_revision: worker.revision.metadata.name, gateway_revision: gateway.revision.metadata.name,
    worker_config_sha256: configDigest, staged_owner_cohort_sha256: cohort,
    base44_functions: functions.map(({ name, route_name, build_id, package_digest, runtime_activation_id }) => ({ name, route_name, build_id, package_digest, runtime_activation_id })),
    schema_readback_sha256: digest(packet.schema_readback.entity_sources), infrastructure_sha256: digest(infra), prerequisite_sha256: digest(packet),
  } };
}

// This function must remain self-contained: it also runs inside Base44 exec.
export async function executeStaged500Canary(base44, config, now = Date.now, sleep = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  const report = { schema_version: "staged_500_canary_v1", production_freeze: false, source_sha: config.sourceSha,
    expected_owner_user_id: config.ownerId, project_id: config.projectId, target_url: config.targetUrl, request_id: config.requestId,
    release_fingerprint: null, provenance: config.provenance, observed_at: new Date(now()).toISOString(), scan_id: null,
    attempt_count: null, scan_started_at: null, scan_completed_at: null,
    terminal_outcome_verified: false, functional_500_verified: false, full_500_gate: false, acceptance_verified: false,
    outcome: "unverified", progress: [], selection_coverage: null, durable_worker_owned: false, durable_worker_receipt_required: false,
    payload_bytes: { customer_projection: null, completion_request: null },
    memory: { finalize_peak_bytes: null, scope: "finalize_only", all_stages_verified: false }, unverified: ["completion_request_byte_measurement", "all_stage_memory_measurement", "per_scan_runtime_revision_receipt"], failure_code: null };
  const deadline = now() + config.maxWait * 1000;
  class CanaryCheckError extends Error {}
  const require = (value, code) => { if (!value) throw new CanaryCheckError(code); };
  const unwrap = value => value?.data && typeof value.data === "object" ? value.data : value;
  const integer = value => Number.isInteger(value) && value >= 0;
  const url = value => { try { return new URL(String(value)).href; } catch { return ""; } };
  function persistedTimestamp(value) {
    if (typeof value !== "string") return NaN;
    const match = /^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.exec(value);
    if (!match || match[1].startsWith("0000-")) return NaN;
    const date = new Date(`${match[1]}T00:00:00Z`);
    if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== match[1]) return NaN;
    return Date.parse(value);
  }
  async function signedSelectionCoverage(sampling, crawled) {
    const record = value => Boolean(value && typeof value === "object" && !Array.isArray(value));
    const discovered = sampling?.sections_discovered;
    const selected = sampling?.sections_selected;
    if (!record(discovered) || !record(selected)
        || !/^[a-z0-9_]{5,120}$/.test(sampling.sampling_version || "")
        || typeof sampling.inventory_capped !== "boolean" || sampling.pages_checked !== crawled
        || !integer(sampling.sitemap_urls_discovered) || sampling.sitemap_urls_discovered > 5000
        || !integer(sampling.sitemap_urls_selected) || sampling.sitemap_urls_selected > 499) return null;

    const names = Object.keys(discovered);
    if (names.length > sampling.sitemap_urls_discovered || Object.keys(selected).length !== names.length) return null;
    const omitted = [];
    let totalDiscovered = 0, totalSelected = 0;
    for (const section of names) {
      const count = discovered[section], chosen = selected[section];
      if (!section || section.length > 2000 || !integer(count) || count === 0
          || !Object.hasOwn(selected, section) || !integer(chosen) || chosen > count) return null;
      totalDiscovered += count;
      totalSelected += chosen;
      if (chosen === 0) omitted.push(section);
    }
    if (totalDiscovered !== sampling.sitemap_urls_discovered || totalSelected > sampling.sitemap_urls_selected
        || !Array.isArray(sampling.sections_never_selected) || sampling.sections_never_selected.length !== omitted.length) return null;
    const reportedOmissions = new Set(sampling.sections_never_selected);
    if (reportedOmissions.size !== omitted.length || omitted.some(section => !reportedOmissions.has(section))) return null;

    // Commit to section identities and counts without placing inventory paths
    // in CLI output. The offline replay uses the same sorted tuple encoding.
    const encode = new TextEncoder();
    const hash = async value => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", encode.encode(value))),
      byte => byte.toString(16).padStart(2, "0")).join("");
    const rows = await Promise.all(names.map(async section => [await hash(section), discovered[section], selected[section]]));
    rows.sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0);
    return { sampling_version: sampling.sampling_version, inventory_capped: sampling.inventory_capped,
      inventory_urls: totalDiscovered, selected_urls: sampling.sitemap_urls_selected,
      selected_inventory_urls: totalSelected, pages_checked: crawled,
      sections_discovered: rows.length, sections_never_selected: omitted.length, sections_sha256: await hash(JSON.stringify(rows)) };
  }
  async function bounded(operation) {
    const remaining = Math.min(30000, deadline - now()); require(remaining > 0, "scan_timeout");
    let timer; try { return await Promise.race([Promise.resolve().then(operation), new Promise((_, reject) => { timer = setTimeout(() => reject(new CanaryCheckError("operation_timeout")), remaining); })]); } finally { clearTimeout(timer); }
  }
  try {
    require(config.appId === "6a498732ec779dfaaeab0e53" && config.provenance?.source_sha === config.sourceSha && config.provenance?.release_fingerprint === config.expectedFingerprint && Date.parse(config.provenance?.expires_at) > now(), "prerequisites_invalid_or_expired");
    const published = Array.isArray(config.provenance.base44_functions) ? config.provenance.base44_functions : [];
    const launcher = published.find(row => row?.name === "startStandardScanJobV9");
    const reader = published.find(row => row?.name === "getCustomerScanResultV9");
    require(/^startStandardScanJobV9B[a-f0-9]{16}$/.test(config.launchRoute)
      && /^getCustomerScanResultV9B[a-f0-9]{16}$/.test(config.resultRoute)
      && config.launchRoute === launcher?.route_name && config.resultRoute === reader?.route_name,
    "staged_scan_routes_unverified");
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
    const accepted = unwrap(await bounded(() => base44.functions.invoke(config.launchRoute, { request_id: config.requestId, idempotency_key: config.requestId, project_id: config.projectId, website_url: config.targetUrl, submitted_url: config.targetUrl, scan_mode: "standard_500", source: "staged_500_acceptance" })));
    require(accepted?.success === true && accepted.accepted === true && accepted.scan_mode === "standard_500" && accepted.page_cap === 500 && accepted.pipeline_mode === "staged", "scan_not_accepted_as_staged_500");
    report.scan_id = String(accepted.scan_id || accepted.scan_run_id || ""); require(/^[A-Za-z0-9_-]{6,160}$/.test(report.scan_id), "scan_id_missing");
    let run, projection;
    while (now() < deadline) {
      projection = unwrap(await bounded(() => base44.functions.invoke(config.resultRoute, { scan_id: report.scan_id })));
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
    report.payload_bytes.customer_projection = new TextEncoder().encode(JSON.stringify(projection)).byteLength;
    const memory = projection.run.worker_peak_memory_bytes ?? projection.run.peak_memory_bytes;
    report.memory.finalize_peak_bytes = typeof memory === "number" && Number.isFinite(memory) && memory > 0 ? memory : null;
    require(integer(run.attempt_count) && run.attempt_count > 0 && run.attempt_count < 2 ** 31, "scan_attempt_unverified");
    const startedAt = persistedTimestamp(run.started_at);
    const completedAt = persistedTimestamp(run.completed_at);
    report.duration_ms = Number.isFinite(startedAt) && Number.isFinite(completedAt) ? completedAt - startedAt : null;
    require(Number.isFinite(report.duration_ms) && report.duration_ms > 0 && report.duration_ms <= 1800000, "duration_unverified");
    report.attempt_count = run.attempt_count;
    report.scan_started_at = run.started_at;
    report.scan_completed_at = run.completed_at;
    if (run.status === "complete") {
      require(projection.authority_verified === true && /^[a-f0-9]{64}$/.test(run.authority_proof || "") && Boolean(run.authority_seal_version), "complete_authority_unverified");
      require(projection.run.advanced_scan_backend === "python_scanner_api" && projection.run.deno_fallback_used === false
        && projection.run.ai_review_backend === "python_review_api" && projection.run.python_review_fallback_used === false, "durable_worker_evidence_missing");
      report.durable_worker_owned = true;
      // Slow batches may end at the stage work fuse before retaining 50 pages.
      // Such a terminal result is valid, but does not prove the ten-batch case.
      require(run.pages_crawled === run.pages_planned && report.committed_batch_count >= Math.ceil(run.pages_crawled / 50), "completed_batch_count_mismatch");
      report.outcome = "complete";
      report.functional_500_verified = run.pages_crawled === 500 && report.committed_batch_count === 10;
      // The verified current complete-result seal covers sampling_evidence.
      // Historical v1 and limited seals do not attest this field.
      if (run.authority_seal_version === "standard_review_snapshot_hmac_identity_v1") {
        report.selection_coverage = await signedSelectionCoverage(projection.run.sampling_evidence, run.pages_crawled);
      }
      if (!report.selection_coverage) report.unverified.push("signed_selection_coverage");
    } else {
      require(projection.result_integrity_verified === true && /^[a-f0-9]{64}$/.test(run.result_integrity_proof || "") && Boolean(run.result_integrity_version), "limited_integrity_unverified");
      require(projection.authority_verified !== true && projection.run.score_is_provisional === true && projection.run.release_gate_eligible === false && ["limited_coverage", "access_limited", "inventory_unproven"].includes(projection.run.coverage_state) && Boolean(projection.run.limitation) && Array.isArray(projection.fixItems) && projection.fixItems.length > 0, "limited_coverage_untruthful");
      const fixIds = new Set(projection.fixItems.map(fix => String(fix?.fix_id || fix?.issue_id || fix?.id || "")).filter(Boolean));
      require(Array.isArray(projection.top_fix_ids) && projection.top_fix_ids.length >= 1 && projection.top_fix_ids.length <= 3 && new Set(projection.top_fix_ids).size === projection.top_fix_ids.length && projection.top_fix_ids.every(id => typeof id === "string" && fixIds.has(id)), "limited_priorities_missing_or_invalid");
      const reasons = Array.isArray(projection.run.coverage_reasons) ? projection.run.coverage_reasons : [];
      const throttled = reasons.includes("staged_rate_limit");
      if (throttled) {
        require(run.result_integrity_version === "standard_limited_result_integrity_v5_report_evidence", "throttled_proof_version_unverified");
        const levels = ["critical", "high", "medium", "low"];
        const byId = new Map(projection.fixItems.map(fix => [fix?.fix_id, levels.indexOf(fix?.priority)]));
        const ranks = projection.top_fix_ids.map(id => byId.get(id));
        require(byId.size === projection.fixItems.length && ![...byId.values()].includes(-1)
          && ranks[0] === Math.min(...byId.values()) && ranks.every((rank, index) => rank >= 0 && (index === 0 || rank >= ranks[index - 1])),
        "throttled_priorities_unverified");
        report.throttled_priority_summary = ranks.map(rank => levels[rank]);
      }
      const budget = reasons.includes("staged_wall_budget");
      require(throttled || budget || reasons.includes("staged_partial_evidence"), "limited_termination_reason_missing");
      report.termination_reasons = reasons.filter(reason => ["rate_limit", "rate_limited", "throttled", "staged_rate_limit", "staged_wall_budget", "staged_partial_evidence"].includes(reason));
      report.outcome = throttled ? "limited_throttled" : budget ? "limited_budget" : "limited_partial";
      // Limited seals do not attest the scan/review backend fields. The
      // independent receipt must bind this result to the exact worker.
      report.durable_worker_receipt_required = true;
    }
    report.terminal_outcome_verified = true;
    if (!report.memory.finalize_peak_bytes) report.unverified.push("finalize_memory_measurement");
    // The private workspace receipt collector measures the completion request
    // and per-stage memory separately from this customer readback.
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
  const { schema_version, functions } = JSON.parse(fs.readFileSync(path.join(root, "data/generated-staged-v9-routes.json"), "utf8"));
  if (schema_version !== "fixlist_staged_v9_routes_v1" || !functions
    || Object.keys(functions).length !== STAGED_RELEASE_FUNCTIONS.length) throw new Error("staged_deployment_manifest_invalid");
  for (const name of STAGED_RELEASE_FUNCTIONS) {
    const identity = functions[name];
    if (!identity || !new RegExp(`^${name}B[a-f0-9]{16}$`).test(identity.route_name)
      || !/^[a-f0-9]{64}$/.test(identity.build_id) || !/^[a-f0-9]{64}$/.test(identity.package_digest)
      || !/^[A-Za-z0-9._-]{1,120}$/.test(identity.runtime_activation_id)) throw new Error("staged_deployment_identity_invalid");
  }
  return { sourceSha, ownerId, fingerprint: JSON.parse(fs.readFileSync(path.join(root, "data/beta-crawler-revision.json"), "utf8")).fingerprint, functions, entitySources: Object.fromEntries(STAGED_RELEASE_ENTITIES.map(name => [name, fs.readFileSync(path.join(root, "base44/entities", `${name}.jsonc`), "utf8")])) };
}

export function assemblePrerequisites({ base44, schema, intake, cloud, task }, expected, now = Date.now()) {
  if (schema?.schema_version !== "fixlist_staged_schema_v1" || schema.action !== "verify"
      || schema.status !== "live_match" || schema.live_verified !== true || schema.readback_verified !== true
      || schema.local_source_verified !== true || schema.execution_environment !== "production"
      || cloud?.schema_version !== "staged_scan_gcp_observations_v1"
      || cloud.source_sha !== expected.sourceSha || cloud.release_fingerprint !== expected.fingerprint) {
    throw new Error("live_observations_unverified");
  }
  const sourceTime = [base44, schema, intake, cloud, cloud.worker, cloud.gateway, cloud.infrastructure]
    .map(record => Date.parse(record?.observed_at));
  const expires = Math.min(...sourceTime.map(time => time + 900_000),
    ...[cloud, cloud.worker, cloud.gateway, cloud.infrastructure].map(record => record?.expires_at == null ? Infinity : Date.parse(record.expires_at)));
  if (!sourceTime.every(Number.isFinite) || !Number.isFinite(expires) || expires <= now) throw new Error("live_observations_stale");
  const observed_at = new Date(Math.min(now, ...sourceTime)).toISOString();
  const expires_at = new Date(expires).toISOString();
  const packet = {
    schema_version: "staged_scan_acceptance_prerequisites_v1", source_sha: expected.sourceSha,
    release_fingerprint: expected.fingerprint, observed_at, expires_at,
    base44: { ...base44, expires_at },
    schema_readback: { observed_at: schema.observed_at, expires_at, source_sha: schema.source_sha, app_id: schema.app_id,
      entity_sources: Object.fromEntries(STAGED_RELEASE_ENTITIES.map(name => [name, JSON.stringify(schema.before_schemas?.[name])])) },
    base44_configuration: { observed_at: intake.observed_at, expires_at, source_sha: expected.sourceSha, intake_route: intake },
    worker: { ...cloud.worker, expires_at },
    gateway: { ...cloud.gateway, expires_at },
    infrastructure: { ...cloud.infrastructure, expires_at, task },
  };
  const check = validatePrerequisites(packet, { ...expected, now });
  if (!check.ready) throw new Error(check.failures.join(","));
  return packet;
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
    if (mode === "describe-prerequisites") console.log(JSON.stringify({ schema_version: "staged_scan_acceptance_prerequisites_v1", required_observations: REQUIRED_OBSERVATIONS, freshness_seconds: 900, stage_task_max_age_seconds: taskSampleLifetimeMs / 1000 }, null, 2));
    else if (mode === "assemble-prerequisites") {
      if (process.argv.length !== 9) throw new Error("expected six paths: package schema intake cloud task output");
      const [base44File, schemaFile, intakeFile, cloudFile, taskFile, output] = process.argv.slice(3);
      const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
      const expected = localAcceptanceIdentity(root, process.env.SOURCE_SHA, process.env.EXPECTED_OWNER_USER_ID);
      const read = file => {
        if (!path.isAbsolute(file) || !fs.lstatSync(file).isFile() || fs.realpathSync(file) !== file) throw new Error("observation_path_invalid");
        return JSON.parse(fs.readFileSync(file, "utf8"));
      };
      const packet = assemblePrerequisites({ base44: read(base44File), schema: read(schemaFile), intake: read(intakeFile),
        cloud: read(cloudFile), task: read(taskFile) }, expected);
      writeNewArtifact(output, packet, root);
      console.log("STAGED_500_PREREQUISITES_ASSEMBLED");
    }
    else if (mode === "render") {
      const env = process.env, root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
      const expected = localAcceptanceIdentity(root, env.SOURCE_SHA, env.EXPECTED_OWNER_USER_ID);
      const packet = JSON.parse(fs.readFileSync(env.PREREQUISITES_FILE, "utf8"));
      const validation = validatePrerequisites(packet, expected);
      if (!validation.ready) throw new Error(validation.failures.join(","));
      if (!id(env.EXPECTED_OWNER_USER_ID) || !id(env.PROJECT_ID) || !id(env.REQUEST_ID) || !origin(env.TARGET_URL)) throw new Error("scan_input_invalid");
      const maxWait = Number(env.MAX_WAIT_SECONDS || 900), pollSeconds = Number(env.POLL_SECONDS || 5);
      if (!Number.isInteger(maxWait) || maxWait < 1 || maxWait > 1800 || !Number.isInteger(pollSeconds) || pollSeconds < 1 || pollSeconds > 60) throw new Error("scan_timeout_invalid");
      const launchRoute = expected.functions.startStandardScanJobV9.route_name;
      const resultRoute = expected.functions.getCustomerScanResultV9.route_name;
      process.stdout.write(renderRemoteCanary({ appId: APP_ID, sourceSha: env.SOURCE_SHA, ownerId: env.EXPECTED_OWNER_USER_ID, projectId: env.PROJECT_ID, requestId: env.REQUEST_ID, targetUrl: origin(env.TARGET_URL), expectedFingerprint: expected.fingerprint, maxWait, pollSeconds, provenance: validation.provenance, launchRoute, resultRoute }));
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
    } else throw new Error("Use render, collect, assemble-prerequisites, or describe-prerequisites");
  } catch (error) { console.error(`STAGED_500_ACCEPTANCE_BLOCKED: ${error.message}`); process.exitCode = 2; }
}
