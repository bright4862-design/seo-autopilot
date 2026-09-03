// Release integrity for the durable Standard 150 worker.
//
// Covers package integrity, the single deterministic auth route, truthful
// failure codes, and the private-worker deployment contract. The manifest
// helpers are imported and executed rather than string-matched.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import {
  auditAll,
  buildManifest,
  compareReleaseDirectories,
  RELEASE_ENTITIES,
  RELEASE_FUNCTIONS,
} from "../../scripts/base44_release_manifest.mjs";

const TASKS = "base44/functions/startStandardScanJob/cloudTasks.js";
const WORKER_BUILD = "cloudbuild.durable-worker.yaml";
const WORKER_SRC = "scanner-api/app/main.py";

const tasksSource = fs.readFileSync(TASKS, "utf8");
const workerBuild = fs.readFileSync(WORKER_BUILD, "utf8");
const workerDockerfile = fs.readFileSync("Dockerfile", "utf8");
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

test("every customer-release function package is portable, closed, pinned and symlink-free", () => {
  const problems = auditAll().flatMap((r) => r.problems);
  assert.deepEqual(problems, [], problems.join("\n"));
  assert.deepEqual(RELEASE_FUNCTIONS, [
    "startStandardScanJobV2",
    "durableScanWorkerControlV2",
    "persistDurableScanAuthorityV2",
    // A limited result gets its own package rather than a provisional branch
    // inside the authority function: there is no authority seal in it to weaken.
    "persistLimitedScanResultV2",
    "getCustomerScanResultV2",
    "deleteCustomerScanDataV2",
    "createAccessCheckout",
    "stripeWebhook",
    "ownerScanDebugControl",
  ]);
});

test("missing key and malformed key produce distinct failure codes", () => {
  assert.match(tasksCode, /failureCode: "tasks_credentials_not_configured"/);
  assert.match(tasksCode, /failureCode: "tasks_token_mint_failed"/);

  // The missing-key branch must be the one guarded by an absent key, and the
  // mint branch must not reuse the missing-key code.
  const fn = tasksCode.match(/async function accessToken\(\)[\s\S]*?\n\}/)?.[0] || "";
  assert.ok(fn, "accessToken() not found");
  assert.match(fn, /if \(!key\) return \{ token: "", failureCode: "tasks_credentials_not_configured" \}/);
  // The catch may bind the error to inspect its code, so accept either form.
  const catchBlock = fn.match(/catch\s*(?:\([^)]*\))?\s*\{[\s\S]*?\}/)?.[0] || "";
  assert.ok(catchBlock, "accessToken() catch block not found");
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
  assert.match(preflight, /WORKER_DISPATCH_DEADLINE = "480s"/);
  assert.match(preflight, /dispatchDeadline: WORKER_DISPATCH_DEADLINE/);
  assert.match(preflight, /standard150-\$\{safeScanId\(scanId\)\}-a\$\{normalizeAttemptCount\(attemptCount\)\}/);
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
  for (const key of ["_RELEASE_SHA", "_WORKER_SERVICE", "_REGION", "_IMAGE", "_RUNTIME_SA", "_INVOKER_SA"]) {
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

test("manual builds require one explicit full release SHA for every image reference", () => {
  const preflight = fs.readFileSync("scripts/deployment_preflight.sh", "utf8");
  assert.match(workerBuild, /_RELEASE_SHA: ""/);
  assert.match(workerBuild, /"_RELEASE_SHA=\$\{_RELEASE_SHA\}"/);
  assert.match(workerBuild, /\^\[0-9a-f\]\{40\}\$/);
  assert.match(buildCode, /docker[\s\S]*\$\{_IMAGE\}:\$\{_RELEASE_SHA\}/);
  assert.doesNotMatch(buildCode, /\$COMMIT_SHA/);
  assert.match(preflight, /git rev-parse HEAD/);
  assert.match(preflight, /git status --porcelain/);
  assert.match(preflight, /checkout is dirty/);
});

test("Cloud Build proves the uploaded worker bytes match the claimed commit", () => {
  const candidateBuild = fs.readFileSync("scripts/build-worker-candidate.sh", "utf8");

  // GitHub Actions verifies the exact clean commit and submits a git archive of
  // that commit, rather than asking Cloud Build to clone the private repository.
  assert.match(candidateBuild, /git -C "\$REPO_ROOT" archive --format=tar "\$SOURCE_SHA"/);
  assert.match(candidateBuild, /\.fixlist-source-sha/);
  assert.match(candidateBuild, /gcloud builds submit "\$BUILD_CONTEXT"/);

  // Cloud Build independently binds the uploaded archive to the claimed SHA,
  // then builds only from the isolated verified context.
  assert.match(workerBuild, /id: verify-release-source/);
  assert.match(workerBuild, /readonly stamp=\/workspace\/\.fixlist-source-sha/);
  assert.match(workerBuild, /actual_sha=.*tr -d/);
  assert.match(workerBuild, /archive stamp \$actual_sha, expected \$\{_RELEASE_SHA\}/);
  assert.match(workerBuild, /scanner-api\/requirements\.txt/);
  assert.match(workerBuild, /scanner-api\/app/);
  assert.match(workerBuild, /cp -a \/workspace\/scanner-api\/app/);
  assert.match(workerBuild, /sha256sum "\$verified_context\/scanner-api\/app\/main\.py"/);
  assert.doesNotMatch(workerBuild, /https:\/\/github\.com\/bright4862-design\/seo-autopilot\.git/);
  assert.doesNotMatch(buildCode, /git[^\n]*fetch/);
  assert.match(
    buildCode,
    /docker[\s\S]*\/workspace\/\.verified-context/,
    "the image must be built from the exact archived commit context",
  );
  assert.doesNotMatch(
    buildCode,
    /args:\s*\["build",\s*"--tag",[^\n]*,\s*"\."\]/,
    "the uploaded workspace root must not remain the Docker build source",
  );
});

test("the durable worker image contains the cross-runtime fingerprint input at its runtime path", () => {
  const modulePath = "/app/app/beta_revision.py";
  const repoRoot = path.posix.dirname(
    path.posix.dirname(path.posix.dirname(modulePath)),
  );
  const runtimeInput = path.posix.join(
    repoRoot,
    "data/cross-runtime-release-components.json",
  );

  // beta_revision.py resolves parents[2] from /app/app/beta_revision.py, so
  // the file belongs at /data. COPY data ./data would silently put it at
  // /app/data and every /health, /revision, and /scan-job fingerprint lookup
  // would fail at request time.
  assert.equal(runtimeInput, "/data/cross-runtime-release-components.json");
  assert.match(
    workerBuild,
    /data\/cross-runtime-release-components\.json/,
    "the exact release-components file must be a verified build input",
  );
  assert.match(
    workerBuild,
    /cp .*\/workspace\/data\/cross-runtime-release-components\.json .*\$verified_context\/data\/cross-runtime-release-components\.json/,
    "the verified Docker context must include the release-components file",
  );
  assert.match(
    workerDockerfile,
    /^COPY data\/cross-runtime-release-components\.json \/data\/cross-runtime-release-components\.json$/m,
    "the image must place the file at /data, not beneath WORKDIR /app",
  );
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
  const { functions, entities, entityDigest } = buildManifest();
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
  assert.deepEqual(RELEASE_ENTITIES, ["ScanRun", "FixList", "FixItem"]);
  assert.match(entityDigest, /^[a-f0-9]{64}$/);
  for (const entityName of RELEASE_ENTITIES) {
    const metadata = entities[entityName];
    assert.equal(metadata.file, `${entityName}.jsonc`);
    assert.match(metadata.sha256, /^[a-f0-9]{64}$/);
    assert.equal(metadata.bytes, fs.statSync(`base44/entities/${entityName}.jsonc`).size);
  }
});

test("a fresh pulled Base44 inventory must match every release package and authority schema byte-for-byte", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-base44-pull-"));
  const functionsRoot = path.join(root, "functions");
  const entitiesRoot = path.join(root, "entities");
  try {
    fs.mkdirSync(functionsRoot);
    fs.mkdirSync(entitiesRoot);
    for (const fnName of RELEASE_FUNCTIONS) {
      fs.cpSync(`base44/functions/${fnName}`, path.join(functionsRoot, fnName), { recursive: true });
    }
    for (const entityName of RELEASE_ENTITIES) {
      fs.copyFileSync(
        `base44/entities/${entityName}.jsonc`,
        path.join(entitiesRoot, `${entityName}.jsonc`),
      );
    }
    assert.equal(compareReleaseDirectories(functionsRoot, entitiesRoot).ok, true);

    fs.appendFileSync(path.join(functionsRoot, "getCustomerScanResultV2", "projection.js"), "\n// drift\n");
    const drifted = compareReleaseDirectories(functionsRoot, entitiesRoot);
    assert.equal(drifted.ok, false);
    assert.ok(drifted.problems.some((problem) => problem.includes("getCustomerScanResultV2")));
    fs.copyFileSync(
      "base44/functions/getCustomerScanResultV2/projection.js",
      path.join(functionsRoot, "getCustomerScanResultV2", "projection.js"),
    );

    fs.appendFileSync(path.join(entitiesRoot, "ScanRun.jsonc"), "\n// drift\n");
    const entityDrift = compareReleaseDirectories(functionsRoot, entitiesRoot);
    assert.equal(entityDrift.ok, false);
    assert.ok(entityDrift.problems.some((problem) => problem.includes("ScanRun: deployed entity digest")));
    fs.copyFileSync("base44/entities/ScanRun.jsonc", path.join(entitiesRoot, "ScanRun.jsonc"));

    fs.rmSync(path.join(functionsRoot, "stripeWebhook"), { recursive: true });
    const missing = compareReleaseDirectories(functionsRoot, entitiesRoot);
    assert.equal(missing.ok, false);
    assert.ok(missing.problems.some((problem) => problem.includes("stripeWebhook: missing")));

    fs.cpSync("base44/functions/stripeWebhook", path.join(functionsRoot, "stripeWebhook"), { recursive: true });
    fs.rmSync(path.join(entitiesRoot, "FixItem.jsonc"));
    const missingEntity = compareReleaseDirectories(functionsRoot, entitiesRoot);
    assert.equal(missingEntity.ok, false);
    assert.ok(missingEntity.problems.some((problem) => problem.includes("FixItem: entity schema missing")));
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
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

  // Exactly one secret reference, pinned to a substituted numeric version.
  // ":latest" is prohibited: it re-resolves at instance start, so a new secret
  // version would change what an already-verified revision reads.
  const refs = (secretLine.match(/[A-Z0-9_]+=\$\{_[A-Z0-9_]+\}:\$\{_[A-Z0-9_]+\}/g) || []);
  assert.equal(refs.length, 1, `expected exactly 1 pinned secret reference, found ${refs.length}: ${refs}`);
});

test("the signing key is pinned to a numeric version across build, preflight, contract and verifier", () => {
  const workerBuild = fs.readFileSync("cloudbuild.durable-worker.yaml", "utf8");
  const preflight = fs.readFileSync("scripts/deployment_preflight.sh", "utf8");
  const verify = fs.readFileSync("scripts/post_deploy_verify.sh", "utf8");
  const contract = fs.readFileSync("docs/standard150-deployment-contract.md", "utf8");

  // 1. Build artifact: required, fail-closed, guarded, and bound to both substitutions.
  assert.match(workerBuild, /_SIGNING_KEY_VERSION: ""/, "_SIGNING_KEY_VERSION must fail closed");
  assert.match(workerBuild, /"_SIGNING_KEY_VERSION=\$\{_SIGNING_KEY_VERSION\}"/,
    "_SIGNING_KEY_VERSION must be covered by the missing-substitution guard");
  assert.match(workerBuild,
    /--set-secrets=SCAN_EVIDENCE_SIGNING_KEY=\$\{_SIGNING_KEY_SECRET\}:\$\{_SIGNING_KEY_VERSION\}/,
    "the signing secret must bind both the name and the version substitution");
  // Production version numbers are never hardcoded in source.
  assert.doesNotMatch(workerBuild, /_SIGNING_KEY_VERSION:\s*"\d/,
    "no production signing-key version may be hardcoded in source");

  // 2. The executable deployment artifact must contain no ":latest".
  //    Comments may explain why it is prohibited. The preflight and verifier
  //    legitimately contain the token as the pattern they REJECT, so the
  //    prohibition applies to what is actually deployed.
  const executable = (text) =>
    text.split("\n").filter((l) => !/^\s*#/.test(l)).join("\n");
  assert.ok(!executable(workerBuild).includes(":latest"),
    'cloudbuild.durable-worker.yaml must not contain an executable ":latest"');
  assert.match(preflight, /executable ':latest' in the build artifact/,
    "preflight must actively reject an executable ':latest'");

  // 3. Preflight requires the version, validates it is numeric, rejects latest.
  assert.match(preflight, /SIGNING_KEY_VERSION/, "preflight must require SIGNING_KEY_VERSION");
  assert.match(preflight, /is not numeric/, "preflight must reject a non-numeric version");
  assert.match(preflight, /latest\|LATEST/, "preflight must reject 'latest'");

  // 4. Post-deploy verifier requires both expectations and matches them exactly.
  assert.match(verify, /EXPECTED_SIGNING_SECRET/, "verifier must require EXPECTED_SIGNING_SECRET");
  assert.match(verify, /EXPECTED_SIGNING_VERSION/, "verifier must require EXPECTED_SIGNING_VERSION");
  assert.match(verify, /secretKeyRef/, "verifier must read the secret reference, not just count refs");
  assert.match(verify, /PLAINTEXT/, "verifier must fail closed on a plaintext signing key");
  assert.match(verify, /MALFORMED/, "verifier must fail closed on a malformed reference");
  assert.ok(!verify.includes("versions access"), "verifier must never access a secret payload");

  // 5. Contract documents the requirement and the prohibition.
  assert.match(contract, /_SIGNING_KEY_VERSION/, "contract must list _SIGNING_KEY_VERSION as an input");
  assert.match(contract, /numeric, \*\*ENABLED\*\*|numeric, ENABLED|\*\*numeric, ENABLED\*\*/,
    "contract must require a numeric ENABLED version");
  assert.match(contract, /`latest` is prohibited/, "contract must prohibit latest");
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

test("post-deploy verification fails closed without a fresh Base44 package pull", () => {
  const verify = fs.readFileSync("scripts/post_deploy_verify.sh", "utf8");
  assert.match(verify, /BASE44_PULLED_FUNCTIONS_DIR/);
  assert.match(verify, /BASE44_PULLED_ENTITIES_DIR/);
  assert.match(verify, /base44_release_manifest\.mjs compare/);
  assert.doesNotMatch(verify, /Base44 function presence \(manual\)/);
  assert.doesNotMatch(verify, /no read-only CLI check exists/);
});

function runPostDeployVerifier(policyMode) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "durable-release-verify-"));
  const gcloudPath = path.join(tempDir, "gcloud");
  const describePath = path.join(tempDir, "describe.json");
  const pulledFunctions = path.join(tempDir, "base44-functions");
  const pulledEntities = path.join(tempDir, "base44-entities");
  fs.mkdirSync(pulledFunctions);
  fs.mkdirSync(pulledEntities);
  for (const fnName of RELEASE_FUNCTIONS) {
    fs.cpSync(`base44/functions/${fnName}`, path.join(pulledFunctions, fnName), { recursive: true });
  }
  for (const entityName of RELEASE_ENTITIES) {
    fs.copyFileSync(`base44/entities/${entityName}.jsonc`, path.join(pulledEntities, `${entityName}.jsonc`));
  }
  const image = `europe-west1-docker.pkg.dev/test/repo/worker:${"a".repeat(40)}`;
  const runtimeSa = "runtime@test.iam.gserviceaccount.com";
  const invokerSa = "invoker@test.iam.gserviceaccount.com";
  const describe = {
    status: { latestReadyRevisionName: "worker-00001", url: "" },
    spec: { template: { spec: {
      serviceAccountName: runtimeSa,
      timeoutSeconds: 480,
      containerConcurrency: 1,
      containers: [{
        image,
        env: [
          { name: "BASE44_APP_ID", value: "test-app" },
          { name: "TASKS_INVOKER_SERVICE_ACCOUNT", value: invokerSa },
          { name: "GROK_PROXY_ENABLED", value: "false" },
          { name: "FIXLIST_WORKER_SOURCE_SHA", value: "a".repeat(40) },
          { name: "SCAN_EVIDENCE_SIGNING_KEY", valueFrom: {
            secretKeyRef: { name: "SCAN_EVIDENCE_SIGNING_KEY", key: "1" },
          } },
        ],
      }],
    } } },
  };
  fs.writeFileSync(describePath, JSON.stringify(describe));
  const scanQueuePath = path.join(tempDir, "scan-queue.json");
  const drainQueuePath = path.join(tempDir, "drain-queue.json");
  fs.writeFileSync(scanQueuePath, JSON.stringify({
    state: "RUNNING",
    rateLimits: { maxConcurrentDispatches: 1, maxDispatchesPerSecond: 1 },
    retryConfig: { maxAttempts: 3, minBackoff: "10s", maxBackoff: "300s", maxDoublings: 3 },
  }));
  fs.writeFileSync(drainQueuePath, JSON.stringify({
    state: "RUNNING",
    rateLimits: { maxConcurrentDispatches: 5, maxDispatchesPerSecond: 5 },
    retryConfig: { maxAttempts: 100, maxRetryDuration: "14400s", minBackoff: "30s", maxBackoff: "180s", maxDoublings: 3 },
  }));
  fs.writeFileSync(gcloudPath, `#!/usr/bin/env bash
if [[ " $* " == *" tasks queues describe "* ]]; then
  if [[ " $* " == *" $DRAIN_QUEUE "* ]]; then command cat "$FAKE_DRAIN_QUEUE_PATH"; else command cat "$FAKE_SCAN_QUEUE_PATH"; fi
elif [[ " $* " == *" get-iam-policy "* ]]; then
  case "$FAKE_POLICY_MODE" in
    unreadable) exit 1 ;;
    malformed) printf '{' ;;
    missing) printf '%s' '{"bindings":[]}' ;;
    public) printf '%s' '{"bindings":[{"role":"roles/run.invoker","members":["allUsers","serviceAccount:invoker@test.iam.gserviceaccount.com"]}]}' ;;
    valid) printf '%s' '{"bindings":[{"role":"roles/run.invoker","members":["serviceAccount:invoker@test.iam.gserviceaccount.com"]}]}' ;;
    *) exit 9 ;;
  esac
else
  command cat "$FAKE_DESCRIBE_PATH"
fi
`);
  fs.chmodSync(gcloudPath, 0o755);
  const result = spawnSync("bash", ["scripts/post_deploy_verify.sh"], {
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${tempDir}:${process.env.PATH}`,
      FAKE_POLICY_MODE: policyMode,
      FAKE_DESCRIBE_PATH: describePath,
      FAKE_SCAN_QUEUE_PATH: scanQueuePath,
      FAKE_DRAIN_QUEUE_PATH: drainQueuePath,
      WORKER_SERVICE: "worker",
      REGION: "europe-west1",
      PROJECT: "test",
      EXPECTED_IMAGE: image,
      EXPECTED_RUNTIME_SA: runtimeSa,
      EXPECTED_INVOKER_SA: invokerSa,
      EXPECTED_SOURCE_SHA: "a".repeat(40),
      EXPECTED_SIGNING_SECRET: "SCAN_EVIDENCE_SIGNING_KEY",
      EXPECTED_SIGNING_VERSION: "1",
      TASKS_QUEUE: "fixlist-standard150",
      DRAIN_QUEUE: "fixlist-standard150-drain",
      EXPECTED_SCAN_QUEUE_CONCURRENCY: "1",
      BASE44_PULLED_FUNCTIONS_DIR: pulledFunctions,
      BASE44_PULLED_ENTITIES_DIR: pulledEntities,
      NODE_BIN: process.execPath,
    },
  });
  fs.rmSync(tempDir, { recursive: true, force: true });
  return { ...result, output: `${result.stdout}${result.stderr}` };
}

test("post-deploy verifier fails closed when worker IAM is unreadable or malformed", () => {
  for (const mode of ["unreadable", "malformed"]) {
    const result = runPostDeployVerifier(mode);
    assert.notEqual(result.status, 0, `${mode} IAM must not pass`);
    assert.match(result.output, /unverified|malformed/i);
  }
});

test("post-deploy verifier requires the exact private invoker binding", () => {
  for (const mode of ["missing", "public"]) {
    const result = runPostDeployVerifier(mode);
    assert.equal(result.status, 1, `${mode} IAM must be a failed release check`);
    assert.match(result.output, /FAILED/);
  }
  const valid = runPostDeployVerifier("valid");
  assert.equal(valid.status, 0, valid.output);
  assert.match(valid.output, /exact invoker holds roles\/run\.invoker/);
  assert.match(valid.output, /POST-DEPLOY VERIFICATION PASSED/);
});

test("the release path never publishes signing-key material or fingerprints", () => {
  const operator = fs.readFileSync(".github/workflows/fixlist-cloud-operator.yml", "utf8");
  const sync = fs.readFileSync("scripts/sync-base44-signing-key.sh", "utf8");

  // Actions logs persist and are readable by anyone with repo access, and
  // GitHub's masking does not cover values derived at runtime. A digest or
  // exact length of the HMAC key is a permanent oracle over it.
  assert.doesNotMatch(operator, /secret_sha256/, "must not log a signing-key digest");
  assert.doesNotMatch(operator, /secret_bytes/, "must not log the signing-key length");
  assert.doesNotMatch(operator, /sha256sum\s+"\$TMP_DIR\/key"/, "must not digest the key file");

  // The diagnostic proves reachability; it must not put plaintext on disk.
  assert.doesNotMatch(operator, /versions access[^\n]*>\s*"\$TMP_DIR\/key"/,
    "the diagnostic must not write the secret payload to the runner filesystem");

  // The key is never echoed by the sync script either.
  assert.doesNotMatch(sync, /echo[^\n]*\$\(cat "\$TMP\/signing-key"\)/,
    "the sync script must never echo the signing key");
});

test("reading and transmitting the signing key requires explicit dispatch confirmation", () => {
  const operator = fs.readFileSync(".github/workflows/fixlist-cloud-operator.yml", "utf8");
  const job = operator.split("\n  sync-base44-signing-key:")[1] || "";
  assert.ok(job, "sync-base44-signing-key job must exist");

  const gate = job.split("\n    name:")[0];
  assert.match(gate, /workflow_dispatch/, "sync must be workflow_dispatch-only");
  assert.match(gate, /inputs\.confirm == 'SYNC-SIGNING-KEY'/, "sync must require exact confirmation");
  assert.doesNotMatch(gate, /head_commit\.message/,
    "a commit message must not be able to trigger a signing-key read");
});

test("the Base44 CLI is pinned and digest-verified before it handles the signing key", () => {
  const sync = fs.readFileSync("scripts/sync-base44-signing-key.sh", "utf8");

  assert.doesNotMatch(sync, /npx\s+-y\s+base44/,
    "must not run an unverified CLI fetched at use time");
  assert.match(sync, /BASE44_CLI_VERSION="\d+\.\d+\.\d+"/, "CLI version must be pinned");
  assert.match(sync, /BASE44_CLI_SHA512/, "CLI tarball digest must be checked");
  assert.match(sync, /openssl dgst -sha512/, "digest must actually be computed");
  assert.match(sync, /integrity mismatch/, "a digest mismatch must abort");

  // The pinned value must be present, not left for an operator to supply at
  // run time, or the fail-closed check is one forgotten env var from blocking
  // the release for a reason unrelated to supply-chain safety.
  assert.match(sync, /BASE44_CLI_SHA512:-sha512-[A-Za-z0-9+/=]{40,}/,
    "the verified registry digest must be pinned in source");

  // openssl emits bare base64; npm publishes "sha512-<base64>". Comparing the
  // two forms directly would never match, so a correctly pinned value would
  // abort every run and look exactly like a real integrity failure.
  assert.match(sync, /GOT_SHA512="sha512-\$\(openssl dgst -sha512/,
    "the computed digest must be normalized to npm SRI form");
  assert.match(sync, /EXPECTED_SHA512="sha512-\$\{EXPECTED_SHA512\}"/,
    "a bare base64 pin must be normalized rather than rejected");
  assert.match(sync, /\[ "\$GOT_SHA512" != "\$EXPECTED_SHA512" \]/,
    "comparison must use the normalized values on both sides");

  // Login must precede the secret read, so the plaintext window never spans an
  // unbounded wait for a human to approve a device code.
  const loginAt = sync.indexOf('"$CLI" login');
  const readAt = sync.indexOf("gcloud secrets versions access");
  assert.ok(loginAt > 0 && readAt > 0, "both steps must be present");
  assert.ok(loginAt < readAt,
    "Base44 login must happen before the signing key is read from Secret Manager");
});

// The Base44 leg of admission signs with SCAN_EVIDENCE_SIGNING_KEY, and Base44
// receives that key through an env file. Cloud Run hands the worker and the
// coordinator the secret payload verbatim, trailing newline included, but
// `KEY=<payload>\n` and `KEY=<payload>` parse to the same string, so an env file
// cannot carry one. A payload with surrounding whitespace therefore gives Base44
// a different signing root than Cloud Run holds; every admission call 401s with
// invalid_signature while the sync still prints KEY_SYNC_COMPLETE over the top.
test("the signing-key sync refuses a payload the env file cannot carry", () => {
  const sync = fs.readFileSync("scripts/sync-base44-signing-key.sh", "utf8");

  const guard = sync.match(
    /echo "\[6\/8\] Verifying the secret can survive the env-file round trip\.\.\."[\s\S]*?\nfi\n/,
  );
  assert.ok(guard, "the env-file round-trip guard is missing from the sync script");

  // A guard that runs after the env file is written would not stop the bad
  // value being sent, so ordering is part of the contract.
  assert.ok(
    sync.indexOf(guard[0]) < sync.indexOf('} > "$TMP/base44.env"'),
    "the round-trip guard must run before the env file is written",
  );

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-key-shape-"));
  const check = (bytes) => {
    fs.writeFileSync(path.join(dir, "signing-key"), bytes);
    return spawnSync(
      "bash",
      [
        "-c",
        `set -euo pipefail\nTMP="${dir}"\nSIGNING_SECRET=SCAN_EVIDENCE_SIGNING_KEY\nPROJECT=p\nWORKER=w\n${guard[0]}`,
      ],
      { encoding: "utf8" },
    );
  };

  const clean = check("0123456789abcdef");
  assert.equal(clean.status, 0, `a whitespace-free payload must pass: ${clean.stderr}`);

  for (const [label, bytes] of [
    ["a trailing newline", "0123456789abcdef\n"],
    ["a leading space", " 0123456789abcdef"],
    ["trailing whitespace", "0123456789abcdef \t"],
  ]) {
    const rejected = check(bytes);
    assert.equal(rejected.status, 1, `${label} must fail the sync closed`);
    assert.match(rejected.stderr, /surrounding whitespace/, `${label} must say why`);
    // The operator has to be told the repair spans all three consumers, or
    // repointing one of them silently splits the signing root instead.
    assert.match(rejected.stderr, /versions add/, `${label} must name the repair`);

    // Diagnosing a secret must never print it.
    const output = `${rejected.stdout}${rejected.stderr}`;
    assert.doesNotMatch(output, /0123456789abcdef/, `${label} must not echo the payload`);
  }

  fs.rmSync(dir, { recursive: true, force: true });
});
