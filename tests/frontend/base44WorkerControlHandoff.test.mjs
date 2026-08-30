import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(path, "utf8");

test("Base44 worker handoff is edge-compatible and observable without sensitive data", () => {
  const worker = read("scanner-api/app/scan_job.py");

  assert.match(worker, /BASE44_WORKER_USER_AGENT/);
  assert.match(worker, /Mozilla\/5\.0/);
  assert.match(worker, /FixListStandard150Worker\/1\.0/);
  assert.match(worker, /"User-Agent": BASE44_WORKER_USER_AGENT/);

  for (const safeField of [
    "function=name",
    "response_status=int(response.status_code)",
    "content_type=content_type",
    "base44_request_id=base44_request_id",
    "cloudflare_ray_id=cloudflare_ray_id",
    "transport_error_class=type(error).__name__",
  ]) {
    assert.ok(worker.includes(safeField), `missing safe handoff field: ${safeField}`);
  }

  const emitBlocks = [...worker.matchAll(/emit\(\s*"base44_function_handoff"[\s\S]*?\n\s*\)/g)]
    .map((match) => match[0])
    .join("\n");
  assert.doesNotMatch(emitBlocks, /proof|signing_key|payload|request_body|customer_data|scan_id/);
});

test("Base44 release requires a live durable-control route, not inventory alone", () => {
  const siteDeploy = read("scripts/deploy-base44-beta-site.sh");
  const functionDeploy = read("scripts/deploy-base44-beta-functions.sh");
  const routeProbe = read("scripts/verify-base44-worker-control-route.sh");

  assert.match(siteDeploy, /verify-base44-worker-control-route\.sh/);
  assert.match(functionDeploy, /verify-base44-worker-control-route\.sh/);
  assert.match(routeProbe, /durableScanWorkerControl/);
  assert.match(routeProbe, /X-FixList-Worker: invalid_route_probe/);
  assert.match(routeProbe, /User-Agent: \$WORKER_USER_AGENT/);
  assert.match(routeProbe, /worker_header_invalid/);
  assert.match(routeProbe, /code" != "403"/);
  assert.doesNotMatch(routeProbe, /SCAN_EVIDENCE_SIGNING_KEY|secrets versions access/);
});

test("worker promotion is blocked until a signed read-only Base44 control call executes", () => {
  const workflow = read(".github/workflows/fixlist-cloud-operator.yml");
  const probe = read("scripts/verify-base44-worker-control.py");

  const publicRelease = workflow.indexOf("Verify matching Base44 product release is public");
  const signedHandoff = workflow.indexOf("Verify signed Base44 worker-control handoff");
  const promote = workflow.indexOf("Promote exact candidate with automatic rollback on failed post-check");

  assert.ok(publicRelease >= 0);
  assert.ok(signedHandoff > publicRelease);
  assert.ok(promote > signedHandoff);

  assert.match(workflow, /gcloud secrets versions access "\$secret_version"/);
  assert.match(workflow, /verify-base44-worker-control\.py/);
  assert.match(workflow, /chmod 600 "\$secret_file"/);

  assert.match(probe, /action": "read"/);
  assert.match(probe, /fixlist_preflight_missing_scan_v1/);
  assert.match(probe, /worker_record_not_found/);
  assert.match(probe, /status != 404/);
  assert.match(probe, /FixListStandard150Worker\/1\.0/);

  // The verification output may expose only response metadata. Never the HMAC,
  // secret contents, or the signed request body.
  assert.doesNotMatch(probe, /print\([^\n]*(proof|secret|payload)/);
});
