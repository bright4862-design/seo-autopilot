import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const WORKFLOW = ".github/workflows/fixlist-base44-fresh-name-canary.yml";
const CANARY_PREFIX = "fixlistRuntimeActivationProbe";
const STATIC_CANARY_NAME = "fixlistRuntimeActivationProbe20260907A";

test("fresh-name Base44 runtime canary is exact-main, owner-gated, isolated, and collision-hardened", () => {
  const workflow = fs.readFileSync(WORKFLOW, "utf8");

  assert.match(workflow, /github\.actor == 'bright4862-design'/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /environment:\s*fixlist-production-owner/);
  assert.match(workflow, /group:\s*fixlist-base44-hosted-controls-v2/,
    "the canary must serialize with publication and runtime recovery");
  assert.match(workflow, /DEPLOY-FRESH-BASE44-RUNTIME-CANARY/);
  assert.match(workflow, new RegExp(CANARY_PREFIX));

  assert.match(workflow, /git rev-parse HEAD/);
  assert.match(workflow, /git rev-parse origin\/main/);
  assert.match(workflow, /functions list/);
  assert.match(workflow, /Refusing fresh-name canary: .*already exists/,
    "an already-used name must refuse rather than be recycled");
  assert.match(workflow, /openssl rand -hex 8/,
    "the deployment name must include a fresh cryptographic nonce");
  assert.match(workflow, /GITHUB_RUN_ID/,
    "the deployment name must be scoped to the unique workflow run");
  assert.doesNotMatch(workflow, new RegExp(STATIC_CANARY_NAME),
    "a predictable fixed canary name leaves a check-then-deploy overwrite race");
  assert.match(workflow, /functions deploy "\$CANARY_NAME"/);
  assert.match(workflow, /functions pull "\$CANARY_NAME"/,
    "the workflow must read back the stored package before accepting ownership");
  assert.doesNotMatch(workflow, /functions delete/,
    "the diagnostic must never delete or recycle a remote function name");

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
