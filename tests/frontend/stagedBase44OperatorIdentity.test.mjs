import assert from "node:assert/strict";
import { chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const source = "a".repeat(40);
const bright = { id: "6a498da58ef5cec1f5cd4486", email: "bright4862@gmail.com", role: "admin" };
const london = { id: "6a498732ec779dfaaeab0e54", email: "londonparisbrussels@gmail.com", role: "admin" };
const operator = "scripts/operate-base44-staged-runtime.sh";
const collector = "scripts/collect-base44-staged-observations.sh";

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "staged-operator-identity-"));
  const output = mkdtempSync(join(tmpdir(), "staged-operator-observations-"));
  t.after(() => {
    rmSync(root, { recursive: true, force: true });
    rmSync(output, { recursive: true, force: true });
  });
  mkdirSync(join(root, "scripts/lib"), { recursive: true });
  for (const file of [operator, collector]) copyFileSync(file, join(root, file));
  writeFileSync(join(root, "scripts/lib/release-source-guard.sh"), "fixlist_require_exact_main() { [[ \"$2\" == \"$SOURCE_SHA\" ]]; }\n");
  writeFileSync(join(root, "scripts/lib/base44-pinned-cli.sh"), `
fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$TEST_CLI"; }
fixlist_require_base44_owner() { return 0; }
`);
  writeFileSync(join(root, "scripts/base44_release_manifest.mjs"),
    "export function assertPulledFunctionPackage() {}\n");
  writeFileSync(join(root, "scripts/deploy-base44-staged-functions.sh"), `
#!/usr/bin/env bash
[[ "$1" == verify ]] || exit 1
printf '%s\\n' '{"candidate_fingerprint":"2222222222222222","functions":[{"name":"startStandardScanJobV9","build_id":"${"1".repeat(64)}","runtime_activation_id":"v9-activation"}]}' > "$READINESS_OUTPUT"
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
      };
      return {
        success: true, schema_version: "fixlist_staged_v9_intake_readback_v1",
        observed_at: new Date().toISOString(), build_id: "1".repeat(64), runtime_activation_id: "v9-activation",
        release_fingerprint: "2".repeat(16), configured_pipeline_mode: "staged", pipeline_mode: "staged",
        staged_owner_cohort_state: "explicit", staged_owner_count: 1, staged_owner_cohort_sha256: "3".repeat(64),
        staged_owner_enabled: true, intake_gate: "enabled", admission_gate: "enabled",
      };
    } },
  };
  const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
  await new AsyncFunction("base44", readFileSync(0, "utf8"))(base44);
}
`);
  chmodSync(cli, 0o700);
  return (script, operation, selected, user) => {
    const confirm = {
      "prepare-owner": `PREPARE-BASE44-STAGED-150:${source}:${selected}`,
      "deploy-probe": `DEPLOY-BASE44-STAGED-PROBE:${source}`,
      disable: `DISABLE-BASE44-STAGED:${source}:${selected}`,
    }[operation] || "";
    const result = spawnSync("bash", [script], {
      cwd: root, encoding: "utf8", timeout: 15000,
      env: {
        ...process.env, BASE44_API_KEY: "", SOURCE_SHA: source, OPERATION: operation, CONFIRM: confirm,
        STAGED_OWNER_USER_ID: selected, EXPECTED_OWNER_USER_ID: selected, BASE44_OBSERVATIONS_DIR: output,
        TEST_CLI: cli, TEST_TRACE: trace, TEST_USER: JSON.stringify(user),
      },
    });
    const calls = existsSync(trace) ? readFileSync(trace, "utf8").trim().split("\n").map(JSON.parse) : [];
    return { ...result, calls, output };
  };
}

test("the new London staged cohort uses the signed-in app identity before any Base44 writes", t => {
  const result = fixture(t)(operator, "prepare-owner", london.id, london);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.calls.slice(0, 2), [["exec", "--data-env", "prod"], ["auth.me"]]);
  assert.equal(result.calls.filter(([name]) => name === "secrets").length, 2);
  assert.ok(result.calls.some(row => row.includes(`SCAN_STAGED_OWNER_IDS=${london.id}`)));
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

test("the collector reads V9 for the selected London app identity", t => {
  const result = fixture(t)(collector, "status", london.id, london);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.calls, [
    ["exec", "--data-env", "prod"], ["auth.me"], ["invoke", "startStandardScanJobV9", "staged_runtime_status"],
  ]);
  assert.equal(JSON.parse(readFileSync(join(result.output, "intake.json"), "utf8")).staged_owner_enabled, true);
});

test("the collector refuses a different app identity before any V9 call", t => {
  const result = fixture(t)(collector, "status", london.id, bright);
  assert.notEqual(result.status, 0);
  assert.deepEqual(result.calls, [["exec", "--data-env", "prod"], ["auth.me"]]);
  assert.equal(existsSync(join(result.output, "intake.json")), false);
});
