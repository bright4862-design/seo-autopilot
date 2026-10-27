// Production incident guard: the safe one-off diagnosis must not depend on
// changing Cloud Run traffic, source fingerprints, queues or persisted scans.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const workflow = fs.readFileSync(".github/workflows/fixlist-cloud-operator.yml", "utf8");
const operator = fs.readFileSync("scripts/fixlist-cloud-operator.sh", "utf8");

function step(name) {
  const marker = `      - name: ${name}\n`;
  const start = workflow.indexOf(marker);
  assert.ok(start >= 0, `missing workflow step: ${name}`);
  const next = workflow.indexOf("      - name:", start + marker.length);
  return workflow.slice(start, next < 0 ? undefined : next);
}

test("release investigation is an explicit owner-only read-only workflow operation", () => {
  assert.match(workflow, /^\s+- verify-serving-worker-release\s*$/m);
  assert.match(workflow, /github\.actor == 'bright4862-design'/);
  assert.match(workflow, /test "\$\{\{ github\.ref \}\}" = "refs\/heads\/main"/);
  const generic = step("Run allowlisted worker operation");
  assert.match(generic, /inputs\.operation != 'verify-serving-worker-release'/);
  assert.match(operator, /verify-worker-runtime-revision\)/);
});

test("private serving-worker probe uses the exact canonical Cloud Run token audience", () => {
  const audience = step("Resolve serving worker token audience (read only)");
  const token = step("Mint serving worker invoker identity token (read only)");
  const probe = step("Verify 100%-serving worker release identity (read only)");
  for (const text of [audience, token, probe]) {
    assert.match(text, /if: inputs\.operation == 'verify-serving-worker-release'/);
  }
  assert.match(audience, /gcloud run services describe "\$CLOUD_RUN_SERVICE"/);
  assert.match(audience, /value\(status\.url\)/);
  assert.match(token, /token_format: id_token/);
  assert.match(token, /create_credentials_file: false/);
  assert.match(token, /id_token_audience: \$\{\{ steps\.serving-worker-url\.outputs\.url \}\}/);
  assert.match(probe, /OPERATION: verify-worker-runtime-revision/);
  // Do not honor the old prefilled candidate 'revision' workflow input.
  assert.match(probe, /TARGET_REVISION: ""/);
  assert.match(probe, /SOURCE_SHA: \$\{\{ github\.sha \}\}/);
  assert.match(probe, /FIXLIST_WORKER_ID_TOKEN: \$\{\{ steps\.serving-worker-token\.outputs\.id_token \}\}/);
  assert.match(probe, /FIXLIST_WORKER_TOKEN_AUDIENCE: \$\{\{ steps\.serving-worker-url\.outputs\.url \}\}/);
  for (const forbidden of [
    /update-traffic/, /--set-tags/, /queues pause/, /queues resume/,
    /gcloud run deploy/, /releaseAdmission/, /SCAN_EVIDENCE_SIGNING_KEY/,
  ]) assert.doesNotMatch(audience + token + probe, forbidden);
});

test("the reused runtime verifier checks live full component set, fingerprint and source SHA", () => {
  assert.match(operator, /verify_worker_runtime_revision\(\)/);
  assert.match(operator, /live\.get\("fingerprint"\)/);
  assert.match(operator, /recorded\.get\("fingerprint"\)/);
  assert.match(operator, /live\.get\("component_versions"\)/);
  assert.match(operator, /recorded\.get\("component_versions"\)/);
  assert.match(operator, /live\.get\("source_sha"\)/);
  assert.match(operator, /if live_components != recorded_components/);
  assert.match(operator, /if live_fingerprint != recorded_fingerprint/);
});
