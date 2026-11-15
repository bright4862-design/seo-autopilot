import assert from "node:assert/strict";
import { chmodSync, cpSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const script = "scripts/deploy-base44-beta-functions.sh";
const siteScript = "scripts/deploy-base44-beta-site.sh";
const functionVerifier = "scripts/verify-base44-functions.sh";
const routeManifest = "data/base44-function-routes.json";
const routeResolver = "scripts/lib/base44-public-routes.mjs";
const workflow = readFileSync(".github/workflows/fixlist-base44-release-publish.yml", "utf8");
const scannerFunctions = [
  "startStandardScanJobV8",
  "durableScanWorkerControlV8",
  "persistDurableScanAuthorityV8",
  "persistLimitedScanResultV8",
  "getCustomerScanResultV8",
  "deleteCustomerScanDataV8",
];

const scannerFunctionsV9 = scannerFunctions.map((name) => name.replace(/V8$/, "V9"));
const checkoutFunctions = ["createAccessCheckout", "stripeWebhook", "ownerScanDebugControl"];

function selectV9(routes) {
  routes.generation = "v9";
  routes.historical_routes.v8 = routes.routes;
  routes.routes = routes.candidate_routes.v9;
  delete routes.candidate_routes.v9;
}

function fixture({ verifierExit = 0, editRoutes = () => {}, publishSite = false, staleFunction = "" } = {}) {
  const root = mkdtempSync(join(tmpdir(), "fixlist-functions-only-"));
  mkdirSync(join(root, "scripts", "lib"), { recursive: true });
  mkdirSync(join(root, "bin"));
  mkdirSync(join(root, "data"));
  const publisher = publishSite ? siteScript : script;
  cpSync(publisher, join(root, publisher));
  cpSync(routeResolver, join(root, routeResolver));
  const routes = JSON.parse(readFileSync(routeManifest, "utf8"));
  if (routes.generation === "v9") {
    routes.generation = "v8";
    routes.candidate_routes = { ...routes.candidate_routes, v9: routes.routes };
    routes.routes = routes.historical_routes.v8;
    delete routes.historical_routes.v8;
  }
  editRoutes(routes);
  writeFileSync(join(root, routeManifest), JSON.stringify(routes));
  writeFileSync(join(root, "scripts", "generate_release_contracts.mjs"), `
if (process.argv[2] === "--build-id") process.stdout.write("a".repeat(64));
if (process.argv[2] === "--activation-id") process.stdout.write(process.argv[3] + "-test");
`);
  writeFileSync(join(root, "scripts", "base44_release_manifest.mjs"), `
import { appendFileSync } from "node:fs";
appendFileSync(process.env.TEST_MUTATIONS, process.argv.slice(2).join(" ") + "\\n");
`);
  // The production release guard is tested against accepted/candidate records in
  // Python tests; this isolated shell fixture stubs only its successful exit.
  writeFileSync(join(root, "scripts", "assert_standard150_promotion_record.py"), `import os
with open(os.environ["TEST_MUTATIONS"], "a") as out:
    out.write("release-guard-ran\\n")
`);

  writeFileSync(join(root, "scripts", "lib", "release-source-guard.sh"), `
fixlist_require_exact_main() { FIXLIST_EXACT_SOURCE_SHA="$2"; }
`);
  writeFileSync(join(root, "scripts", "lib", "base44-pinned-cli.sh"), `
fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$TEST_FAKE_CLI"; export FIXLIST_BASE44_CLI; }
fixlist_require_base44_owner() { :; }
fixlist_set_base44_release_source_sha() { printf 'set-release-source\\n' >> "$TEST_MUTATIONS"; }
`);
  if (publishSite) {
    cpSync(functionVerifier, join(root, functionVerifier));
    writeFileSync(join(root, "scripts", "verify-base44-site.sh"), `#!/usr/bin/env bash
printf 'site-verified\\n' >> "$TEST_MUTATIONS"
`);
    writeFileSync(join(root, "bin", "npm"), `#!/usr/bin/env bash
printf 'npm %s\\n' "$*" >> "$TEST_CLI_CALLS"
`, { mode: 0o755 });
    writeFileSync(join(root, "bin", "curl"), `#!/usr/bin/env bash
set -euo pipefail
while [[ "$1" != "-o" ]]; do shift; done
body="$2"
url="\${@: -1}"
[[ "$url" == 'https://fixture.invalid/api/apps/publicTestApp/functions/'* ]]
name="\${url##*/}"
activation="$name-test"
[[ "$name" != "$TEST_STALE_FUNCTION" ]] || activation=stale
printf 'probe %s\\n' "$name" >> "$TEST_CLI_CALLS"
printf '{"build_id":"${"a".repeat(64)}","runtime_activation_id":"%s"}\\n' "$activation" > "$body"
printf 405
`, { mode: 0o755 });
  } else {
    writeFileSync(join(root, functionVerifier), `#!/usr/bin/env bash
printf 'verifier-ran\\n' >> "$TEST_MUTATIONS"
exit ${verifierExit}
`);
  }
  const fakeCli = join(root, "bin", "base44");
  writeFileSync(fakeCli, `#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$TEST_CLI_CALLS"
case "$3 $4" in
  'functions deploy') shift 4; printf '%s\\n' "$@" > "$TEST_CLI_CALLS.inventory" ;;
  'functions list') cat "$TEST_CLI_CALLS.inventory" ;;
esac
`);
  chmodSync(fakeCli, 0o755);
  const calls = join(root, "cli-calls");
  const mutations = join(root, "mutations");
  const run = (scope) => spawnSync("bash", [join(root, publisher)], {
    cwd: root,
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${join(root, "bin")}:${process.env.PATH}`,
      SOURCE_SHA: "a".repeat(40),
      CONFIRM: "a".repeat(40),
      BASE44_EXPECTED_OWNER: "owner@example.com",
      BASE44_APP_ID: "publicTestApp",
      BASE44_FUNCTION_ORIGIN: "https://fixture.invalid",
      DEPLOY_SCOPE: scope,
      PROBE_ATTEMPTS: "1",
      TEST_STALE_FUNCTION: staleFunction,
      TEST_FAKE_CLI: fakeCli,
      TEST_CLI_CALLS: calls,
      TEST_MUTATIONS: mutations,
    },
  });
  return { root, calls, mutations, run };
}

function contents(path) {
  try { return readFileSync(path, "utf8"); } catch { return ""; }
}

test("scanner-functions deploys and attests exactly the six V8 scanner routes", () => {
  const f = fixture();
  try {
    const result = f.run("scanner-functions");
    assert.equal(result.status, 0, result.stderr);
    const deploy = contents(f.calls).split("\n").find((line) => line.includes(" functions deploy "));
    assert.ok(deploy, contents(f.calls));
    for (const name of scannerFunctions) assert.match(deploy, new RegExp(`(?:^| )${name}(?: |$)`));
    assert.equal(deploy.trim().split(/\s+/).slice(-scannerFunctions.length).join(" "), scannerFunctions.join(" "));
    for (const forbidden of ["createAccessCheckout", "stripeWebhook", "ownerScanDebugControl", "site", "entities"])
      assert.doesNotMatch(contents(f.calls), new RegExp(forbidden));
    assert.match(contents(f.mutations), /release-guard-ran/);
    assert.ok(contents(f.mutations).indexOf("release-guard-ran") < contents(f.mutations).indexOf("set-release-source"));
    assert.match(contents(f.mutations), /verifier-ran/);
    assert.match(result.stdout, /BASE44_RELEASE_FUNCTIONS_DEPLOYED/);
    assert.match(result.stdout, /function_count=6/);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("verifier failure returns nonzero and suppresses the deployment success marker", () => {
  const f = fixture({ verifierExit: 19 });
  try {
    const result = f.run("scanner-functions");
    assert.equal(result.status, 19);
    assert.match(contents(f.mutations), /verifier-ran/);
    assert.doesNotMatch(result.stdout, /BASE44_RELEASE_FUNCTIONS_DEPLOYED/);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("the functions-only publisher selects V9 and retains all V8 routes from the exact manifest", () => {
  const f = fixture({ editRoutes: selectV9 });
  try {
    const result = f.run("scanner-functions");
    assert.equal(result.status, 0, result.stderr);
    const deploy = contents(f.calls).split("\n").find((line) => line.includes(" functions deploy "));
    const expected = [...scannerFunctionsV9, ...scannerFunctions];
    assert.deepEqual(deploy.trim().split(/\s+/).slice(4), expected);
    assert.match(contents(f.mutations), /verify --staged/);
    assert.match(result.stdout, /function_count=12/);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("site publisher deploys and probes exact V9 and retained V8 both before and after site publish", (t) => {
  const f = fixture({ editRoutes: selectV9, publishSite: true });
  t.after(() => rmSync(f.root, { recursive: true, force: true }));
  const result = f.run("site-and-functions");
  assert.equal(result.status, 0, result.stderr);
  const expected = [...scannerFunctionsV9, ...scannerFunctions];
  const cli = "--app-id publicTestApp";
  const probes = expected.map((name) => `probe ${name}`);
  assert.deepEqual(contents(f.calls).trim().split("\n"), [
    `${cli} functions deploy ${expected.join(" ")}`,
    ...probes,
    "npm run build",
    `${cli} site deploy --no-build --yes`,
    `${cli} functions deploy ${[...expected, ...checkoutFunctions].join(" ")}`,
    `${cli} functions list`,
    ...probes,
  ]);
  assert.match(contents(f.mutations), /verify --staged/);
  assert.match(contents(f.mutations), /site-verified/);
  assert.match(result.stdout, /BASE44_SITE_AND_BACKEND_DEPLOYED/);
});

test("site publication aborts if a V9 handler serves the wrong activation for the exact build", (t) => {
  const staleFunction = scannerFunctionsV9[0];
  const f = fixture({ editRoutes: selectV9, publishSite: true, staleFunction });
  t.after(() => rmSync(f.root, { recursive: true, force: true }));
  const result = f.run("site-and-functions");
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, new RegExp(`FUNCTION_BUILD_MISMATCH name=${staleFunction}`));
  assert.doesNotMatch(contents(f.calls), /site deploy|npm run build/);
  assert.doesNotMatch(result.stdout, /BASE44_SITE_AND_BACKEND_DEPLOYED/);
});

test("a manifest that selects a mixed scanner generation is rejected before remote writes", () => {
  const f = fixture({ editRoutes(routes) { routes.routes.startStandardScanJob = "startStandardScanJobV9"; } });
  try {
    const result = f.run("scanner-functions");
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /public Base44 route manifest/i);
    assert.equal(contents(f.calls), "");
    assert.doesNotMatch(contents(f.mutations), /set-release-source/);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("site publication requires historical V8 and refuses duplicate active V9 aliases", (t) => {
  for (const corrupt of [
    (routes) => { delete routes.historical_routes.v8; },
    (routes) => { routes.candidate_routes.v9 = routes.routes; },
  ]) {
    const f = fixture({ publishSite: true, editRoutes(routes) {
      selectV9(routes);
      corrupt(routes);
    } });
    t.after(() => rmSync(f.root, { recursive: true, force: true }));
    const result = f.run("site-and-functions");
    assert.equal(result.status, 2, result.stderr);
    assert.match(result.stderr, /public Base44 route manifest/i);
    assert.equal(contents(f.calls), "");
    assert.doesNotMatch(contents(f.mutations), /set-release-source/);
  }
});

test("unknown deployment scope fails before any mutation", () => {
  const f = fixture();
  try {
    const result = f.run("scanner-functions-and-site");
    assert.notEqual(result.status, 0);
    assert.equal(contents(f.calls), "");
    assert.equal(contents(f.mutations), "");
    assert.match(result.stderr, /deployment scope/i);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("hosted release dispatch defaults safely and preserves shared release protections", () => {
  assert.match(workflow, /deployment_target:[\s\S]*default:\s*scanner-functions[\s\S]*options:[\s\S]*- scanner-functions[\s\S]*- site-and-functions/);
  assert.match(workflow, /case "\$INPUT_DEPLOYMENT_TARGET" in[\s\S]*scanner-functions\|site-and-functions[\s\S]*Refusing/);
  assert.match(workflow, /if:.*deployment_target.*scanner-functions[\s\S]*DEPLOY_SCOPE:\s*scanner-functions[\s\S]*deploy-base44-beta-functions\.sh/);
  assert.match(workflow, /if:.*deployment_target.*site-and-functions[\s\S]*deploy-base44-beta-site\.sh/);
  assert.match(workflow, /group:\s*fixlist-base44-hosted-controls-v2/);
  assert.match(workflow, /github\.actor == 'bright4862-design'/);
  assert.match(workflow, /git rev-parse origin\/main/);
  assert.match(workflow, /BASE44_EXPECTED_OWNER: \$\{\{ secrets\.BASE44_EXPECTED_OWNER \}\}/);
  assert.match(workflow, /if: \$\{\{ always\(\) \}\}[\s\S]*rm -rf "\$HOME\/\.base44"/);
});
