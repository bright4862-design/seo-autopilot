import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const workflow = readFileSync(".github/workflows/fixlist-cloud-operator.yml", "utf8");
const operator = readFileSync("scripts/fixlist-cloud-operator.sh", "utf8");

function jobBlock() {
  const start = workflow.indexOf("  incident378-serving-revision-readonly:\n");
  assert.ok(start > 0, "the owner-only incident job must exist");
  const next = workflow.indexOf("\n  sync-base44-signing-key:\n", start);
  assert.ok(next > start, "the incident job must end before the existing signing-key job");
  return workflow.slice(start, next);
}

test("incident 378 can only be triggered by a signed-in owner comment on that exact issue", () => {
  const job = jobBlock();
  assert.match(job, /github\.event_name == 'issue_comment'/);
  assert.match(job, /github\.event\.issue\.number == 378/);
  assert.match(job, /github\.event\.issue\.pull_request == null/);
  assert.match(job, /github\.event\.comment\.user\.login == 'bright4862-design'/);
  assert.match(job, /startsWith\(github\.event\.comment\.body, '\/fixlist-readonly-incident-378 '\)/);
  assert.match(job, /test "\$COMMENT_BODY" = "\/fixlist-readonly-incident-378 \$GITHUB_SHA"/);
  assert.match(job, /test "\$GITHUB_REF" = "refs\/heads\/main"/);
  assert.match(job, /test "\$COMMENT_AUTHOR" = "bright4862-design"/);
  assert.match(job, /test "\$\(git rev-parse HEAD\)" = "\$GITHUB_SHA"/);
  assert.match(job, /permissions:\n\s+contents: read\n\s+id-token: write\n\s+issues: write/);
  assert.match(job, /persist-credentials: false/);
});

test("the read-only probe authenticates the PRIVATE worker with its own canonical-audience OIDC token", () => {
  const job = jobBlock();
  assert.match(job, /google-github-actions\/auth@v3/);
  assert.match(job, /service_account: \$\{\{ env\.GCP_OPERATOR_SERVICE_ACCOUNT \}\}/);
  assert.match(job, /id_token_audience: \$\{\{ steps\.canonical-url\.outputs\.url \}\}/);
  assert.match(job, /create_credentials_file: false/);
  assert.match(job, /token_format: id_token/);
  assert.match(job, /OPERATION: verify-worker-runtime-revision/);
  assert.match(job, /TARGET_REVISION: ""/);
  assert.match(job, /SOURCE_SHA: \$\{\{ github\.sha \}\}/);
  assert.match(job, /FIXLIST_WORKER_TOKEN_AUDIENCE: \$\{\{ steps\.canonical-url\.outputs\.url \}\}/);
  assert.match(job, /FIXLIST_WORKER_ID_TOKEN: \$\{\{ steps\.worker-token\.outputs\.id_token \}\}/);
  assert.match(operator, /verify_worker_runtime_revision\(\)/);
  assert.match(operator, /live_components != recorded_components/);
  assert.match(operator, /live_fingerprint != recorded_fingerprint/);
});

test("no scanner, queue, barrier, persistence, source release or traffic writes are reachable from diagnostic", () => {
  const job = jobBlock();
  for (const bad of [
    /gcloud run deploy/i, /gcloud run services update-traffic/i,
    /gcloud tasks queues (?:pause|resume|create)/i, /gcloud builds submit/i,
    /gcloud secrets/i, /update-traffic/i, /set-tags/i, /scanner-api\/app\/scan_job/i,
    /base44 deploy/i, /git push/i, /curl .*(?:POST|PATCH|PUT|DELETE)/i,
    /BETA_SCAN_ADMISSION_ENABLED/, /SCAN_EVIDENCE_SIGNING_KEY/,
    /FIXLIST_EXTENDED500/,
  ]) assert.doesNotMatch(job, bad);
  assert.match(job, /gh issue comment 378 --repo "\$GITHUB_REPOSITORY" --body-file "\$report"/);
  assert.match(job, /grep -E '\^\(revision under test:/);
  assert.match(job, /test "\$EXIT_CODE" = "0"/);
  assert.doesNotMatch(job, /echo .*FIXLIST_WORKER_ID_TOKEN/);
  assert.doesNotMatch(job, /(?:\$\{\{ steps\.worker-token\.outputs\.id_token \}\}).*(?:issue comment|report)/);
});
