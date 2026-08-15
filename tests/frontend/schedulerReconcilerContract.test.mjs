import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
