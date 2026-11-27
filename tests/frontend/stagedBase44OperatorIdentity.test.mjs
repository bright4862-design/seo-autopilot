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
const launcherEntitlement = "base44/functions/startStandardScanJobV9/entitlement.js";
const routeManifestBytes = readFileSync(new URL("../../" + routeManifest, import.meta.url), "utf8");
const { functions } = JSON.parse(routeManifestBytes);
const { route_name: intakeRoute, build_id: buildId, runtime_activation_id: activationId } = functions.startStandardScanJobV9;
const fingerprint = "2".repeat(16);
const customerDigest = createHash("sha256").update(JSON.stringify([customer.id])).digest("hex");
const brightDigest = createHash("sha256").update(JSON.stringify([bright.id])).digest("hex");
const gatewayOrigin = "https://fixlist-dispatch-gateway-tpucgyfewa-ew.a.run.app";
const gatewayRevision = "fixlist-dispatch-gateway-staged-fixture";
const pilotWorkerOrigin = "https://canary-00123-xyz---fixlist-standard150-worker-tpucgyfewa-ew.a.run.app";
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
  writeFileSync(join(root, routeManifest), routeManifestBytes);
  mkdirSync(join(root, "base44/functions/startStandardScanJobV9"), { recursive: true });
  copyFileSync(launcherEntitlement, join(root, launcherEntitlement));
  for (const file of [operator, collector, "scripts/assert_tagged_zero_traffic_worker.py"]) copyFileSync(file, join(root, file));
  writeFileSync(join(root, "scripts/verify-base44-site.sh"), [
    '[[ "$EXPECTED_SOURCE_SHA" == "$SOURCE_SHA" && "$1" == --published-pilot ]] || exit 4',
    "printf '[\"site.verify\",\"%s\"]\\n' \"$2\" >> \"$TEST_TRACE\"",
    '[[ "${TEST_PILOT_SITE_STALE:-}" != yes ]]',
  ].join("\n"));
  const gcloud = join(root, "gcloud");
  const workerServiceOrigin = pilotWorkerOrigin.replace("canary-00123-xyz---", "");
  const workerRevision = "fixlist-standard150-worker-00123-xyz";
  const sourceTag = `staged-${source.slice(0, 12)}`;
  writeFileSync(gcloud, `#!${process.execPath}
import { appendFileSync } from "node:fs";
const args = process.argv.slice(2);
if (args[0] === "auth" && args[1] === "print-identity-token") {
  console.log("fixture-token");
} else if (args[0] === "run" && args[1] === "services" && args[2] === "describe" && args[3] === "fixlist-standard150-worker") {
  appendFileSync(process.env.TEST_TRACE, JSON.stringify(["worker.service"]) + "\\n");
  console.log(JSON.stringify({ status: { url: "${workerServiceOrigin}", traffic: [
    { revisionName: "${workerRevision}", tag: "canary-00123-xyz", url: "${pilotWorkerOrigin}", percent: Number(process.env.TEST_WORKER_PERCENT) },
    { revisionName: "${workerRevision}", tag: "${sourceTag}", url: "${workerServiceOrigin.replace("https://", `https://${sourceTag}---`)}" },
  ] } }));
} else if (args[0] === "run" && args[1] === "revisions" && args[2] === "describe" && args[3] === "${workerRevision}") {
  console.log(JSON.stringify({
    metadata: { name: "${workerRevision}" },
    spec: { containers: [{ env: [
      { name: "SCAN_PIPELINE_MODE", value: "staged" },
      { name: "SCAN_STAGED_OWNER_IDS", value: process.env.TEST_WORKER_OWNER },
      { name: "FIXLIST_WORKER_SOURCE_SHA", value: "${source}" },
    ] }] },
    status: { conditions: [{ type: "Ready", status: "True" }] },
  }));
} else {
  process.exit(3);
}
`);
  chmodSync(gcloud, 0o700);
  writeFileSync(join(root, "scripts/fixlist-cloud-operator.sh"), `
[[ "$OPERATION" == verify-worker-runtime-revision && "$SOURCE_SHA" == "${source}" &&
  "$TARGET_REVISION" == "${workerRevision}" && "$FIXLIST_WORKER_PROBE_URL" == "${pilotWorkerOrigin}" &&
  "$FIXLIST_WORKER_TOKEN_AUDIENCE" == "${workerServiceOrigin}" && "$FIXLIST_VERIFY_STAGED_BASE44_RUNTIME" == 1 ]]
`);
  writeFileSync(join(root, "scripts/lib/release-source-guard.sh"), [
    'fixlist_require_exact_main() { [[ "$2" == "$SOURCE_SHA" && "$TEST_MAIN_MOVED" != true ]]; }',
    'fixlist_require_merged_checkout() { [[ "$2" == "$SOURCE_SHA" && "$TEST_SOURCE_MERGED" == true ]]; }',
  ].join("\n"));
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
  const cli = join(root, "base44-cli");
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
    entities: {
      User: { get: () => { log(["user.get"]); return JSON.parse(process.env.TEST_BRIGHT_TARGET); } },
      Access: { filter: () => { log(["grant.filter"]); return JSON.parse(process.env.TEST_BRIGHT_GRANT); } },
    },
    functions: { invoke: (name, payload) => {
      log(["invoke", name, payload.action]);
      if (name === "fixlistStagedRuntimeControl") return {
        success: true, operator_build_id: "fixlist-staged-runtime-control-v1", v9_runtime_attested: false,
        schema_version: "fixlist_staged_runtime_readback_v1", config_converged: true,
        env_mode: "staged", owner_match: true, cohort_count: 1, intake_disabled_verified: true,
        ...JSON.parse(process.env.TEST_PROBE)
      };
      if (name !== "${intakeRoute}" || payload.action !== "staged_runtime_status") throw new Error("unexpected intake route");
      const changedPilot = readFileSync(process.env.TEST_TRACE, "utf8").includes("SCAN_PUBLIC_PILOT_EXPIRES_AT=");
      return {
        success: true, schema_version: "fixlist_staged_v9_intake_readback_v1",
        observed_at: new Date().toISOString(), build_id: "${buildId}", runtime_activation_id: "${activationId}",
        release_fingerprint: "${fingerprint}", configured_pipeline_mode: "staged", pipeline_mode: "staged",
        staged_owner_cohort_state: "explicit", staged_owner_count: 1, staged_owner_cohort_sha256: "3".repeat(64),
        staged_owner_enabled: true, intake_gate: "enabled", admission_gate: "enabled",
        staged_rollout_scope: "off", staged_500_entitled_enabled: false, legacy_staged_500_entitled_enabled: false,
        paid_dispatch_gateway_origin: "${gatewayOrigin}", admin_500_rehearsal_enabled: false,
        ...JSON.parse(process.env.TEST_V9),
        ...(changedPilot ? JSON.parse(process.env.TEST_V9_AFTER_PILOT) : {}),
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
      "prepare-owner": `PREPARE-BASE44-STAGED-150:${source}:${selected}${options.pilotExpiry ? ":" + options.pilotExpiry : ""}`,
      "hold-published-pilot": `HOLD-BASE44-PUBLISHED-PILOT:${source}`,
      "prepare-admin-500-rehearsal": `PREPARE-BASE44-ADMIN-500-REHEARSAL:${source}:${gatewayRevision}:${selected}:${options.pilotExpiry}`,
      "hold-admin-500-rehearsal": `HOLD-BASE44-ADMIN-500-REHEARSAL:${source}:${selected}`,
      "prepare-paid": `PREPARE-BASE44-STAGED-PAID:${source}:${gatewayRevision}:${options.cap || "150"}`,
      "prepare-paid-500-pilot": `PREPARE-PAID-500-PILOT:${source}:${gatewayRevision}:${selected}:${options.pilotExpiry}`,
      "hold-paid-500-pilot": `HOLD-PAID-500-PILOT:${source}:${selected}`,
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
        EXPECTED_OPERATOR_USER_ID: options.intakeOperatorId || "",
        STAGED_COHORT_TARGET_ROLE: options.targetRole || "user",
        STAGED_PUBLIC_PILOT_EXPIRES_AT: options.pilotExpiry || "",
        STAGED_PILOT_WORKER_ORIGIN: options.workerOrigin ?? (options.pilotExpiry ? pilotWorkerOrigin : ""),
        TEST_MAIN_MOVED: options.mainMoved ? "true" : "false",
        TEST_SOURCE_MERGED: options.sourceMerged === false ? "false" : "true",
        TEST_CLI: cli, TEST_TRACE: trace, TEST_USER: JSON.stringify(user),
        TEST_BRIGHT_TARGET: JSON.stringify(options.targetUser || bright),
        TEST_BRIGHT_GRANT: JSON.stringify([{
          id: "owner-test-access", owner_user_id: bright.id, user_email: bright.email, app_id: "6a498732ec779dfaaeab0e53",
          has_full_access: true, access_status: "active", plan_id: "standard150_lifetime", page_cap: options.grantCap ?? 500,
          grant_source: "owner_test", granted_at: "2026-11-25T00:00:00Z",
        }]),
        TEST_PILOT_SITE_STALE: options.siteStale ? "yes" : "",
        TEST_WORKER_PERCENT: String(options.workerPercent ?? 0), TEST_WORKER_OWNER: options.workerOwner || bright.id,
        TEST_PROBE: JSON.stringify(options.probe || {}), TEST_V9: JSON.stringify(options.v9 || {}),
        TEST_V9_AFTER_PILOT: JSON.stringify(options.v9AfterPilot || {}),
        STAGED_PAID_PAGE_CAP: options.cap || "150", STAGED_GATEWAY_REVISION: gatewayRevision,
        TEST_GATEWAY: JSON.stringify({
          ...(options.pilotExpiry && operation === "prepare-owner" ? {
            staged_rollout_scope: "off", staged_500_entitled_enabled: false,
            staged_owner_count: 1, staged_owner_cohort_sha256: customerDigest,
            canary_worker_origin: pilotWorkerOrigin, canary_owner_count: 1, canary_owner_cohort_sha256: customerDigest,
          } : {}),
          ...options.gateway,
        }),
        TEST_GATEWAY_AFTER_CLOSE: JSON.stringify(options.gatewayAfterClose || {}),
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
      "SCAN_STAGED_ROLLOUT_SCOPE=off", "SCAN_STAGED_500_ENTITLED_ENABLED=false", "SCAN_STAGED_PILOT_OWNER_IDS=",
      "SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED=false"]);
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
  ["an unavailable V9 gateway", london, { v9: { paid_dispatch_gateway_origin: "" } }],
  ["a different V9 gateway", london, { v9: { paid_dispatch_gateway_origin: "https://other.example" } }],
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
        "SCAN_STAGED_ROLLOUT_SCOPE=paid", "SCAN_STAGED_500_ENTITLED_ENABLED=false",
        `SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED=${cap === "500"}`,
        "SCAN_STAGED_PILOT_OWNER_IDS=", "SCAN_PUBLIC_PILOT_EXPIRES_AT=0", "SCAN_PUBLIC_PILOT_ADMIN_500_OWNER_ID="],
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

test("paid status rejects an enabled legacy 500 launcher even when the current launcher and gateway agree", t => {
  const options = paidOptions("500");
  options.v9.legacy_staged_500_entitled_enabled = true;
  const result = fixture(t)(operator, "status-paid", "", london, options);
  assert.equal(result.status, 2, result.stderr);
  assert.equal(result.calls.some(([command]) => command === "secrets"), false);
});

test("preparing and holding only the 500 pilot leaves the paid 150 intake settings untouched", t => {
  const expiry = Math.floor(Date.now() / 1000) + 1800;
  const emptyPilot = { staged_pilot_owner_count: 0, staged_pilot_owner_cohort_sha256: emptyCohortDigest };
  const namedPilot = { staged_pilot_owner_count: 1, staged_pilot_owner_cohort_sha256: customerDigest };
  const options = paidOptions();
  options.v9.intake_gate = "enabled";
  const prepared = fixture(t)(operator, "prepare-paid-500-pilot", customer.id, london, {
    ...options, v9: { ...options.v9, ...emptyPilot },
    v9AfterPilot: { ...namedPilot, public_pilot_expires_at: expiry },
    gateway: namedPilot, pilotExpiry: String(expiry),
  });
  assert.equal(prepared.status, 0, prepared.stderr);
  assert.deepEqual(prepared.calls.filter(([command]) => command === "secrets"), [
    ["secrets", "set", `SCAN_STAGED_PILOT_OWNER_IDS=${customer.id}`, `SCAN_PUBLIC_PILOT_EXPIRES_AT=${expiry}`,
      "SCAN_PUBLIC_PILOT_ADMIN_500_OWNER_ID="],
  ]);
  const mismatched = fixture(t)(operator, "prepare-paid-500-pilot", customer.id, london, {
    ...options, v9: { ...options.v9, ...emptyPilot }, gateway: emptyPilot, pilotExpiry: String(expiry),
  });
  assert.equal(mismatched.status, 2);
  assert.deepEqual(mismatched.calls.filter(([command]) => command === "secrets"), []);
  const held = fixture(t)(operator, "hold-paid-500-pilot", customer.id, london, {
    ...options, v9: { ...options.v9, ...namedPilot, public_pilot_expires_at: expiry },
    v9AfterPilot: { public_pilot_expires_at: 0 }, mainMoved: true,
  });
  assert.equal(held.status, 0, held.stderr);
  assert.deepEqual(held.calls.filter(([command]) => command === "secrets"), [
    ["secrets", "set", "SCAN_PUBLIC_PILOT_EXPIRES_AT=0", "SCAN_PUBLIC_PILOT_ADMIN_500_OWNER_ID="],
  ]);
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

test("the collector binds an ordinary cohort to separate operator-only V9 readback", t => {
  const result = fixture(t)(collector, "status", customer.id, london, {
    intakeOperatorId: london.id,
    v9: { pipeline_mode: "monolith", staged_owner_enabled: false, staged_owner_cohort_sha256: customerDigest },
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.calls, [
    ["exec", "--data-env", "prod"], ["auth.me"], ["invoke", intakeRoute, "staged_runtime_status"],
  ]);
  const intake = JSON.parse(readFileSync(join(result.output, "intake.json"), "utf8"));
  assert.equal(intake.observer_user_id, london.id);
  assert.equal(intake.route_name, intakeRoute);
  assert.equal(intake.staged_owner_cohort_sha256, customerDigest);
  assert.equal(intake.staged_rollout_scope, "off");
  assert.equal(intake.staged_500_entitled_enabled, false);
});

test("ordinary collection fails closed on operator or isolation mismatch", t => {
  const options = { intakeOperatorId: london.id, v9: {
    pipeline_mode: "monolith", staged_owner_enabled: false, staged_owner_cohort_sha256: customerDigest,
  } };
  const wrongOperator = fixture(t)(collector, "status", customer.id, bright, options);
  assert.notEqual(wrongOperator.status, 0);
  assert.deepEqual(wrongOperator.calls, [["exec", "--data-env", "prod"], ["auth.me"]]);
  const widened = fixture(t)(collector, "status", customer.id, london, {
    ...options, v9: { ...options.v9, staged_500_entitled_enabled: true },
  });
  assert.notEqual(widened.status, 0);
  assert.equal(existsSync(join(widened.output, "intake.json")), false);
});

test("published pilot preparation binds expiry to the named ordinary cohort", t => {
  const pilotExpiry = String(Math.floor(Date.now() / 1000) + 1800);
  const options = pilotOptions(london, { pilotExpiry });
  options.v9.public_pilot_expires_at = Number(pilotExpiry);
  const result = fixture(t)(operator, "prepare-owner", customer.id, london, options);
  assert.equal(result.status, 0, result.stderr);
  assert.ok(result.calls.some(row => row.includes(`SCAN_PUBLIC_PILOT_EXPIRES_AT=${pilotExpiry}`)));
  assert.equal(result.calls.filter(([name]) => name === "gateway.health").length, 3);
});

test("published pilot preparation refuses a stale gateway or mismatched canary before any write", t => {
  const pilotExpiry = String(Math.floor(Date.now() / 1000) + 1800);
  for (const gateway of [
    { source_sha: "b".repeat(40) },
    { canary_owner_cohort_sha256: "b".repeat(64) },
    { canary_worker_origin: null },
  ]) {
    const result = fixture(t)(operator, "prepare-owner", customer.id, london, pilotOptions(london, { pilotExpiry, gateway }));
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /does not route the named pilot/);
    assert.equal(result.calls.some(([name]) => name === "secrets"), false);
  }
});

test("holding the published pilot closes only its launcher and verifies the exact runtime", t => {
  const result = fixture(t)(operator, "hold-published-pilot", "", london, {
    operatorId: london.id, expectedCli: london.email, mainMoved: true, v9: { public_pilot_expires_at: 0 },
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.calls.filter(([name]) => name === "secrets"),
    [["secrets", "set", "SCAN_PUBLIC_PILOT_EXPIRES_AT=0", "SCAN_PUBLIC_PILOT_ADMIN_500_OWNER_ID="]]);
  assert.equal(result.calls.filter(row => row[1] === intakeRoute).length, 2);
});


function adminRehearsalOptions(overrides = {}) {
  const expiry = Math.floor(Date.now() / 1000) + 1800;
  return pilotOptions(london, {
    targetRole: "admin",
    pilotExpiry: String(expiry),
    gateway: {
      staged_rollout_scope: "off", staged_500_entitled_enabled: false,
      staged_owner_count: 1, staged_owner_cohort_sha256: brightDigest,
      canary_worker_origin: pilotWorkerOrigin, canary_owner_count: 1, canary_owner_cohort_sha256: brightDigest,
      staged_pilot_owner_count: 0, staged_pilot_owner_cohort_sha256: emptyCohortDigest,
    },
    v9: {
      pipeline_mode: "monolith", staged_owner_enabled: false, staged_owner_cohort_sha256: brightDigest,
      staged_pilot_owner_count: 0, staged_pilot_owner_cohort_sha256: emptyCohortDigest,
      intake_gate: "disabled",
    },
    v9AfterPilot: { admin_500_rehearsal_enabled: true, public_pilot_expires_at: expiry },
    ...overrides,
  });
}

test("London can prepare exactly Bright in the closed 500 rehearsal", t => {
  const options = adminRehearsalOptions();
  const result = fixture(t)(operator, "prepare-admin-500-rehearsal", bright.id, london, options);
  assert.equal(result.status, 0, result.stderr);
  const writes = result.calls.filter(([name]) => name === "secrets");
  assert.deepEqual(writes[0], ["secrets", "set", "BETA_SCAN_INTAKE_ENABLED=false"]);
  assert.ok(writes[1].includes(`SCAN_PUBLIC_PILOT_ADMIN_500_OWNER_ID=${bright.id}`));
  assert.ok(writes[1].includes(`SCAN_PUBLIC_PILOT_EXPIRES_AT=${options.pilotExpiry}`));
  assert.ok(writes[1].includes("SCAN_STAGED_500_ENTITLED_ENABLED=false"));
  assert.match(result.stdout, /BASE44_ADMIN_500_REHEARSAL_PREPARED.*public_intake=closed/);
  assert.ok(result.calls.some(([name]) => name === "user.get"));
  assert.equal(result.calls.filter(([name]) => name === "grant.filter").length, 2);
  assert.ok(result.calls.some(([name]) => name === "worker.service"));
  assert.equal(result.calls.filter(row => row[1] === intakeRoute).length, 3);
});

for (const [detail, options] of [
  ["more than two hours", { pilotExpiry: String(Math.floor(Date.now() / 1000) + 7300) }],
  ["an ordinary or replaced Bright target", { targetUser: { ...bright, role: "user" } }],
  ["a 150-page grant", { grantCap: 150 }],
  ["a worker serving canonical traffic", { workerPercent: 1 }],
  ["a worker pinned to another owner", { workerOwner: customer.id }],
  ["a gateway for another cohort", { gateway: { staged_owner_cohort_sha256: customerDigest } }],
]) {
  test(`the Bright rehearsal makes no changes with ${detail}`, t => {
    const result = fixture(t)(operator, "prepare-admin-500-rehearsal", bright.id, london, adminRehearsalOptions(options));
    assert.notEqual(result.status, 0);
    assert.equal(result.calls.some(([name]) => name === "secrets"), false);
  });
}

test("holding the Bright rehearsal clears only its marker and expiry", t => {
  const options = adminRehearsalOptions({ pilotExpiry: "", mainMoved: true });
  options.v9.admin_500_rehearsal_enabled = true;
  options.v9.public_pilot_expires_at = Math.floor(Date.now() / 1000) + 1800;
  options.v9AfterPilot = { admin_500_rehearsal_enabled: false, public_pilot_expires_at: 0 };
  const result = fixture(t)(operator, "hold-admin-500-rehearsal", bright.id, london, options);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.calls.filter(([name]) => name === "secrets"), [
    ["secrets", "set", "SCAN_PUBLIC_PILOT_ADMIN_500_OWNER_ID=", "SCAN_PUBLIC_PILOT_EXPIRES_AT=0"],
  ]);
  assert.match(result.stdout, /BASE44_ADMIN_500_REHEARSAL_HELD/);
});

test("an old Bright hold cannot expire an ordinary customer's active pilot", t => {
  const options = adminRehearsalOptions({ pilotExpiry: "" });
  options.v9.staged_owner_cohort_sha256 = customerDigest;
  options.v9.public_pilot_expires_at = Math.floor(Date.now() / 1000) + 1800;
  const result = fixture(t)(operator, "hold-admin-500-rehearsal", bright.id, london, options);
  assert.notEqual(result.status, 0);
  assert.equal(result.calls.some(([name]) => name === "secrets"), false);
});


test("Bright rehearsal marker cannot be prepared until V9 observes intake closed", t => {
  const options = adminRehearsalOptions();
  options.v9.intake_gate = "enabled";
  const result = fixture(t)(operator, "prepare-admin-500-rehearsal", bright.id, london, options);
  assert.notEqual(result.status, 0);
  assert.deepEqual(result.calls.filter(([name]) => name === "secrets"), [
    ["secrets", "set", "BETA_SCAN_INTAKE_ENABLED=false"],
  ]);
});

test("a stale public site blocks each named preparation before any Base44 mutation", t => {
  const pilotExpiry = String(Math.floor(Date.now() / 1000) + 3600);
  for (const [operation, target, mode, options] of [
    ["prepare-owner", customer.id, "PUBLISHED_PILOT", pilotOptions(london, { pilotExpiry })],
    ["prepare-admin-500-rehearsal", bright.id, "PUBLISHED_PILOT", adminRehearsalOptions()],
    ["prepare-paid-500-pilot", customer.id, "PAID_PILOT", pilotOptions(london, { pilotExpiry })],
  ]) {
    const result = fixture(t)(operator, operation, target, london, { ...options, siteStale: true });
    assert.notEqual(result.status, 0);
    assert.deepEqual(result.calls, [["site.verify", mode]], result.stderr);
  }
});
