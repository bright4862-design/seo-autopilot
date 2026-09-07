import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const WORKFLOW = ".github/workflows/fixlist-base44-fresh-name-canary.yml";
const WORKFLOWS_DIR = ".github/workflows";
const CANARY_PREFIX = "fixlistRuntimeActivationProbe";
const STATIC_CANARY_NAME = "fixlistRuntimeActivationProbe20260907A";
const BASE44_MUTATION_LOCK = /group:\s*fixlist-base44-hosted-controls-v2/;

function withoutYamlComments(value) {
  return value
    .split("\n")
    .filter((line) => !/^\s*#/.test(line))
    .join("\n");
}

function workflowJobs(content) {
  const lines = content.split("\n");
  const jobsIndex = lines.findIndex((line) => /^jobs:\s*$/.test(line));
  assert.notEqual(jobsIndex, -1, "workflow must contain a jobs section");

  const preamble = lines.slice(0, jobsIndex).join("\n");
  const jobs = [];
  let current = null;

  for (const line of lines.slice(jobsIndex + 1)) {
    const jobStart = line.match(/^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$/);
    if (jobStart) {
      if (current) jobs.push(current);
      current = { name: jobStart[1], lines: [line] };
      continue;
    }
    if (current) current.lines.push(line);
  }
  if (current) jobs.push(current);

  return {
    preamble,
    jobs: jobs.map(({ name, lines: jobLines }) => ({
      name,
      content: jobLines.join("\n"),
    })),
  };
}

test("fresh-name Base44 runtime canary is exact-main, owner-gated, isolated, and collision-hardened", () => {
  const workflow = fs.readFileSync(WORKFLOW, "utf8");

  assert.match(workflow, /github\.actor == 'bright4862-design'/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /environment:\s*fixlist-production-owner/);
  assert.match(workflow, BASE44_MUTATION_LOCK,
    "the canary must serialize with every hosted Base44 writer");
  assert.match(workflow, /DEPLOY-FRESH-BASE44-RUNTIME-CANARY/);
  assert.match(workflow, new RegExp(CANARY_PREFIX));

  assert.match(workflow, /git rev-parse HEAD/);
  assert.match(workflow, /git rev-parse origin\/main/);
  assert.match(workflow, /functions list/);
  assert.match(workflow, /Refusing fresh-name canary: .*already exists/,
    "an already-used name must refuse rather than be recycled");
  assert.match(
    workflow,
    /mkdir -p "\$WORK_TMP\/base44"[\s\S]*cp "\$GITHUB_WORKSPACE\/base44\/config\.jsonc" "\$WORK_TMP\/base44\/config\.jsonc"[\s\S]*cd "\$WORK_TMP"[\s\S]*functions deploy "\$CANARY_NAME"/,
    "the deploy workspace must contain Base44 project config before functions deploy",
  );

  assert.match(
    workflow,
    /nonce="\$\(openssl rand -hex 8\)"[\s\S]*CANARY_NAME="\$\{CANARY_PREFIX\}\$\{GITHUB_RUN_ID\}\$\{nonce\}"/,
    "CANARY_NAME itself must be built from the run id and fresh cryptographic nonce",
  );
  assert.match(
    workflow,
    /CANARY_NAME="\$\{CANARY_PREFIX\}\$\{GITHUB_RUN_ID\}\$\{nonce\}"[\s\S]*PROBE_ID="base44-fresh-name-\$\{GITHUB_RUN_ID\}-\$\{nonce\}"/,
    "the probe identity must be bound to the same run and nonce as the function name",
  );
  assert.doesNotMatch(workflow, new RegExp(STATIC_CANARY_NAME),
    "a predictable fixed canary name leaves a check-then-deploy overwrite race");
  assert.match(
    workflow,
    /functions deploy "\$CANARY_NAME"[\s\S]*functions pull "\$CANARY_NAME"[\s\S]*probe_url="\$BASE44_FUNCTION_ORIGIN\/api\/apps\/\$BASE44_APP_ID\/functions\/\$CANARY_NAME"/,
    "one generated CANARY_NAME must flow through deploy, remote readback, and live probing",
  );
  assert.doesNotMatch(workflow, /functions delete/,
    "the diagnostic must never delete or recycle a remote function name");
  assert.doesNotMatch(workflow, /--force/,
    "the diagnostic must never use prune/force semantics to make a name reusable");

  assert.match(workflow, /source_sha/);
  assert.match(workflow, /github\.sha/);
  assert.match(workflow, /probe_id/);
  assert.match(workflow, /BASE44_FRESH_NAME_RUNTIME_VERIFIED/);

  for (const customerRoute of [
    "startStandardScanJobV2",
    "durableScanWorkerControlV2",
    "persistDurableScanAuthorityV2",
    "persistLimitedScanResultV2",
    "getCustomerScanResultV2",
    "deleteCustomerScanDataV2",
  ]) {
    assert.doesNotMatch(workflow, new RegExp(customerRoute),
      `${customerRoute} must not be touched by the fresh-name diagnostic`);
  }
});

test("every hosted Base44 mutation job is owner-gated and shares one external serialization lock", () => {
  const workflowFiles = fs.readdirSync(WORKFLOWS_DIR)
    .filter((name) => /\.ya?ml$/.test(name));

  const directMutation = /functions (?:deploy|delete)/;
  const scriptMutation = /(?:^|\s)(?:\/bin\/bash|bash)\s+scripts\/(?:deploy|recover|set)-base44-[A-Za-z0-9._-]+\.sh(?:\s|$)/m;
  const mutators = [];

  for (const name of workflowFiles) {
    const content = fs.readFileSync(`${WORKFLOWS_DIR}/${name}`, "utf8");
    const parsed = workflowJobs(content);
    const workflowPreamble = withoutYamlComments(parsed.preamble);
    const workflowHasSharedLock = BASE44_MUTATION_LOCK.test(workflowPreamble);

    for (const job of parsed.jobs) {
      const jobContent = withoutYamlComments(job.content);
      if (!directMutation.test(jobContent) && !scriptMutation.test(jobContent)) continue;
      mutators.push({ name, job: job.name });

      assert.match(jobContent, /scripts\/authenticate-base44-owner-session\.sh/,
        `${name}:${job.name} must authenticate the Base44 owner in the mutating job`);
      assert.match(jobContent, /environment:\s*fixlist-production-owner/,
        `${name}:${job.name} must protect the mutating job with the production-owner environment`);
      assert.ok(workflowHasSharedLock || BASE44_MUTATION_LOCK.test(jobContent),
        `${name}:${job.name} must share the external Base44 mutation serialization lock`);
    }
  }

  assert.ok(mutators.length >= 6,
    `expected the canary plus established Base44 mutation jobs, found ${mutators.length}`);
});
