import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const source = "a".repeat(40);
const bright = { id: "6a498da58ef5cec1f5cd4486", email: "bright4862@gmail.com", role: "admin" };
const london = { id: "6a498732ec779dfaaeab0e54", email: "londonparisbrussels@gmail.com", role: "admin" };
const customer = { id: "6aaaaaaaaaaaaaaaaaaaaaaa", email: "customer@example.test", role: "user" };
const operator = "scripts/operate-base44-staged-runtime.sh";
const collector = "scripts/collect-base44-staged-observations.sh";
const routeManifest = "data/generated-staged-v9-routes.json";
const { functions } = JSON.parse(readFileSync(new URL("../../" + routeManifest, import.meta.url), "utf8"));
const { route_name: intakeRoute, build_id: buildId, runtime_activation_id: activationId } = functions.startStandardScanJobV9;
const fingerprint = "2".repeat(16);
const customerDigest = createHash("sha256").update(JSON.stringify([customer.id])).digest("hex");
const gatewayOrigin = "https://fixlist-dispatch-gateway-tpucgyfewa-ew.a.run.app";
const gatewayRevision = "fixlist-dispatch-gateway-staged-fixture";
const emptyCohortDigest = createHash("sha256").update("[]").digest("hex");

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "staged-operator-identity-"));
  const output = realpathSync(mkdtempSync(join(tmpdir(), "staged-operator-observations-")));
  t.after(() => {
    rmSync(root, { recursive: true, force: true });
    rmSync(output, { recursive: true, force: true });
  });
  mkdirSync(join(root, "scripts/lib"), { recursive: true });
  mkdirSync(join(root, "data"));
  writeFileSync(join(root, "data/beta-crawler-revision.json"), JSON.stringify({ fingerprint }));
  copyFileSync(routeManifest, join(root, routeManifest));
  for (const file of [operator, collector]) copyFileSync(file, join(root, file));
  writeFileSync(join(root, "scripts/lib/release-source-guard.sh"), "fixlist_require_exact_main() { [[ \"$2\" == \"$SOURCE_SHA\" ]]; }\n");
  writeFileSync(join(root, "scripts/lib/base44-pinned-cli.sh"), `
fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$TEST_CLI"; }
fixlist_require_base44_owner() { [[ "$1" == "$TEST_CLI_USER" ]] || return 2; }
`);
  writeFileSync(join(root, "scripts/base44_release_manifest.mjs"),
    "export function assertPulledFunctionPackage() {}\n");
  const readiness = { schema_version: "fixlist_staged_v9_readiness_v2", candidate_fingerprint: fingerprint,
    functions: Object.entries(functions).map(([name, row]) => ({ name, ...row, http_status: 405 })),
    runtime_probe_transport: "base44_native_authenticated_sdk_get",
    anonymous_probe: { transport: "base44_legacy_anonymous_get",
      functions: Object.entries(functions).map(([name, { route_name, build_id, runtime_activation_id }]) => ({
        name, route_name, build_id, runtime_activation_id, state: "matched", http_status: 405,
      })) } };
  writeFileSync(join(root, "scripts/deploy-base44-staged-functions.sh"), `
#!/usr/bin/env bash
[[ "$1" == verify ]] || exit 1
printf '%s\\n' '${JSON.stringify(readiness)}' > "$READINESS_OUTPUT"
`);
  writeFileSync(join(root, "scripts/base44_staged_schema.mjs"), `
import { writeFileSync } from "node:fs";
if (process.argv[2] !== "verify") process.exit(1);
writeFileSync(process.argv.at(-1), "{}");
`);
  writeFileSync(join(root, "package.json"), '{"type":"module"}');
  const cli = join(root, "base44");
  const trace = join(root, "trace");
  writeFileSync(cli, `#!${process.execPath}
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
const log = (value) => appendFileSync(process.env.TEST_TRACE, JSON.stringify(value) + "\\n");
const args = process.argv.slice(2);
log(args.slice(2));
if (args[0] !== "--app-id" || args[1] !== "6a498732ec779dfaaeab0e53") process.exit(3);
if (args[2] === "functions" && args[3] === "pull") {
  const folder = "base44/functions/fixlistStagedRuntimeControl";
  mkdirSync(folder, { recursive: true });
  writeFileSync(folder + "/function.jsonc", "{}");
}
if (args[2] === "exec") {
  const base44 = {
    auth: { me: () => { log(["auth.me"]); return JSON.parse(process.env.TEST_USER); } },
    functions: { invoke: (name, payload) => {
      log(["invoke", name, payload.action]);
      if (name === "fixlistStagedRuntimeControl") return {
        success: true, operator_build_id: "fixlist-staged-runtime-control-v1", v9_runtime_attested: false,
        schema_version: "fixlist_staged_runtime_readback_v1", config_converged: true,
        env_mode: "staged", owner_match: true, cohort_count: 1, intake_disabled_verified: true,
        ...JSON.parse(process.env.TEST_PROBE)
      };
      if (name !== "${intakeRoute}" || payload.action !== "staged_runtime_status") throw new Error("unexpected intake route");
      return {
        success: true, schema_version: "fixlist_staged_v9_intake_readback_v1",
        observed_at: new Date().toISOString(), build_id: "${buildId}", runtime_activation_id: "${activationId}",
        release_fingerprint: "${fingerprint}", configured_pipeline_mode: "staged", pipeline_mode: "staged",
        staged_owner_cohort_state: "explicit", staged_owner_count: 1, staged_owner_cohort_sha256: "3".repeat(64),
        staged_owner_enabled: true, intake_gate: "enabled", admission_gate: "enabled",
        staged_rollout_scope: "off", staged_500_entitled_enabled: false,
        ...JSON.parse(process.env.TEST_V9),
      };
    } },
  };
  const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
  await new AsyncFunction("base44", readFileSync(0, "utf8"))(base44);
}
`);
  chmodSync(cli, 0o700);
  const curl = join(root, "curl");
  writeFileSync(curl, `#!${process.execPath}
import { appendFileSync, readFileSync } from "node:fs";
const url = process.argv.at(-1);
if (url !== "${gatewayOrigin}/health") process.exit(3);
const trace = process.env.TEST_TRACE;
const closed = readFileSync(trace, "utf8").includes("BETA_SCAN_INTAKE_ENABLED=false");
appendFileSync(trace, JSON.stringify(["gateway.health"]) + "\\n");
console.log(JSON.stringify({
  ok: true, service: "fixlist-dispatch-gateway", source_sha: "${source}", revision: "${gatewayRevision}",
  pipeline_mode: "staged", staged_rollout_scope: "paid", staged_500_entitled_enabled: process.env.STAGED_PAID_PAGE_CAP === "500",
  staged_owner_count: 0, staged_owner_cohort_sha256: "${emptyCohortDigest}", canary_worker_origin: null, canary_owner_count: 0,
  ...JSON.parse(process.env.TEST_GATEWAY),
  ...(closed ? JSON.parse(process.env.TEST_GATEWAY_AFTER_CLOSE) : {}),
}));
`);
  chmodSync(curl, 0o700);
  return (script, operation, selected, user, options = {}) => {
    const confirm = {
      "prepare-owner": `PREPARE-BASE44-STAGED-150:${source}:${selected}`,
      "prepare-paid": `PREPARE-BASE44-STAGED-PAID:${source}:${gatewayRevision}:${options.cap || "150"}`,
      "deploy-probe": `DEPLOY-BASE44-STAGED-PROBE:${source}`,
      disable: `DISABLE-BASE44-STAGED:${source}:${selected}`,
    }[operation] || "";
    const result = spawnSync("bash", [script], {
      cwd: root, encoding: "utf8", timeout: 15000,
      env: {
        ...process.env, PATH: `${root}:${process.env.PATH}`, BASE44_API_KEY: options.apiKey || "", SOURCE_SHA: source, OPERATION: operation,
        CONFIRM: options.confirm ?? confirm, STAGED_OPERATOR_USER_ID: options.operatorId || "",
        BASE44_EXPECTED_OWNER: options.expectedCli || "", TEST_CLI_USER: options.actualCli || options.expectedCli || "",
        STAGED_OWNER_USER_ID: selected, EXPECTED_OWNER_USER_ID: selected, BASE44_OBSERVATIONS_DIR: output,
        STAGED_COHORT_TARGET_ROLE: options.targetRole || "user",
        TEST_CLI: cli, TEST_TRACE: trace, TEST_USER: JSON.stringify(user),
        TEST_PROBE: JSON.stringify(options.probe || {}), TEST_V9: JSON.stringify(options.v9 || {}),
        STAGED_PAID_PAGE_CAP: options.cap || "150", STAGED_GATEWAY_REVISION: gatewayRevision,
        TEST_GATEWAY: JSON.stringify(options.gateway || {}), TEST_GATEWAY_AFTER_CLOSE: JSON.stringify(options.gatewayAfterClose || {}),
      },
    });
    const calls = existsSync(trace) ? readFileSync(trace, "utf8").trim().split("\n").map(JSON.parse) : [];
    return { ...result, calls, output };
  };
}

test("the new London staged cohort uses the signed-in app identity before any Base44 writes", t => {
  const result = fixture(t)(operator, "prepare-owner", london.id, london, {
    v9: {
      staged_owner_cohort_sha256: createHash("sha256").update(JSON.stringify([london.id])).digest("hex"),
      intake_gate: "disabled",
    },
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.calls.slice(0, 2), [["exec", "--data-env", "prod"], ["auth.me"]]);
  assert.equal(result.calls.filter(([name]) => name === "secrets").length, 2);
  assert.ok(result.calls.some(row => row.includes(`SCAN_STAGED_OWNER_IDS=${london.id}`)));
  assert.equal(result.calls.filter(row => row[1] === intakeRoute).length, 2);
});

for (const [operation, user] of [
  ["deploy-probe", bright],
  ["prepare-owner", { ...london, email: bright.email }],
  ["disable", { ...london, role: "user" }],
]) {
  test(`a mismatched app identity cannot mutate Base44 with ${operation}`, t => {
    const result = fixture(t)(operator, operation, london.id, user);
    assert.equal(result.status, 2);
    assert.deepEqual(result.calls, [["exec", "--data-env", "prod"], ["auth.me"]]);
    assert.doesNotMatch(result.stdout + result.stderr, /@gmail\.com/);
  });
}

function pilotOptions(admin = london, overrides = {}) {
  return {
    operatorId: admin.id,
    expectedCli: admin.email,
    probe: { owner_match: false },
    v9: {
      pipeline_mode: "monolith",
      staged_owner_enabled: false,
      staged_owner_cohort_sha256: customerDigest,
      intake_gate: "disabled",
    },
    ...overrides,
  };
}

for (const [name, admin] of [["London", london], ["Bright", bright]]) {
  test(`the approved ${name} administrator prepares only the customer and proves the exact V9 cohort`, t => {
    const result = fixture(t)(operator, "prepare-owner", customer.id, admin, pilotOptions(admin));
    assert.equal(result.status, 0, result.stderr);
    const { calls } = result;
    const intakeReadbacks = calls.flatMap((row, index) => row[1] === intakeRoute ? [index] : []);
    const mutations = calls.flatMap((row, index) => row[0] === "secrets" ? [index] : []);
    assert.deepEqual(calls.slice(0, 2), [["exec", "--data-env", "prod"], ["auth.me"]]);
    assert.equal(intakeReadbacks.length, 2);
    assert.equal(mutations.length, 2);
    assert.ok(intakeReadbacks[0] < mutations[0] && mutations[1] < intakeReadbacks[1]);
    assert.deepEqual(calls[mutations[0]], ["secrets", "set", "BETA_SCAN_INTAKE_ENABLED=false"]);
    assert.deepEqual(calls[mutations[1]], ["secrets", "set", "SCAN_PIPELINE_MODE=staged", `SCAN_STAGED_OWNER_IDS=${customer.id}`,
      "SCAN_STAGED_ROLLOUT_SCOPE=off", "SCAN_STAGED_500_ENTITLED_ENABLED=false"]);
    assert.match(result.stdout, /public_intake=closed v9_attested=true pilot_cohort_matches=true/);
    assert.equal((result.stdout + result.stderr).includes(customer.id), false);
    assert.equal((result.stdout + result.stderr).includes(customerDigest), false);
  });
}

for (const [name, user, overrides] of [
  ["absent explicit administrator", london, { operatorId: "" }],
  ["unknown administrator", london, { operatorId: customer.id }],
  ["wrong confirmation target", london, { confirm: `PREPARE-BASE44-STAGED-150:${source}:${london.id}` }],
  ["wrong configured CLI account", london, { expectedCli: bright.email }],
  ["different signed-in CLI account", london, { actualCli: bright.email }],
  ["workspace API key without the personal CLI session", london, { apiKey: "b44k_mock" }],
  ["ordinary customer as the runtime caller", customer, {}],
  ["stale V9 intake build", london, { v9: { build_id: "0".repeat(64) } }],
]) {
  test(`pilot preparation makes zero configuration writes with ${name}`, t => {
    const result = fixture(t)(operator, "prepare-owner", customer.id, user, pilotOptions(london, overrides));
    assert.equal(result.status, 2, result.stderr);
    assert.equal(result.calls.some(([command]) => command === "secrets"), false);
    assert.doesNotMatch(result.stdout, /BASE44_STAGED_CONFIG_READBACK_VERIFIED/);
  });
}

for (const drift of [
  { staged_owner_cohort_sha256: "9".repeat(64) },
  { staged_owner_count: 2 },
  { staged_owner_enabled: true },
  { intake_gate: "enabled" },
]) {
  test(`pilot verification fails closed for V9 drift in ${Object.keys(drift)[0]}`, t => {
    const options = pilotOptions();
    options.v9 = { ...options.v9, ...drift };
    const result = fixture(t)(operator, "prepare-owner", customer.id, london, options);
    assert.equal(result.status, 2, result.stderr);
    assert.ok(result.calls.some(row => row.includes("BETA_SCAN_INTAKE_ENABLED=false")));
    assert.doesNotMatch(result.stdout, /BASE44_STAGED_CONFIG_READBACK_VERIFIED/);
  });
}

test("customer-cohort disable is available with a stale V9 route", t => {
  const options = pilotOptions(london, { probe: { env_mode: "monolith", owner_match: false, cohort_count: 0 } });
  const result = fixture(t)(operator, "disable", customer.id, london, options);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.calls.some(row => row[1] === intakeRoute), false);
  assert.ok(result.calls.some(row => row.includes("SCAN_PIPELINE_MODE=monolith") && row.includes("SCAN_STAGED_OWNER_IDS=")));
  assert.ok(result.calls.some(row => row.includes("SCAN_STAGED_ROLLOUT_SCOPE=off") && row.includes("SCAN_STAGED_500_ENTITLED_ENABLED=false")));
});

test("read-only pilot status identifies a different exact cohort without exposing it", t => {
  const options = pilotOptions();
  options.v9.staged_owner_cohort_sha256 = "9".repeat(64);
  const result = fixture(t)(operator, "status", customer.id, london, options);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.calls.some(([command]) => command === "secrets"), false);
  const status = JSON.parse(result.stdout.trim().split("\n").at(-1));
  assert.equal(status.v9_intake_attested, true);
  assert.equal(status.pilot_cohort_matches, false);
  assert.equal(result.stdout.includes("9".repeat(64)), false);
});

test("an authenticated London operator can prepare Bright for an explicit admin canary", t => {
  const options = pilotOptions(london, { targetRole: "admin" });
  options.v9.staged_owner_cohort_sha256 = createHash("sha256").update(JSON.stringify([bright.id])).digest("hex");
  const result = fixture(t)(operator, "prepare-owner", bright.id, london, options);
  assert.equal(result.status, 0, result.stderr);
  assert.ok(result.calls.some(row => row.includes(`SCAN_STAGED_OWNER_IDS=${bright.id}`)));
  assert.match(result.stdout, /v9_attested=true pilot_cohort_matches=true/);
});

test("separate preparation requires the selected cohort role to match the test account", t => {
  for (const [target, role] of [[customer, "admin"], [bright, "user"]]) {
    const result = fixture(t)(operator, "prepare-owner", target.id, london, pilotOptions(london, { targetRole: role }));
    assert.equal(result.status, 2);
    assert.equal(result.calls.some(([command]) => command === "secrets"), false);
  }
});

function paidOptions(cap = "150", overrides = {}) {
  return {
    cap, operatorId: london.id, expectedCli: london.email,
    v9: { pipeline_mode: "monolith", staged_owner_enabled: false, staged_owner_cohort_state: "empty",
      staged_owner_count: 0, staged_owner_cohort_sha256: emptyCohortDigest, intake_gate: "disabled",
      staged_rollout_scope: "paid", staged_500_entitled_enabled: cap === "500", paid_dispatch_gateway_origin: gatewayOrigin },
    ...overrides,
  };
}

for (const cap of ["150", "500"]) {
  test(`paid ${cap} preparation proves both runtimes and keeps intake closed`, t => {
    const result = fixture(t)(operator, "prepare-paid", "", london, paidOptions(cap));
    assert.equal(result.status, 0, result.stderr);
    const relevant = result.calls.filter(([name, fn]) => name === "secrets" || name === "gateway.health" || fn === intakeRoute);
    assert.deepEqual(relevant, [
      ["invoke", intakeRoute, "staged_runtime_status"], ["gateway.health"],
      ["secrets", "set", "BETA_SCAN_INTAKE_ENABLED=false"], ["gateway.health"],
      ["secrets", "set", "SCAN_PIPELINE_MODE=staged", "SCAN_STAGED_OWNER_IDS=", "SCAN_PIPELINE_OWNER_IDS=",
        "SCAN_STAGED_ROLLOUT_SCOPE=paid", `SCAN_STAGED_500_ENTITLED_ENABLED=${cap === "500"}`],
      ["invoke", intakeRoute, "staged_runtime_status"], ["gateway.health"],
    ]);
    assert.match(result.stdout, /BASE44_STAGED_PAID_READBACK_VERIFIED.*public_intake=closed/);
  });
}

test("paid preparation makes no writes when Base44 dispatches to another origin", t => {
  const options = paidOptions();
  options.v9.paid_dispatch_gateway_origin = "https://other.example";
  const result = fixture(t)(operator, "prepare-paid", "", london, options);
  assert.equal(result.status, 2);
  assert.equal(result.calls.some(([command]) => command === "secrets" || command === "gateway.health"), false);
});

test("paid preparation leaves intake closed when the gateway changes after the close", t => {
  const options = paidOptions("500", { gatewayAfterClose: { staged_500_entitled_enabled: false } });
  const result = fixture(t)(operator, "prepare-paid", "", london, options);
  assert.equal(result.status, 2);
  assert.deepEqual(result.calls.filter(([command]) => command === "secrets"), [["secrets", "set", "BETA_SCAN_INTAKE_ENABLED=false"]]);
});

test("paid status cross-checks both runtimes without writing", t => {
  const result = fixture(t)(operator, "status-paid", "", london, paidOptions("500"));
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.calls.filter(([command]) => command === "secrets"), []);
  assert.deepEqual(JSON.parse(result.stdout.trim()), {
    base44_v9_attested: true, page_cap: 500, intake_gate: "disabled", admission_gate: "enabled",
  });
});

test("off status verifies actual V9 rollback and keeps the operator read-only", t => {
  const v9 = {
    configured_pipeline_mode: "monolith", pipeline_mode: "monolith", staged_owner_cohort_state: "empty",
    staged_owner_count: 0, staged_owner_enabled: false, staged_owner_cohort_sha256: emptyCohortDigest,
    intake_gate: "disabled",
  };
  const result = fixture(t)(operator, "status-off", "", london, { ...paidOptions(), v9 });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.calls.some(([command]) => command === "secrets" || command === "gateway.health"), false);
  assert.deepEqual(JSON.parse(result.stdout.trim()), {
    base44_v9_attested: true, staged_rollout_scope: "off", staged_500_entitled_enabled: false, intake_gate: "disabled",
  });
});

test("off status refuses proof while the exact V9 runtime still sees paid settings", t => {
  const options = paidOptions("500");
  options.v9.configured_pipeline_mode = "monolith";
  const result = fixture(t)(operator, "status-off", "", london, options);
  assert.equal(result.status, 2);
  assert.equal(result.calls.some(([command]) => command === "secrets"), false);
  assert.doesNotMatch(result.stdout, /base44_v9_attested/);
});

test("the collector reads V9 for the selected London app identity", t => {
  const result = fixture(t)(collector, "status", london.id, london);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.calls, [
    ["exec", "--data-env", "prod"], ["auth.me"], ["invoke", intakeRoute, "staged_runtime_status"],
  ]);
  assert.equal(JSON.parse(readFileSync(join(result.output, "intake.json"), "utf8")).staged_owner_enabled, true);
});

test("the collector refuses a different app identity before any V9 call", t => {
  const result = fixture(t)(collector, "status", london.id, bright);
  assert.notEqual(result.status, 0);
  assert.deepEqual(result.calls, [["exec", "--data-env", "prod"], ["auth.me"]]);
  assert.equal(existsSync(join(result.output, "intake.json")), false);
});
