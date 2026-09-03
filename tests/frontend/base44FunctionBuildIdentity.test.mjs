import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
const GENERATOR = path.join(ROOT, "scripts/generate_release_contracts.mjs");
const RELEASE_FUNCTIONS = [
  "startStandardScanJob",
  "durableScanWorkerControl",
  "persistDurableScanAuthority",
  "persistLimitedScanResult",
  "getCustomerScanResult",
  "createAccessCheckout",
  "stripeWebhook",
  "deleteCustomerScanData",
  "ownerScanDebugControl",
];

function source(relative, root = ROOT) {
  return fs.readFileSync(path.join(root, relative), "utf8");
}

function buildId(fnName, root) {
  return execFileSync(process.execPath, [GENERATOR, "--build-id", fnName], {
    cwd: ROOT,
    env: { ...process.env, RELEASE_CONTRACT_ROOT: root },
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function copyFunction(fnName, root) {
  const from = path.join(ROOT, "base44/functions", fnName);
  const to = path.join(root, "base44/functions", fnName);
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.cpSync(from, to, { recursive: true });
  return to;
}

test("every published Base44 function exposes its generated build id before auth", () => {
  for (const fnName of RELEASE_FUNCTIONS) {
    const config = source(`base44/functions/${fnName}/function.jsonc`);
    const entry = config.match(/"entry"\s*:\s*"([^"]+)"/)?.[1];
    assert.ok(entry, `${fnName} must declare an entry`);

    const entrySource = source(`base44/functions/${fnName}/${entry}`);
    const handlerSource = fnName === "deleteCustomerScanData"
      ? source("base44/functions/deleteCustomerScanData/index.ts")
      : entrySource;

    assert.match(
      handlerSource,
      /import\s+\{\s*FUNCTION_BUILD_ID\s*\}\s+from\s+["']\.\/generatedBuildId\.js["']/,
      `${fnName} must import its generated build identity`,
    );
    assert.match(
      handlerSource,
      /req\.method\s*!==\s*["']POST["'][\s\S]{0,400}build_id\s*:\s*FUNCTION_BUILD_ID/,
      `${fnName} must return build_id on its cheap non-POST branch`,
    );

    const generated = source(`base44/functions/${fnName}/generatedBuildId.js`);
    assert.match(generated, /FUNCTION_BUILD_ID\s*=\s*"[0-9a-f]{64}"/);
  }
});

test("function build identity changes when package source bytes change", (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-build-id-content-"));
  t.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));
  const dir = copyFunction("startStandardScanJob", tempRoot);

  const before = buildId("startStandardScanJob", tempRoot);
  const target = path.join(dir, "admission.js");
  fs.appendFileSync(target, "\n// build-id mutation proof\n");
  const after = buildId("startStandardScanJob", tempRoot);

  assert.match(before, /^[0-9a-f]{64}$/);
  assert.match(after, /^[0-9a-f]{64}$/);
  assert.notEqual(after, before, "source-byte mutation must move the build identity");
});

test("generatedBuildId.js is excluded from its own package hash", (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-build-id-self-"));
  t.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));
  const dir = copyFunction("startStandardScanJob", tempRoot);

  const before = buildId("startStandardScanJob", tempRoot);
  fs.writeFileSync(
    path.join(dir, "generatedBuildId.js"),
    'export const FUNCTION_BUILD_ID = "' + "f".repeat(64) + '";\n',
  );
  const after = buildId("startStandardScanJob", tempRoot);

  assert.equal(after, before, "generatedBuildId.js must never participate in its own hash");
});

test("publish verifies deployed function source before the success marker", () => {
  const deploy = source("scripts/deploy-base44-beta-site.sh");
  const verifyAt = deploy.indexOf('verify-base44-functions.sh');
  const successAt = deploy.indexOf("BASE44_SITE_AND_BACKEND_DEPLOYED");

  assert.ok(verifyAt >= 0, "publish must call the function build verifier");
  assert.ok(successAt >= 0, "publish success marker must remain explicit");
  assert.ok(verifyAt < successAt, "function verification must happen before deployment success is reported");
  assert.match(deploy, /generate_release_contracts\.mjs" --check/);
  assert.match(deploy, /DEPLOY_REPORT=/, "the Base44 function deploy report must be retained");
});

test("runtime verifier requires the handler 405 and the exact build id", () => {
  const verifier = source("scripts/verify-base44-functions.sh");
  const recovery = source("scripts/recover-base44-unrouted-functions.sh");

  assert.match(verifier, /PROBE_ORIGIN="\$\{BASE44_FUNCTION_ORIGIN:-https:\/\/base44\.app\}"/);
  assert.match(recovery, /PROBE_ORIGIN="\$\{BASE44_FUNCTION_ORIGIN:-https:\/\/base44\.app\}"/);
  assert.match(verifier, /\/api\/apps\/\$APP_ID\/functions\/\$name/);
  assert.match(verifier, /"\$status" == "405"/);
  assert.match(verifier, /"\$actual" == "\$expected"/);
  assert.match(verifier, /FUNCTION_BUILD_MISMATCH/);
  assert.match(verifier, /BASE44_FUNCTIONS_SOURCE_VERIFIED/);
});
