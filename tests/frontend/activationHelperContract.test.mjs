import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { spawnSync } from "node:child_process";

const PATH = "scripts/activate-standard150-beta-once.sh";
const source = fs.readFileSync(PATH, "utf8");

test("activation helper is valid bash", () => {
  const result = spawnSync("bash", ["-n", PATH], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
});

test("helper is pinned to the exact merged candidate and fingerprint", () => {
  assert.match(source, /EXPECTED_RELEASE_SHA="499d6479225d980ee95d60ef9df4118d726823d5"/);
  assert.match(source, /EXPECTED_FINGERPRINT="5caec7fdcabceee7"/);
  assert.match(source, /origin\/main moved.*refusing to deploy a stale release/);
});

test("candidate is built no-traffic before the explicit candidate promotion", () => {
  assert.match(source, /cloudbuild\.durable-worker\.yaml/);
  assert.match(source, /candidate_traffic=0%%/);
  assert.match(source, /post_deploy_verify\.sh/);
  const buildAt = source.indexOf("gcloud builds submit");
  const promotionMarkerAt = source.indexOf('say "6/7 PROMOTE EXACT CANDIDATE');
  const exactPromotionAt = source.indexOf('--to-revisions="${CANDIDATE_REVISION}=100"', promotionMarkerAt);
  assert.ok(buildAt >= 0, "Cloud Build submission must exist");
  assert.ok(promotionMarkerAt > buildAt, "candidate promotion phase must come after the build");
  assert.ok(exactPromotionAt > promotionMarkerAt, "the exact candidate promotion must occur inside the promotion phase");
});

test("Base44 receives only JS TS durable functions and the site from GitHub", () => {
  assert.match(source, /functions deploy[\s\\\n]+startStandardScanJob durableScanWorkerControl persistDurableScanAuthority/);
  assert.match(source, /deploy --site-only/);
  assert.doesNotMatch(source, /base44[^\n]*\.py\b/i);
  assert.doesNotMatch(source, /functions deploy[^\n]*(runPythonScanner|scanner-api)/);
});

test("Base44 CLI is independently digest verified before source deploy", () => {
  assert.match(source, /BASE44_CLI_VERSION="0\.1\.9"/);
  assert.match(source, /BASE44_CLI_SRI="sha512-[A-Za-z0-9+/=]+"/);
  assert.match(source, /openssl dgst -sha512/);
  assert.match(source, /GOT_SRI.*BASE44_CLI_SRI/);
});

test("promotion requires an empty queue and has automatic recovery", () => {
  const queueLists = source.match(/gcloud tasks list/g) || [];
  assert.ok(queueLists.length >= 3, "queue must be checked before build, before promotion, and after activation");
  assert.match(source, /QUEUE_PAUSED_BY_US=1/);
  assert.match(source, /attempting rollback to \$OLD_REVISION/);
  assert.match(source, /Restoring Standard 150 queue to RUNNING/);
  assert.match(source, /to-revisions="\$\{OLD_REVISION\}=100"/);
  assert.match(source, /to-revisions="\$\{CANDIDATE_REVISION\}=100"/);
});

test("helper never POSTs a scan or enables deferred features", () => {
  const curlCommands = source.split("\n").filter((line) => /\bcurl\b/.test(line));
  for (const line of curlCommands) {
    assert.doesNotMatch(line, /(?:-X|--request)\s*POST/i, `activation helper must never POST with curl: ${line}`);
  }
  assert.doesNotMatch(source, /GROK_PROXY_ENABLED=true|GROK_CHAT_ENABLED=true|premium_5000/i);
  assert.match(source, /No customer scan was started/);
});
