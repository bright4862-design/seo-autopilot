// Release integrity for the durable Standard 150 worker.
//
// Covers package integrity, the single deterministic auth route, truthful
// failure codes, and the private-worker deployment contract. The manifest
// helpers are imported and executed rather than string-matched.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { auditAll, buildManifest, RELEASE_FUNCTIONS } from "../../scripts/base44_release_manifest.mjs";

const TASKS = "base44/functions/startStandardScanJob/cloudTasks.js";
const WORKER_BUILD = "cloudbuild.durable-worker.yaml";
const WORKER_SRC = "scanner-api/app/main.py";

const tasksSource = fs.readFileSync(TASKS, "utf8");
const workerBuild = fs.readFileSync(WORKER_BUILD, "utf8");
const workerSrc = fs.readFileSync(WORKER_SRC, "utf8");

// Comment-stripped view: documentation may name a thing precisely to forbid it.
const tasksCode = tasksSource.split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");
const buildCode = workerBuild.split("\n").filter((l) => !/^\s*#/.test(l)).join("\n");

test("gcpAuth.js is imported statically, never dynamically", () => {
  assert.match(tasksCode, /^import \{ createServiceAccountAccessToken \} from "\.\/gcpAuth\.js";$/m);
  assert.doesNotMatch(tasksCode, /await import\(/);
  assert.doesNotMatch(tasksCode, /\bimport\s*\(\s*["']\./);
});

test("no release function contains a local dynamic import", () => {
  for (const result of auditAll()) {
    const dynamic = result.problems.filter((p) => p.includes("dynamic import"));
    assert.deepEqual(dynamic, [], `${result.fnName}: ${dynamic.join("; ")}`);
  }
});

test("all three release packages are portable, closed, pinned and symlink-free", () => {
  const problems = auditAll().flatMap((r) => r.problems);
  assert.deepEqual(problems, [], problems.join("\n"));
  assert.equal(RELEASE_FUNCTIONS.length, 3);
});

test("missing key and malformed key produce distinct failure codes", () => {
  assert.match(tasksCode, /failureCode: "tasks_credentials_not_configured"/);
  assert.match(tasksCode, /failureCode: "tasks_token_mint_failed"/);

  // The missing-key branch must be the one guarded by an absent key, and the
  // mint branch must not reuse the missing-key code.
  const fn = tasksCode.match(/async function accessToken\(\)[\s\S]*?\n\}/)?.[0] || "";
  assert.ok(fn, "accessToken() not found");
  assert.match(fn, /if \(!key\) return \{ token: "", failureCode: "tasks_credentials_not_configured" \}/);
  const catchBlock = fn.match(/catch \{[\s\S]*?\}/)?.[0] || "";
  assert.match(catchBlock, /tasks_token_mint_failed/);
  assert.doesNotMatch(catchBlock, /tasks_credentials_not_configured/);
});

test("there is one deterministic auth route and no direct-token fallback", () => {
  assert.doesNotMatch(tasksCode, /GCP_ACCESS_TOKEN/);
  assert.match(tasksCode, /GCP_SERVICE_ACCOUNT_KEY/);
});

test("Cloud Tasks HTTP failures keep distinct status-derived codes", () => {
  assert.match(tasksCode, /failureCode: `tasks_http_\$\{response\.status\}`/);
  // Never leak an upstream body or credential into the failure surface.
  assert.doesNotMatch(tasksCode, /failureCode:[^;\n]*await response\.text\(\)/);
  assert.doesNotMatch(tasksCode, /failureCode:[^;\n]*\bkey\b/);
});

test("the worker deployment artifact requires a private service", () => {
  assert.match(buildCode, /--no-allow-unauthenticated/);
  assert.match(buildCode, /--service-account=\$\{_RUNTIME_SA\}/);
  assert.match(buildCode, /--timeout=300/);
  assert.match(buildCode, /--concurrency=1/);
  assert.match(buildCode, /--no-traffic/);
  assert.match(buildCode, /GROK_CHAT_ENABLED=false/);
});

test("the worker artifact does not target or mutate the existing scanner deployment", () => {
  const existing = fs.readFileSync("cloudbuild.yaml", "utf8").match(/seo-autopilot-\d+/)?.[0];
  assert.ok(existing, "could not identify the existing scanner service");
  assert.ok(
    !buildCode.includes(existing),
    `worker artifact references the existing scanner service ${existing}`,
  );
  // The service name must be a required parameter, not a literal.
  assert.match(buildCode, /_WORKER_SERVICE: ""/);
  assert.match(workerBuild, /Refusing to build/);
});

test("no deployment value is invented", () => {
  for (const key of ["_WORKER_SERVICE", "_REGION", "_IMAGE", "_RUNTIME_SA", "_INVOKER_SA"]) {
    assert.match(
      workerBuild,
      new RegExp(`${key}: ""`),
      `${key} must default to empty so the build fails closed`,
    );
  }
  // No hardcoded project/region/registry literals in the executable portion.
  assert.doesNotMatch(buildCode, /europe-west1/);
  assert.doesNotMatch(buildCode, /\$PROJECT_ID\/[a-z-]+\/[a-z-]+/);
});

test("the /scan-job trust boundary is documented truthfully", () => {
  const docstring = workerSrc.match(/def require_cloud_tasks_oidc[\s\S]*?"""[\s\S]*?"""/)?.[0] || "";
  assert.ok(docstring, "require_cloud_tasks_oidc docstring not found");
  // It must not claim verification the code does not perform. Collapse
  // whitespace first: these phrases wrap across lines in the docstring.
  const flat = docstring.replace(/\s+/g, " ");
  assert.match(flat, /does NOT verify the token signature/);
  assert.match(flat, /does NOT check the `aud` claim/);
  assert.match(flat, /Cloud Run IAM/);
  // And the code genuinely does only the email comparison.
  const fn = workerSrc.match(/def require_cloud_tasks_oidc[\s\S]*?(?=\n@app|\ndef )/)?.[0] || "";
  assert.match(fn, /claims\.get\("email"\)/);
  assert.doesNotMatch(fn, /verify_oauth2_token|verify_token|jwt\.decode\([^)]*verify/);
});

test("the manifest is deterministic across consecutive runs", () => {
  const a = buildManifest();
  const b = buildManifest();
  assert.deepEqual(a, b);
  assert.equal(a.releaseDigest, b.releaseDigest);
  assert.match(a.releaseDigest, /^[a-f0-9]{64}$/);
});

test("the manifest contains no timestamps or machine-specific paths", () => {
  const json = JSON.stringify(buildManifest());
  assert.doesNotMatch(json, /\/(home|Users|tmp|var)\//);
  assert.doesNotMatch(json, /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/);
  assert.doesNotMatch(json, /"(timestamp|generatedAt|mtime|date)"/);
});

test("the manifest covers function.jsonc and the whole closed tree", () => {
  const { functions } = buildManifest();
  for (const fnName of RELEASE_FUNCTIONS) {
    const entry = functions[fnName];
    assert.ok(entry, `${fnName} missing from manifest`);
    assert.ok(entry.files["function.jsonc"], `${fnName}: function.jsonc not hashed`);
    // entry must be a portable bare filename
    assert.doesNotMatch(entry.entry, /[/\\]/, `${fnName}: entry is not a bare filename`);
    assert.ok(entry.files[entry.entry], `${fnName}: declared entry is not in the manifest`);
    // paths sorted deterministically, hashes are exact-byte sha256
    const names = Object.keys(entry.files);
    assert.deepEqual(names, [...names].sort(), `${fnName}: file paths are not sorted`);
    for (const [name, meta] of Object.entries(entry.files)) {
      assert.match(meta.sha256, /^[a-f0-9]{64}$/, `${fnName}/${name}: bad sha256`);
      assert.equal(meta.bytes, fs.statSync(`base44/functions/${fnName}/${name}`).size);
    }
  }
});
