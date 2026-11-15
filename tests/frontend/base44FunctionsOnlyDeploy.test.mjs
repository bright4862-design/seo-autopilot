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
const generatedManifest = "data/generated-staged-v9-routes.json";
const generatedRoutes = JSON.parse(readFileSync(generatedManifest, "utf8")).functions;
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
const physicalV9 = scannerFunctionsV9.map((name) => generatedRoutes[name].route_name);
const productionApp = "6a498732ec779dfaaeab0e53";
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
  cpSync(generatedManifest, join(root, generatedManifest));
  const routes = JSON.parse(readFileSync(routeManifest, "utf8"));
  if (routes.generation === "v9") {
    routes.generation = "v8";
    routes.candidate_routes = { ...routes.candidate_routes, v9: routes.routes };
    routes.routes = routes.historical_routes.v8;
    delete routes.historical_routes.v8;
  }
  editRoutes(routes);
  const v9 = routes.generation === "v9";
  const appId = v9 ? productionApp : "publicTestApp";
  const probeOrigin = v9 ? "https://base44.app" : "https://fixture.invalid";
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
  writeFileSync(join(root, "scripts", "assert_standard150_promotion_record.py"), `import os, sys
with open(os.environ["TEST_MUTATIONS"], "a") as out:
    out.write("release-guard-ran " + " ".join(sys.argv[1:]) + "\\n")
if os.environ.get("TEST_PROMOTION_FAIL"):
    sys.exit(2)
`);

  writeFileSync(join(root, "scripts", "lib", "release-source-guard.sh"), `
fixlist_require_exact_main() {
  [[ ! -e "$TEST_CLI_CALLS.main-advanced" ]] || return 2
  printf 'current-main\\n' >> "$TEST_MUTATIONS"
  FIXLIST_EXACT_SOURCE_SHA="$2"
}
fixlist_require_pinned_checkout() { [[ "$2" == "$FIXLIST_EXACT_SOURCE_SHA" ]]; }
`);
  writeFileSync(join(root, "scripts", "lib", "base44-pinned-cli.sh"), `
fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$TEST_FAKE_CLI"; export FIXLIST_BASE44_CLI; }
fixlist_require_base44_owner() { :; }
fixlist_set_base44_release_source_sha() { printf 'set-release-source\\n' >> "$TEST_MUTATIONS"; }
`);
  writeFileSync(join(root, "scripts", "deploy-base44-staged-functions.sh"), `#!/usr/bin/env bash
fixlist_assert_active_v9_intake_closed() {
  [[ "\${TEST_INTAKE_CLOSED:-yes}" == yes && ! -e "$TEST_CLI_CALLS.intake-open" ]]
}
fixlist_publish_v9_packages() (
  set -euo pipefail
  fixlist_require_pinned_checkout "$PWD" "$SOURCE_SHA"
  [[ "$CONFIRM" == "PUBLISH-BASE44-ACTIVE-V9:$SOURCE_SHA" && ! -e "$READINESS_OUTPUT" ]] || exit 2
  if [[ "$1" == active-preflight ]]; then
    [[ "\${TEST_PACKAGE_PREFLIGHT_FAIL:-}" != yes ]] || exit 2
    fixlist_assert_active_v9_intake_closed
  fi
  printf '%s %s\\n' "$1" '${physicalV9.join(" ")}' >> "$TEST_CLI_CALLS"
  printf '%s\\n' ${physicalV9.join(" ")} >> "$TEST_CLI_CALLS.inventory"
  touch "$READINESS_OUTPUT"
)
`);
  if (publishSite) {
    cpSync(functionVerifier, join(root, functionVerifier));
    writeFileSync(join(root, "scripts", "verify-base44-site.sh"), `#!/usr/bin/env bash
printf 'site-verified\\n' >> "$TEST_MUTATIONS"
`);
    writeFileSync(join(root, "bin", "npm"), `#!/usr/bin/env bash
printf 'npm %s\\n' "$*" >> "$TEST_CLI_CALLS"
if [[ "\${TEST_INTAKE_REOPEN_AFTER_BUILD:-}" == yes ]]; then touch "$TEST_CLI_CALLS.intake-open"; fi
`, { mode: 0o755 });
    writeFileSync(join(root, "bin", "curl"), `#!/usr/bin/env bash
set -euo pipefail
while [[ "$1" != "-o" ]]; do shift; done
body="$2"
url="\${@: -1}"
[[ "$url" == '${probeOrigin}/api/apps/${appId}/functions/'* ]]
name="\${url##*/}"
activation="$name-test"
build="${"a".repeat(64)}"
case "$name" in
${scannerFunctionsV9.map((name) => {
  const identity = generatedRoutes[name];
  return `  ${identity.route_name}) build=${identity.build_id}; activation=${identity.runtime_activation_id} ;;`;
}).join("\n")}
esac
[[ "$name" != "$TEST_STALE_FUNCTION" ]] || activation=stale
printf 'probe %s\\n' "$name" >> "$TEST_CLI_CALLS"
printf '{"build_id":"%s","runtime_activation_id":"%s"}\\n' "$build" "$activation" > "$body"
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
  'functions deploy')
    if [[ -e "$TEST_CLI_CALLS.main-advanced" && "\${TEST_POST_LEGACY_FAIL:-}" == yes ]]; then exit 12; fi
    shift 4
    printf '%s\\n' "$@" >> "$TEST_CLI_CALLS.inventory"
    ;;
  'functions list') cat "$TEST_CLI_CALLS.inventory" ;;
  'site deploy')
    : > "$TEST_CLI_CALLS.inventory"
    touch "$TEST_CLI_CALLS.main-advanced"
    exit "\${TEST_SITE_STATUS:-0}"
    ;;
esac
`);
  chmodSync(fakeCli, 0o755);
  const calls = join(root, "cli-calls");
  const mutations = join(root, "mutations");
  const run = (scope, extraEnv = {}, entry = publisher) => spawnSync("bash", [join(root, entry)], {
    cwd: root,
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${join(root, "bin")}:${process.env.PATH}`,
      SOURCE_SHA: "a".repeat(40),
      CONFIRM: "a".repeat(40),
      BASE44_EXPECTED_OWNER: "owner@example.com",
      BASE44_APP_ID: appId,
      BASE44_FUNCTION_ORIGIN: probeOrigin,
      DEPLOY_SCOPE: scope,
      PROBE_ATTEMPTS: "1",
      TEST_STALE_FUNCTION: staleFunction,
      TEST_FAKE_CLI: fakeCli,
      TEST_CLI_CALLS: calls,
      TEST_MUTATIONS: mutations,
      ...extraEnv,
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
    assert.deepEqual(deploy.trim().split(/\s+/).slice(4), scannerFunctions);
    assert.match(contents(f.calls), new RegExp(`active-preflight ${physicalV9.join(" ")}`));
    assert.match(contents(f.mutations), /release-guard-ran .*--base44-v9 scanner-functions/);
    assert.match(contents(f.mutations), /verify --staged/);
    assert.match(result.stdout, /function_count=12/);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("site publisher deploys and probes exact V9 and retained V8 both before and after site publish", (t) => {
  const f = fixture({ editRoutes: selectV9, publishSite: true });
  t.after(() => rmSync(f.root, { recursive: true, force: true }));
  const result = f.run("site-and-functions");
  assert.equal(result.status, 0, result.stderr);
  const expected = [...physicalV9, ...scannerFunctions];
  const cli = `--app-id ${productionApp}`;
  const probes = expected.map((name) => `probe ${name}`);
  assert.deepEqual(contents(f.calls).trim().split("\n"), [
    `active-preflight ${physicalV9.join(" ")}`,
    `${cli} functions deploy ${scannerFunctions.join(" ")}`,
    ...probes,
    "npm run build",
    `${cli} site deploy --no-build --yes`,
    `${cli} functions deploy ${[...scannerFunctions, ...checkoutFunctions].join(" ")}`,
    `active-restore ${physicalV9.join(" ")}`,
    `${cli} functions list`,
    ...probes,
  ]);
  assert.match(contents(f.mutations), /verify --staged/);
  assert.match(contents(f.mutations), /release-guard-ran .*--base44-v9 site-and-functions/);
  assert.equal(contents(f.mutations).match(/current-main/g)?.length, 1);
  assert.match(contents(f.mutations), /site-verified/);
  assert.match(result.stdout, /BASE44_SITE_AND_BACKEND_DEPLOYED/);
});

test("a failed site upload still restores the pinned V9 and V8 inventory", (t) => {
  const f = fixture({ editRoutes: selectV9, publishSite: true });
  t.after(() => rmSync(f.root, { recursive: true, force: true }));
  const result = f.run("site-and-functions", { TEST_SITE_STATUS: "17" });
  assert.equal(result.status, 17, result.stderr);
  assert.match(result.stderr, /selected function inventory was restored/);
  assert.match(contents(f.calls), /site deploy[\s\S]*functions deploy[\s\S]*active-restore[\s\S]*functions list/);
  assert.doesNotMatch(result.stdout, /BASE44_SITE_AND_BACKEND_DEPLOYED/);
});

test("a failed V8 restoration still attempts the active V9 restoration", (t) => {
  const f = fixture({ editRoutes: selectV9, publishSite: true });
  t.after(() => rmSync(f.root, { recursive: true, force: true }));
  const result = f.run("site-and-functions", { TEST_POST_LEGACY_FAIL: "yes" });
  assert.equal(result.status, 2, result.stderr);
  assert.match(result.stderr, /restoration failed \(checkout=12, active_v9=0\)/);
  assert.match(contents(f.calls), /site deploy[\s\S]*functions deploy[\s\S]*active-restore/);
  assert.doesNotMatch(result.stdout, /BASE44_SITE_AND_BACKEND_DEPLOYED/);
});

test("site publish checks intake again after the build and before upload", (t) => {
  const f = fixture({ editRoutes: selectV9, publishSite: true });
  t.after(() => rmSync(f.root, { recursive: true, force: true }));
  const result = f.run("site-and-functions", { TEST_INTAKE_REOPEN_AFTER_BUILD: "yes" });
  assert.notEqual(result.status, 0);
  assert.match(contents(f.calls), /active-preflight[\s\S]*npm run build/);
  assert.doesNotMatch(contents(f.calls), /site deploy|active-restore/);
});

for (const publishSite of [false, true]) {
  test(`${publishSite ? "site" : "functions-only"} runs V9 approval, package preflight, and closed intake before any writes`, (t) => {
    for (const env of [{ TEST_PROMOTION_FAIL: "yes" }, { TEST_PACKAGE_PREFLIGHT_FAIL: "yes" }, { TEST_INTAKE_CLOSED: "no" }]) {
      const f = fixture({ editRoutes: selectV9, publishSite });
      t.after(() => rmSync(f.root, { recursive: true, force: true }));
      const result = f.run(publishSite ? "site-and-functions" : "scanner-functions", env);
      assert.notEqual(result.status, 0, JSON.stringify(env));
      assert.equal(contents(f.calls), "");
      assert.doesNotMatch(contents(f.mutations), /set-release-source/);
    }
  });
}

test("site publication aborts if a V9 handler serves the wrong activation for the exact build", (t) => {
  const staleFunction = physicalV9[0];
  const f = fixture({ editRoutes: selectV9, publishSite: true, staleFunction });
  t.after(() => rmSync(f.root, { recursive: true, force: true }));
  const result = f.run("site-and-functions");
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, new RegExp(`FUNCTION_BUILD_MISMATCH name=${staleFunction}`));
  assert.doesNotMatch(contents(f.calls), /site deploy|npm run build/);
  assert.doesNotMatch(result.stdout, /BASE44_SITE_AND_BACKEND_DEPLOYED/);
});

test("active V9 publication and verification refuse a different app or probe host before requests", (t) => {
  const f = fixture({ editRoutes: selectV9, publishSite: true });
  t.after(() => rmSync(f.root, { recursive: true, force: true }));
  for (const env of [{ BASE44_APP_ID: "otherApp" }, { BASE44_FUNCTION_ORIGIN: "https://other.invalid" }]) {
    for (const entry of [siteScript, functionVerifier]) {
      const result = f.run("site-and-functions", env, entry);
      assert.equal(result.status, 2, result.stderr);
      assert.match(result.stderr, /the FixList app and Base44 origin must match/);
    }
  }
  assert.equal(contents(f.calls), "");
  assert.doesNotMatch(contents(f.mutations), /set-release-source/);
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
