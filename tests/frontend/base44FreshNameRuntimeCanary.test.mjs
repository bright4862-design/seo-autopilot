import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const WORKFLOW = ".github/workflows/fixlist-base44-fresh-name-canary.yml";
const WORKFLOWS_DIR = ".github/workflows";
const CANARY_PREFIX = "fixlistRuntimeActivationProbe";
const STATIC_CANARY_NAME = "fixlistRuntimeActivationProbe20260907A";
const BASE44_MUTATION_LOCK = /group:\s*fixlist-base44-hosted-controls-v2/;

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

test("every hosted Base44 mutation workflow shares one external serialization lock", () => {
  const workflowFiles = fs.readdirSync(WORKFLOWS_DIR)
    .filter((name) => /\.ya?ml$/.test(name));

  const mutationSignal = /functions (?:deploy|delete)|scripts\/(?:deploy|recover|set)-base44-[A-Za-z0-9._-]+\.sh/;
  const mutators = workflowFiles
    .map((name) => ({
      name,
      content: fs.readFileSync(`${WORKFLOWS_DIR}/${name}`, "utf8"),
    }))
    .filter(({ content }) => mutationSignal.test(content));

  assert.ok(mutators.length >= 6,
    `expected the canary plus established Base44 mutation workflows, found ${mutators.length}`);

  for (const { name, content } of mutators) {
    assert.match(content, /scripts\/authenticate-base44-owner-session\.sh/,
      `${name} must use the owner-authenticated Base44 production path`);
    assert.match(content, /environment:\s*fixlist-production-owner/,
      `${name} must use the production-owner environment`);
    assert.match(content, BASE44_MUTATION_LOCK,
      `${name} must share the external Base44 mutation serialization lock`);
  }
});
