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
  assert.match(buildCode, /--timeout=480/);
  assert.match(buildCode, /--concurrency=1/);
  assert.match(buildCode, /--no-traffic/);
  // GROK_PROXY_ENABLED, not GROK_CHAT_ENABLED: see the dedicated Grok test.
  assert.match(buildCode, /GROK_PROXY_ENABLED=false/);
});

test("preflight and post-deploy verification enforce the same 480-second envelope", () => {
  const preflight = fs.readFileSync("scripts/deployment_preflight.sh", "utf8");
  const verify = fs.readFileSync("scripts/post_deploy_verify.sh", "utf8");

  assert.match(preflight, /has "--timeout=480"/);
  assert.match(preflight, /dispatchDeadline: "480s"/);
  assert.doesNotMatch(preflight, /timeout(?:=|\s)300|dispatchDeadline[^\n]*300s/);
  assert.match(verify, /\[ "\$TO" = "480" \]/);
  assert.doesNotMatch(verify, /timeout 300s|expected 300/);
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

// ---------------------------------------------------------------------------
// Deployment contract: environment variables reachable from the durable path.
// ---------------------------------------------------------------------------

const workerMain = fs.readFileSync("scanner-api/app/main.py", "utf8");
const contractDoc = fs.readFileSync("docs/standard150-deployment-contract.md", "utf8");

// Extract one route handler body. Splitting on the decorator is reliable for
// the LAST route too; a lazy `[\s\S]*?(?=\n@app\.|\Z)` collapses to an empty
// match there, which silently passes "guard absent" assertions.
function routeHandler(path) {
  const chunks = workerMain.split(/(?=@app\.(?:get|post|put|delete)\()/);
  return chunks.find((c) => new RegExp(`^@app\\.(?:get|post|put|delete)\\("${path}"\\)`).test(c)) || "";
}

test("the worker Grok flag matches the variable the worker actually reads", () => {
  // scanner-api reads GROK_PROXY_ENABLED; GROK_CHAT_ENABLED is the Base44
  // grokChat function's variable and is a no-op on Cloud Run.
  assert.match(workerMain, /os\.getenv\("GROK_PROXY_ENABLED"/);
  assert.match(buildCode, /GROK_PROXY_ENABLED=false/);
  assert.ok(
    !buildCode.includes("GROK_CHAT_ENABLED"),
    "GROK_CHAT_ENABLED on the worker is a no-op and gives false assurance",
  );
  // And it must remain default-disabled in code.
  assert.match(workerMain, /os\.getenv\("GROK_PROXY_ENABLED", ""\)\.strip\(\)\.lower\(\) == "true"/);
});

test("every required worker variable is supplied by the deployment artifact", () => {
  // Must be on the --set-env-vars line itself. Matching anywhere in the file
  // would be satisfied by the substitution-guard step, which lists the same
  // names and would hide a variable missing from the actual deploy.
  const envLine = buildCode.split("\n").find((l) => l.includes("--set-env-vars")) || "";
  assert.ok(envLine, "--set-env-vars line not found");
  for (const v of ["BASE44_APP_ID", "BASE44_API_URL", "TASKS_INVOKER_SERVICE_ACCOUNT"]) {
    assert.match(envLine, new RegExp(`\\b${v}=`), `${v} not on the --set-env-vars line`);
  }
});

test("the signing key is the only secret the durable worker requires", () => {
  assert.match(buildCode, /--set-secrets=/);
  const envLine = buildCode.split("\n").find((l) => l.includes("--set-env-vars")) || "";
  const secretLine = buildCode.split("\n").find((l) => l.includes("--set-secrets")) || "";

  assert.ok(!envLine.includes("SCAN_EVIDENCE_SIGNING_KEY"), "signing key must not be a plaintext env var");
  assert.ok(secretLine.includes("SCAN_EVIDENCE_SIGNING_KEY"), "signing key must come from Secret Manager");
  assert.match(workerBuild, /_SIGNING_KEY_SECRET: ""/, "_SIGNING_KEY_SECRET must fail closed");

  // Exactly one secret reference. /scan-job needs no other.
  const refs = (secretLine.match(/[A-Z0-9_]+=\$\{_[A-Z0-9_]+\}:latest/g) || []);
  assert.equal(refs.length, 1, `expected exactly 1 secret reference, found ${refs.length}: ${refs}`);
});

test("SCANNER_API_KEY is not supplied to the durable worker", () => {
  // /scan-job authenticates with Cloud Run IAM + TASKS_INVOKER_SERVICE_ACCOUNT
  // and runs review in-process; it never calls require_scanner_api_key().
  assert.ok(
    !buildCode.includes("SCANNER_API_KEY"),
    "SCANNER_API_KEY must not be granted to a worker that never uses it",
  );
  assert.ok(
    !buildCode.includes("_SCANNER_KEY_SECRET"),
    "_SCANNER_KEY_SECRET must not be a required substitution",
  );
  // Proven against the source, not just the template.
  const scanJob = fs.readFileSync("scanner-api/app/scan_job.py", "utf8");
  assert.ok(!/SCANNER_API_KEY|x-scanner-key/i.test(scanJob), "scan_job.py must not use the scanner key");
  const handler = routeHandler("/scan-job");
  assert.ok(handler, "/scan-job handler not found");
  assert.match(handler, /require_cloud_tasks_oidc\(/);
  assert.ok(!handler.includes("require_scanner_api_key("), "/scan-job must not depend on the scanner key");
});

test("sibling routes keep their scanner-key guard", () => {
  // Removing the secret must not silently drop these guards.
  for (const route of ["/health/auth", "/scan", "/review", "/chat"]) {
    const handler = routeHandler(route);
    assert.ok(handler, `${route} handler not found`);
    assert.match(handler, /require_scanner_api_key\(/, `${route} lost its scanner-key guard`);
  }
  // And the guard itself must fail closed on an empty expected key.
  assert.match(workerMain, /not expected_key/);
});

test("the deployment contract documents every variable the worker reads", () => {
  const readVars = [...workerMain.matchAll(/os\.getenv\("([A-Z0-9_]+)"/g)].map((m) => m[1]);
  const jobVars = [...fs.readFileSync("scanner-api/app/scan_job.py", "utf8")
    .matchAll(/os\.getenv\("([A-Z0-9_]+)"/g)].map((m) => m[1]);
  for (const v of new Set([...readVars, ...jobVars])) {
    assert.ok(
      contractDoc.includes(v),
      `${v} is read by the worker but is absent from the deployment contract`,
    );
  }
});

test("the contract documents every variable the Base44 durable functions read", () => {
  // The dispatcher and the two service-role functions read Deno.env, not
  // os.getenv, and are supplied through Base44 rather than Cloud Build. They
  // are still part of the deployment contract.
  const seen = new Set();
  for (const fnName of RELEASE_FUNCTIONS) {
    const dir = `base44/functions/${fnName}`;
    for (const file of fs.readdirSync(dir)) {
      if (!/\.(ts|js)$/.test(file)) continue;
      const source = fs.readFileSync(`${dir}/${file}`, "utf8");
      for (const m of source.matchAll(/Deno\.env\.get\("([A-Z0-9_]+)"\)/g)) seen.add(m[1]);
    }
  }
  assert.ok(seen.size > 0, "no Deno env reads found; the scan is broken");
  for (const v of seen) {
    assert.ok(
      contractDoc.includes(v),
      `${v} is read by a Base44 durable function but is absent from the deployment contract`,
    );
  }
});

test("the post-deploy verification path is read-only", () => {
  const verify = fs.readFileSync("scripts/post_deploy_verify.sh", "utf8");
  // No mutation verbs against live infrastructure.
  for (const forbidden of [
    /gcloud run deploy/, /gcloud run services update/, /update-traffic/,
    /gcloud builds submit/, /gcloud tasks queues create/, /--to-latest/, /\bdelete\b/,
  ]) {
    assert.doesNotMatch(verify, forbidden, `post-deploy script must not mutate: ${forbidden}`);
  }
  // It must not start a scan.
  assert.doesNotMatch(verify, /-X\s*POST|--data|-d\s+['"]/);
  assert.match(verify, /describe/);
});
