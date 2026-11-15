import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

const configure = readFileSync("scripts/configure-standard150-reconciler.sh", "utf8");
const verify = readFileSync("scripts/verify-standard150-reconciler.sh", "utf8");
const worker = readFileSync("scanner-api/app/main.py", "utf8");

test("Scheduler reconciler is confirmation-gated and targets only the private reconciliation route", () => {
  assert.match(configure, /CONFIGURE-STANDARD150-RECONCILER/);
  assert.match(configure, /STANDARD150_RECONCILER_SCHEDULE:-\*\/5 \* \* \* \*/);
  assert.match(configure, /TARGET_URL="\$WORKER_URL\/scan-reconcile"/);
  assert.match(configure, /--http-method=POST/);
  assert.match(configure, /--oidc-service-account-email="\$INVOKER_SA"/);
  assert.match(configure, /--oidc-token-audience="\$WORKER_URL"/);
  assert.doesNotMatch(configure, /allow-unauthenticated|run services update|tasks queues update/);
});

test("reconciler verifier is read-only and pins route, schedule, OIDC identity and enabled state", () => {
  assert.match(verify, /scheduler jobs describe/);
  assert.match(verify, /run services describe/);
  assert.doesNotMatch(verify, /scheduler jobs (?:create|update|delete|pause|resume|run)|run services (?:update|deploy)|tasks queues update/);
  for (const contract of ["ENABLED", "/scan-reconcile", "serviceAccountEmail", "audience", "POST"]) {
    assert.ok(verify.includes(contract), contract);
  }
});

test("reconciliation route uses the same private worker invoker guard", () => {
  const route = worker.split('@app.post("/scan-reconcile")', 2)[1].split('@app.post("/scan-job-drain")', 1)[0];
  assert.match(route, /require_cloud_tasks_oidc\(authorization\)/);
});

test("release docs and read-only operator surface the Scheduler backstop", () => {
  const docs = readFileSync("docs/standard150-deployment-contract.md", "utf8");
  const operator = readFileSync("scripts/fixlist-cloud-operator.sh", "utf8");
  assert.match(docs, /fixlist-standard150-reconcile/);
  assert.match(docs, /Bound admission is not released by wall-clock lease expiry/);
  assert.match(operator, /scheduler jobs describe/);
  assert.doesNotMatch(operator, /scheduler jobs (?:create|update|delete)/);
});

const project = "seo-autopilot-501517";
const region = "europe-west1";
const serviceName = "fixlist-standard150-worker";
const revisionName = `${serviceName}-00109-nn7`;
const oldRevision = `${serviceName}-00108-nn7`;
const origin = `https://${serviceName}-test-ew.a.run.app`;
const invoker = `fixlist-standard150-invoker@${project}.iam.gserviceaccount.com`;
const source = "a".repeat(40);
const tag = `staged-${source.slice(0, 12)}`;
const taggedUrl = origin.replace("https://", `https://${tag}---`);
const reviewed = {
  SCAN_WORKSPACE_BUCKET: `fixlist-scan-workspaces-${project}`,
  SCAN_TASKS_PROJECT: project,
  SCAN_TASKS_LOCATION: region,
  SCAN_STAGE_QUEUE: "fixlist-scan-stages",
  SCAN_STAGE_TASKS_QUEUE_PATH: `projects/${project}/locations/${region}/queues/fixlist-scan-stages`,
  SCAN_STAGE_TARGET_URL: taggedUrl,
  SCAN_STAGE_TOKEN_AUDIENCE: origin,
  SCAN_PIPELINE_MODE: "monolith",
  SCAN_STAGED_OWNER_IDS: "",
};
const digest = createHash("sha256").update(JSON.stringify({
  environment: Object.fromEntries(Object.keys(reviewed).sort().map(key => [key, reviewed[key]])),
  source_sha: source,
})).digest("hex");

function recordedResources() {
  return {
    service: { metadata: { name: serviceName }, status: { url: origin, traffic: [
      { revisionName, percent: 100 }, { revisionName, tag, url: taggedUrl },
      { revisionName: oldRevision, tag: "canary-00108-nn7", url: origin.replace("https://", "https://canary-00108-nn7---") },
    ] } },
    revision: { metadata: { name: revisionName }, status: { conditions: [{ type: "Ready", status: "True" }] },
      spec: { containers: [{ env: Object.entries({ ...reviewed, FIXLIST_WORKER_SOURCE_SHA: source,
        FIXLIST_STAGED_CONFIG_SHA256: digest, TASKS_INVOKER_SERVICE_ACCOUNT: invoker,
      }).map(([name, value]) => ({ name, value })) }] } },
    job: { state: "ENABLED", schedule: "*/5 * * * *", httpTarget: { uri: `${origin}/scan-reconcile`, httpMethod: "POST",
      oidcToken: { serviceAccountEmail: invoker, audience: origin } } },
  };
}

function runVerifier(t, { resources = recordedResources(), settings = {} } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "standard150-reconciler-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  writeFileSync(join(dir, "gcloud"), `#!/bin/bash
printf '%s\n' "$*" >> "$RECONCILER_FIXTURE_LOG"
case "$1 $2 $3" in
  "run services describe") printf '%s\n' "$RECONCILER_FIXTURE_SERVICE" ;;
  "run revisions describe") printf '%s\n' "$RECONCILER_FIXTURE_REVISION" ;;
  "scheduler jobs describe") printf '%s\n' "$RECONCILER_FIXTURE_JOB" ;;
  *) exit 30 ;;
esac
`, { mode: 0o700 });
  writeFileSync(join(dir, "gcloud.log"), "");
  const result = spawnSync("/bin/bash", ["scripts/verify-standard150-reconciler.sh"], { encoding: "utf8", env: {
    ...process.env, PATH: `${dir}:${process.env.PATH}`, GCP_PROJECT: project, GCP_REGION: region, CLOUD_RUN_SERVICE: serviceName,
    TASKS_INVOKER_SERVICE_ACCOUNT: invoker, STANDARD150_RECONCILER_JOB: "fixlist-standard150-reconcile",
    STANDARD150_RECONCILER_SCHEDULE: "*/5 * * * *", RECONCILER_EXPECTED_SOURCE_SHA: "",
    RECONCILER_EXPECTED_STAGED_CONFIG_SHA256: "", RECONCILER_EXPECTED_REVISION: "",
    RECONCILER_FIXTURE_LOG: join(dir, "gcloud.log"), RECONCILER_FIXTURE_SERVICE: JSON.stringify(resources.service),
    RECONCILER_FIXTURE_REVISION: JSON.stringify(resources.revision), RECONCILER_FIXTURE_JOB: JSON.stringify(resources.job),
    ...settings,
  } });
  return { ...result, calls: readFileSync(join(dir, "gcloud.log"), "utf8") };
}

const staged = { RECONCILER_EXPECTED_SOURCE_SHA: source, RECONCILER_EXPECTED_STAGED_CONFIG_SHA256: digest,
  RECONCILER_EXPECTED_REVISION: revisionName };

test("legacy reconciliation still verifies only the enabled canonical Scheduler contract", t => {
  const resources = recordedResources();
  delete resources.service.status.traffic;
  const result = runVerifier(t, { resources });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), "STANDARD150_RECONCILER_VERIFIED");
  assert.doesNotMatch(result.calls, /run revisions/);
});

test("staged reconciliation verifies the single serving source, reviewed config and canonical Scheduler", t => {
  const result = runVerifier(t, { settings: staged });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, new RegExp(`STANDARD150_STAGED_RECONCILER_VERIFIED revision=${revisionName}`));
  assert.match(result.calls, new RegExp(`run revisions describe ${revisionName} `));
});

test("staged capability works with empty Cloud Run env defaults or a single exact owner", t => {
  for (const cohort of [null, "owner_001"]) {
    const resources = recordedResources();
    const env = Object.fromEntries(resources.revision.spec.containers[0].env.map(entry => [entry.name, entry]));
    if (cohort) {
      env.SCAN_PIPELINE_MODE.value = "staged";
      env.SCAN_STAGED_OWNER_IDS.value = cohort;
    } else {
      delete env.SCAN_STAGED_OWNER_IDS.value;
    }
    const result = runVerifier(t, { resources, settings: { ...staged, RECONCILER_EXPECTED_REVISION: "" } });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /STANDARD150_STAGED_RECONCILER_VERIFIED/);
  }
});

test("staged reconciliation rejects incomplete expected identities before gcloud reads", t => {
  for (const settings of [{ RECONCILER_EXPECTED_SOURCE_SHA: source }, { ...staged, RECONCILER_EXPECTED_STAGED_CONFIG_SHA256: "bad" }]) {
    const result = runVerifier(t, { settings });
    assert.notEqual(result.status, 0);
    assert.equal(result.calls, "");
  }
});

test("staged reconciliation fails closed on split serving, drifted config, mutable tags and Scheduler mismatch", t => {
  const replaceEnv = (r, name, value) => {
    r.revision.spec.containers[0].env = r.revision.spec.containers[0].env.filter(item => item.name !== name);
    if (value !== undefined) r.revision.spec.containers[0].env.push({ name, value });
  };
  const failures = {
    split: r => { r.service.status.traffic[0].percent = 99; r.service.status.traffic[2].percent = 1; },
    overallocated: r => { r.service.status.traffic[2].percent = 1; },
    latestAlias: r => { r.service.status.traffic[0].latestRevision = true; },
    wrongRevision: r => { r.revision.metadata.name = oldRevision; },
    notReady: r => { r.revision.status.conditions[0].status = "False"; },
    wrongSource: r => replaceEnv(r, "FIXLIST_WORKER_SOURCE_SHA", "b".repeat(40)),
    wrongConfigStamp: r => replaceEnv(r, "FIXLIST_STAGED_CONFIG_SHA256", "b".repeat(64)),
    absentBucket: r => replaceEnv(r, "SCAN_WORKSPACE_BUCKET"),
    wrongQueue: r => replaceEnv(r, "SCAN_STAGE_TASKS_QUEUE_PATH", `projects/${project}/locations/${region}/queues/other`),
    wrongTarget: r => replaceEnv(r, "SCAN_STAGE_TARGET_URL", origin),
    wildcard: r => { replaceEnv(r, "SCAN_PIPELINE_MODE", "staged"); replaceEnv(r, "SCAN_STAGED_OWNER_IDS", "*"); },
    tagPointsElsewhere: r => { r.service.status.traffic[1].revisionName = oldRevision; },
    schedulerTag: r => { r.job.httpTarget.uri = `${taggedUrl}/scan-reconcile`; },
    schedulerAudience: r => { r.job.httpTarget.oidcToken.audience = taggedUrl; },
  };
  for (const [failure, mutate] of Object.entries(failures)) {
    const resources = recordedResources();
    mutate(resources);
    const result = runVerifier(t, { resources, settings: { ...staged, PYTHONOPTIMIZE: "1" } });
    assert.notEqual(result.status, 0, failure);
    assert.doesNotMatch(result.stdout, /RECONCILER_VERIFIED/, failure);
  }
});
