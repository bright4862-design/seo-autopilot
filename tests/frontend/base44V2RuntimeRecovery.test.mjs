import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import test from "node:test";

const SCRIPT = "scripts/recover-base44-stale-v2-runtime.sh";
const VERIFIER = "scripts/verify-base44-functions.sh";
const CANONICAL_RECOVERY = "scripts/recover-base44-stale-release-functions.sh";
const WORKFLOW = ".github/workflows/fixlist-base44-v2-runtime-recovery.yml";

const recovery = fs.readFileSync(SCRIPT, "utf8");
const verifier = fs.readFileSync(VERIFIER, "utf8");

/**
 * Base44 synchronized the V2 function definitions and never recompiled the
 * handlers.
 *
 * All six V2 URLs kept executing the packages they were first created with, and
 * `functions deploy` reported them "unchanged", so publication failed at the
 * runtime gate with no redeploy able to move it.
 *
 * The check that failed to catch it is the interesting part. A V2 package is
 * stamped with the build identity of the canonical package it mirrors, so its
 * expected build ID moves only when the canonical moves. The activation refresh
 * touched the V2 entry files alone. Five canonicals happened to change for
 * other reasons; deleteCustomerScanData did not -- so deleteCustomerScanDataV2's
 * expected build ID is still exactly the one its stale handler serves, and a
 * build-only check calls that route current while it runs canonical-era code.
 *
 * Every case below is built from the real build IDs and the real 405 bodies,
 * because a fixture that invents either would prove the classifier works on
 * responses production never sends.
 */

const EXPECTED_BUILD = Object.fromEntries(
  ["startStandardScanJobV2", "durableScanWorkerControlV2", "persistDurableScanAuthorityV2",
    "persistLimitedScanResultV2", "getCustomerScanResultV2", "deleteCustomerScanDataV2"]
    .map((name) => [name, execFileSync("node",
      ["scripts/generate_release_contracts.mjs", "--build-id", name], { encoding: "utf8" }).trim()]),
);
const V2_ACTIVATION = Object.fromEntries(Object.keys(EXPECTED_BUILD).map((name) => [name,
  execFileSync("node", ["scripts/generate_release_contracts.mjs", "--activation-id", name], { encoding: "utf8" }).trim()]));
const CANONICAL_ACTIVATION = Object.fromEntries(Object.keys(EXPECTED_BUILD).map((name) => [name,
  execFileSync("node", ["scripts/generate_release_contracts.mjs", "--activation-id", name.replace(/V2$/, "")], { encoding: "utf8" }).trim()]));

/** The build IDs the six V2 routes were actually observed serving. */
const LIVE_BUILD = {
  startStandardScanJobV2: "37f0fae80c81223a892a233fd9cfdf32902f43cecf8fe3819a1c2e9d55ecfd8d",
  durableScanWorkerControlV2: "0fe23e0d7e53982b59d5bc2edc419b4568dcd063efa223ab0cdbecc9a5345f0b",
  persistDurableScanAuthorityV2: "6cf9bd3b0eaa3da07da8171e237dd921242ed14edecef3421bdacd019abef1db",
  persistLimitedScanResultV2: "62978e16e20791c205e01f58bffd2b2e5dc39067be13939b8eb08cce6a5f1ecb",
  getCustomerScanResultV2: "697d83e9d06c03bde76202c5ebd23408098e4fc8a773761783783298496be1f2",
  deleteCustomerScanDataV2: "6f6c73c198d7a20df923721d826c994f4d8d40decec0ecd313e8f9992f12f481",
};

/** The exact 405 JSON each route's handler returns, by canonical package. */
function staleBody(name, buildId, activationId) {
  if (name === "startStandardScanJobV2") {
    return JSON.stringify({
      success: false, version: "startStandardScanJob_v3_server_admission",
      build_id: buildId, runtime_activation_id: activationId, error: "Method not allowed.",
    });
  }
  const message = {
    durableScanWorkerControlV2: "Use POST for durable worker control.",
    persistDurableScanAuthorityV2: "Use POST to persist durable scan authority.",
    getCustomerScanResultV2: "Use POST to load a saved scan.",
    deleteCustomerScanDataV2: "Use POST to manage saved scan history.",
  }[name];
  if (name === "persistLimitedScanResultV2") {
    return JSON.stringify({
      success: false, error_code: "method_not_allowed",
      error_message: "Use POST to persist a limited scan result.",
      build_id: buildId, runtime_activation_id: activationId,
    });
  }
  return JSON.stringify({
    success: false, error_code: "method_not_allowed", error: message,
    build_id: buildId, runtime_activation_id: activationId,
  });
}

/**
 * Ask the script itself how it classifies one probed response: "current",
 * "stale", or "refuse". Sourcing it in library mode runs no recovery.
 */
function classify(name, { status = 405, body, buildId, activationId }) {
  const out = execFileSync("bash", ["-c", [
    'FIXLIST_V2_RUNTIME_RECOVERY_LIB_ONLY=1 source "$0"',
    'resolve_expectations "$1" >/dev/null 2>&1 || { echo resolve-refused; exit 0; }',
    'PROBE_STATUS="$2"',
    'PROBE_BODY="$3"',
    'PROBE_BUILD_ID="$4"',
    'PROBE_ACTIVATION_ID="$5"',
    'if route_reaches_json_handler && route_serves_expected_runtime "$V2_EXPECTED_BUILD" "$V2_EXPECTED_ACTIVATION"; then echo current',
    'elif route_is_known_stale_v2 "$1" "$V2_CANONICAL" "$V2_CANONICAL_ACTIVATION"; then echo stale',
    'else echo refuse',
    'fi',
  ].join("; "), SCRIPT, name, String(status), body ?? "", buildId ?? "", activationId ?? ""],
  { encoding: "utf8" });
  return out.trim();
}

// ------------------------------------------------ the case that got through --

test("a matching build ID with a stale activation marker is not current", () => {
  // deleteCustomerScanDataV2, exactly as observed: the build ID a build-only
  // check demands, serving canonical-era code.
  const name = "deleteCustomerScanDataV2";
  assert.equal(LIVE_BUILD[name], EXPECTED_BUILD[name],
    "this fixture only means something while the live and expected build IDs agree");
  assert.notEqual(V2_ACTIVATION[name], CANONICAL_ACTIVATION[name]);

  const verdict = classify(name, {
    body: staleBody(name, LIVE_BUILD[name], CANONICAL_ACTIVATION[name]),
    buildId: LIVE_BUILD[name],
    activationId: CANONICAL_ACTIVATION[name],
  });
  assert.equal(verdict, "stale", "a build-only check calls this route current");
});

test("the same route with its own activation marker is current and untouched", () => {
  const name = "deleteCustomerScanDataV2";
  const verdict = classify(name, {
    body: staleBody(name, EXPECTED_BUILD[name], V2_ACTIVATION[name]),
    buildId: EXPECTED_BUILD[name],
    activationId: V2_ACTIVATION[name],
  });
  assert.equal(verdict, "current");
});

test("five routes are caught by the build ID and the sixth only by the marker", () => {
  // The distribution that made this hard to see: most of the fleet fails the
  // cheap check, so the one that does not looks like a healthy route.
  const byBuild = [];
  const byMarkerOnly = [];
  for (const name of Object.keys(EXPECTED_BUILD)) {
    (LIVE_BUILD[name] === EXPECTED_BUILD[name] ? byMarkerOnly : byBuild).push(name);
    assert.equal(
      classify(name, {
        body: staleBody(name, LIVE_BUILD[name], CANONICAL_ACTIVATION[name]),
        buildId: LIVE_BUILD[name],
        activationId: CANONICAL_ACTIVATION[name],
      }),
      "stale",
      `${name} was not recognized as stale`,
    );
  }
  assert.equal(byBuild.length, 5);
  assert.deepEqual(byMarkerOnly, ["deleteCustomerScanDataV2"]);
});

test("every current route is skipped rather than deleted", () => {
  for (const name of Object.keys(EXPECTED_BUILD)) {
    assert.equal(
      classify(name, {
        body: staleBody(name, EXPECTED_BUILD[name], V2_ACTIVATION[name]),
        buildId: EXPECTED_BUILD[name],
        activationId: V2_ACTIVATION[name],
      }),
      "current",
      `${name} would be deleted while already correct`,
    );
  }
});

// ------------------------------------------- anything unrecognized refuses --

test("a response this script cannot account for is never deleted", () => {
  const name = "getCustomerScanResultV2";
  const build = LIVE_BUILD[name];
  const canonical = CANONICAL_ACTIVATION[name];
  const good = staleBody(name, build, canonical);

  const cases = [
    ["transport failure", { status: 0, body: "", buildId: "", activationId: "" }],
    ["router 404", { status: 404, body: JSON.stringify({ error: "Not found" }) }],
    ["edge HTML", { status: 502, body: "<html><body>Bad Gateway</body></html>" }],
    ["worker missing", { status: 500, body: JSON.stringify({ error: "user worker not found" }) }],
    ["malformed JSON", { status: 405, body: "{not json", buildId: build, activationId: canonical }],
    ["JSON array", { status: 405, body: "[]", buildId: build, activationId: canonical }],
    ["unexpected status", { status: 200, body: good, buildId: build, activationId: canonical }],
    ["missing build id", { status: 405, body: staleBody(name, "", canonical), buildId: "", activationId: canonical }],
    ["missing activation", { status: 405, body: staleBody(name, build, ""), buildId: build, activationId: "" }],
    ["unknown activation", { status: 405, body: staleBody(name, build, "who-knows-v9"), buildId: build, activationId: "who-knows-v9" }],
    ["truncated build id", { status: 405, body: good, buildId: build.slice(0, 32), activationId: canonical }],
    ["another function's 405", { status: 405, body: staleBody("durableScanWorkerControlV2", build, canonical), buildId: build, activationId: canonical }],
    // An edge that echoes the handler's own body back inside its error. Only
    // the reaches-a-real-handler check rejects this; the signature match and
    // both identities are present and correct.
    ["edge echo of a real handler", {
      status: 405,
      body: JSON.stringify({
        error: "user worker not found",
        upstream: JSON.parse(staleBody(name, build, canonical)),
        success: false, error_code: "method_not_allowed",
        build_id: build, runtime_activation_id: canonical,
      }).replace('"error":"user worker not found"', '"error":"Use POST to load a saved scan.","edge":"user worker not found"'),
      buildId: build, activationId: canonical,
    }],
  ];
  for (const [label, probe] of cases) {
    assert.equal(classify(name, probe), "refuse", `${label} was treated as recoverable`);
  }
});

test("a half-recovered handler — new build, old marker — still refuses", () => {
  // Neither current nor the proven stale signature. Deleting on a state nobody
  // has characterised is how a recovery makes things worse than it found them.
  const name = "startStandardScanJobV2";
  assert.equal(classify(name, {
    body: staleBody(name, EXPECTED_BUILD[name], CANONICAL_ACTIVATION[name]),
    buildId: EXPECTED_BUILD[name],
    activationId: CANONICAL_ACTIVATION[name],
  }), "stale", "old marker with a current build is the stale signature for this route");

  assert.equal(classify(name, {
    body: staleBody(name, LIVE_BUILD[name], V2_ACTIVATION[name]),
    buildId: LIVE_BUILD[name],
    activationId: V2_ACTIVATION[name],
  }), "refuse", "a new marker on an old build is a state this script has not proven safe");
});

test("an unknown function name resolves to nothing and recovers nothing", () => {
  assert.equal(classify("someOtherFunctionV2", { body: "{}", buildId: "", activationId: "" }), "resolve-refused");
});

test("expectations that cannot discriminate are refused before any probe", () => {
  // resolve_expectations is where the recovery decides it is able to tell a
  // stale route from a current one. If the two markers were ever equal, or
  // either were malformed, every later comparison would be meaningless -- so it
  // refuses there rather than probing and guessing. The resolvers are replaced
  // after sourcing, because no real package can be put into these states.
  const withResolver = (bodyOfResolver) => execFileSync("bash", ["-c", [
    'FIXLIST_V2_RUNTIME_RECOVERY_LIB_ONLY=1 source "$0"',
    `expected_activation_id() { ${bodyOfResolver}; }`,
    'if resolve_expectations startStandardScanJobV2 >/dev/null 2>&1; then echo accepted; else echo refused; fi',
  ].join("; "), SCRIPT], { encoding: "utf8" }).trim();

  assert.equal(withResolver('echo "identical-marker-v1"'), "refused",
    "identical V2 and canonical markers cannot prove staleness");

  // Malformed on the V2 side only. Returning the same bad value for both would
  // make them identical, and the guard above would refuse for that reason
  // instead -- leaving the well-formedness checks never exercised.
  const onlyV2Malformed = (bad) =>
    `case "$1" in *V2) printf '%s' ${bad};; *) printf '%s' "canonical-marker-v1";; esac`;
  assert.equal(withResolver(onlyV2Malformed('"has a space"')), "refused",
    "a malformed V2 marker is not usable");
  assert.equal(withResolver(onlyV2Malformed('""')), "refused", "an empty V2 marker is not usable");
  assert.equal(withResolver(onlyV2Malformed('"$(printf "%0121d" 0 | tr 0 a)"')), "refused",
    "an over-long V2 marker is not usable");

  // And malformed on the canonical side only, which is what the stale
  // comparison is made against.
  const onlyCanonicalMalformed =
    `case "$1" in *V2) printf '%s' "v2-marker-v1";; *) printf '%s' "also has a space";; esac`;
  assert.equal(withResolver(onlyCanonicalMalformed), "refused",
    "a malformed canonical marker is not usable");

  // The real resolvers do discriminate, so the guard is not simply always-on.
  assert.equal(
    execFileSync("bash", ["-c", [
      'FIXLIST_V2_RUNTIME_RECOVERY_LIB_ONLY=1 source "$0"',
      'if resolve_expectations startStandardScanJobV2 >/dev/null 2>&1; then echo accepted; else echo refused; fi',
    ].join("; "), SCRIPT], { encoding: "utf8" }).trim(),
    "accepted",
  );
});

test("a route already current is never handed to the CLI", () => {
  // The strongest form of "skipped": run the real recover_one_v2 against a
  // stubbed probe and a recording CLI, and assert nothing was invoked. Reading
  // the source for a skip branch would pass even if the branch fell through.
  const out = execFileSync("bash", ["-c", [
    'set -uo pipefail',
    'log="$(mktemp)"',
    'cli="$(mktemp)"',
    'printf \'#!/usr/bin/env bash\\necho "$@" >> "$FIXLIST_TEST_CLI_LOG"\\n\' > "$cli"',
    'chmod +x "$cli"',
    'FIXLIST_V2_RUNTIME_RECOVERY_LIB_ONLY=1 source "$0"',
    'export FIXLIST_TEST_CLI_LOG="$log"',
    'FIXLIST_BASE44_CLI="$cli"',
    'remote_inventory() { echo "$1"; }',
    'resolve_expectations deleteCustomerScanDataV2',
    'probe_v2_route() { PROBE_STATUS=405; PROBE_BODY="{\\"success\\":false,\\"error_code\\":\\"method_not_allowed\\",\\"error\\":\\"Use POST to manage saved scan history.\\"}"; PROBE_BUILD_ID="$V2_EXPECTED_BUILD"; PROBE_ACTIVATION_ID="$V2_EXPECTED_ACTIVATION"; }',
    'recover_one_v2 deleteCustomerScanDataV2 >/dev/null',
    'printf "calls=%s" "$(wc -l < "$log" | tr -d " ")"',
  ].join("; "), SCRIPT], { encoding: "utf8" }).trim();
  assert.equal(out, "calls=0", "a current route reached the Base44 CLI");
});

// ------------------------------------------------------------ the sequence --

test("all six are classified before any one is deleted", () => {
  const preflightLoop = recovery.slice(
    recovery.indexOf("for fn in \"${V2_FUNCTIONS[@]}\"; do\n  require_recoverable_v2_prestate"),
  );
  assert.ok(preflightLoop.startsWith("for fn in"), "the preflight loop must exist");
  assert.ok(
    recovery.indexOf("require_recoverable_v2_prestate \"$fn\"")
      < recovery.indexOf("recover_one_v2 \"$fn\""),
    "a deletion must not precede the full preflight",
  );
  assert.ok(
    recovery.indexOf("BASE44_V2_RUNTIME_PREFLIGHT_VERIFIED") < recovery.indexOf("RECOVERED=0"),
    "the preflight must be declared complete before recovery starts",
  );
  // And the preflight itself never mutates.
  const preflight = recovery.slice(recovery.indexOf("require_recoverable_v2_prestate() {"),
    recovery.indexOf("recover_one_v2() {"));
  assert.doesNotMatch(preflight, /functions delete|functions deploy/);
});

test("each route proves absence after delete and presence after deploy", () => {
  const body = recovery.slice(recovery.indexOf("recover_one_v2() {"), recovery.indexOf("\nif [[ -n \"${FIXLIST_V2"));
  const deleteAt = body.indexOf("functions delete");
  const deployAt = body.indexOf("functions deploy");
  assert.ok(deleteAt > -1 && deployAt > deleteAt);

  const afterDelete = body.slice(deleteAt, deployAt);
  assert.match(afterDelete, /if inventory_contains "\$inventory" "\$name"; then/);
  assert.match(afterDelete, /still present after delete/);

  const afterDeploy = body.slice(deployAt);
  assert.match(afterDeploy, /if ! inventory_contains "\$inventory" "\$name"; then/);
  assert.match(afterDeploy, /did not reappear after deploy/);
  assert.match(afterDeploy, /require_expected_v2_runtime/);

  // Membership is confirmed before the delete, too.
  assert.match(body.slice(0, deleteAt), /absent from remote inventory/);
});

test("a failure on one route stops before the next is touched", () => {
  assert.match(recovery, /^set -euo pipefail$/m);
  const body = recovery.slice(recovery.indexOf("recover_one_v2() {"), recovery.indexOf("\nif [[ -n \"${FIXLIST_V2"));
  // Every guard returns non-zero rather than continuing, and `set -e` turns
  // that into a stop at the call site in the loop.
  for (const guard of ["still present after delete", "did not reappear after deploy",
    "absent from remote inventory", "pre-state does not match"]) {
    const at = body.indexOf(guard);
    assert.ok(at > -1, `${guard} guard is missing`);
    assert.match(body.slice(at, at + 200), /return 1/, `${guard} does not stop the run`);
  }
});

test("the run ends by re-verifying all six, not by trusting the loop", () => {
  const tail = recovery.slice(recovery.indexOf("RECOVERED=0"));
  const finalLoop = tail.slice(tail.indexOf("for fn in \"${V2_FUNCTIONS[@]}\"; do", tail.indexOf("recover_one_v2 \"$fn\"")));
  assert.match(finalLoop, /require_expected_v2_runtime "\$fn"/);
  assert.ok(tail.indexOf("BASE44_V2_RUNTIME_RECOVERED") > tail.lastIndexOf("require_expected_v2_runtime"));
});

// ------------------------------------------------------------ the guards --

test("recovery refuses without exact main, owner session, and confirmation", () => {
  // The main body, after the library-only early return. Matching the whole file
  // would pass on the function definitions alone, with neither ever called.
  const mainBody = recovery.slice(recovery.indexOf('if [[ -n "${FIXLIST_V2_RUNTIME_RECOVERY_LIB_ONLY:-}" ]]; then'));
  assert.match(mainBody, /^require_owner_session_mode$/m);
  assert.match(mainBody, /^require_v2_action_confirmation$/m);
  assert.match(mainBody, /^fixlist_require_exact_main /m);
  assert.match(recovery, /fixlist_require_exact_main "\$REPO_ROOT" "\$SOURCE_SHA" "\$CONFIRM"/);
  assert.match(recovery, /EXPECTED_ACTION_CONFIRM="RECREATE-STALE-BASE44-V2-RUNTIME"/);
  assert.match(recovery, /generate_release_contracts\.mjs" --check/);
  assert.match(recovery, /base44_release_manifest\.mjs" verify/);
  assert.match(recovery, /fixlist_require_base44_owner/);
});

test("the destructive confirmation is distinct from the canonical recovery's", () => {
  // Read from a sourced shell, not from the file text. This script sources the
  // canonical recovery to reuse its classification, and that script assigns
  // EXPECTED_ACTION_CONFIRM unconditionally -- so the phrase written here was
  // being replaced at runtime by the canonical one while a source-text
  // assertion went on passing. Sharing a phrase would let an operator holding
  // authorisation for one destructive run trigger the other.
  const runtimeValue = (script, variable) => execFileSync("bash", ["-c",
    `FIXLIST_STALE_RECOVERY_LIB_ONLY=1 FIXLIST_V2_RUNTIME_RECOVERY_LIB_ONLY=1 source "$0"; printf %s "\${${variable}}"`,
    script], { encoding: "utf8" }).trim();

  const ours = runtimeValue(SCRIPT, "V2_EXPECTED_ACTION_CONFIRM");
  const theirs = runtimeValue(CANONICAL_RECOVERY, "EXPECTED_ACTION_CONFIRM");
  assert.equal(ours, "RECREATE-STALE-BASE44-V2-RUNTIME");
  assert.notEqual(ours, theirs);

  // And the guard compares against that variable, not the clobbered one.
  const guard = recovery.slice(recovery.indexOf("require_v2_action_confirmation() {"));
  assert.match(guard.slice(0, guard.indexOf("\n}")), /"\$ACTION_CONFIRM" != "\$V2_EXPECTED_ACTION_CONFIRM"/);
});

test("nothing this script relies on is clobbered by the recovery it sources", () => {
  // The bug above was one variable; the shape of it is general. Every constant
  // this script depends on must survive sourcing the canonical recovery.
  const probe = execFileSync("bash", ["-c", [
    'FIXLIST_V2_RUNTIME_RECOVERY_LIB_ONLY=1 source "$0"',
    'printf "%s|%s|%s" "$V2_EXPECTED_ACTION_CONFIRM" "$PROBE_ATTEMPTS" "${V2_FUNCTIONS[0]}"',
  ].join("; "), SCRIPT], { encoding: "utf8" }).trim().split("|");
  assert.deepEqual(probe, ["RECREATE-STALE-BASE44-V2-RUNTIME", "12", "startStandardScanJobV2"]);
});

test("recovery touches nothing outside Base44 functions", () => {
  const forbidden = [
    /gcloud/, /\brun deploy\b/, /update-traffic/, /\bkubectl\b/,
    /deploy-base44-beta-site/, /functions deploy .*--site/,
    /secrets?\s+(create|update|versions)/, /\bgsutil\b/,
    /set-standard150-/, /admission/, /\biam\b/i, /entities?\s+deploy/,
    /npm run build/, /firebase/,
  ];
  // Comments are stripped first: the header deliberately lists the subsystems
  // this script must not touch, and matching on that would be matching the
  // promise rather than the behaviour.
  const executable = recovery
    .split("\n")
    .filter((line) => !/^\s*#/.test(line))
    .join("\n");
  for (const pattern of forbidden) {
    assert.doesNotMatch(executable, pattern, `recovery reaches outside function recompilation: ${pattern}`);
  }
  // The only CLI verbs this script issues itself are the two that recompile a
  // function. Reading the inventory is delegated to the shared helper, so the
  // whole surface here is delete + deploy.
  const verbs = [...recovery.matchAll(/\$FIXLIST_BASE44_CLI"[^\n]*?functions (\w+)/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(verbs)].sort(), ["delete", "deploy"]);
  assert.match(recovery, /inventory="\$\(remote_inventory\)"/, "membership is read, not assumed");
});

// ------------------------------------------------- the verifier it feeds --

test("runtime verification demands both identities", () => {
  assert.match(verifier, /--build-id "\$name"/, "the build ID resolves through the alias table");
  assert.match(verifier, /--activation-id "\$name"/);
  assert.match(verifier, /"\$actual" == "\$expected" && "\$actual_activation" == "\$expected_activation"/);
  assert.match(verifier, /FUNCTION_RUNTIME_VERIFIED/);
  // A body carrying only one of the two is not enough to pass.
  assert.match(verifier, /if \(!\/\^\[A-Za-z0-9\._-\]\{1,120\}\$\/\.test\(activationId\)\) process\.exit\(5\)/);
});

test("the verifier probes exactly the six live routes", () => {
  const listed = verifier.slice(verifier.indexOf("FUNCTION_ROUTES=("), verifier.indexOf(")", verifier.indexOf("FUNCTION_ROUTES=(")))
    .split("\n").slice(1).map((line) => line.trim()).filter(Boolean);
  assert.deepEqual(listed.sort(), Object.keys(EXPECTED_BUILD).sort());
});

test("build IDs resolve through the alias and activation markers do not", () => {
  // The asymmetry the whole fix rests on. If --activation-id resolved through
  // the alias too, both routes would report the canonical marker and the pair
  // would stop discriminating.
  for (const name of Object.keys(EXPECTED_BUILD)) {
    const canonical = name.replace(/V2$/, "");
    assert.equal(
      EXPECTED_BUILD[name],
      execFileSync("node", ["scripts/generate_release_contracts.mjs", "--build-id", canonical], { encoding: "utf8" }).trim(),
      `${name} must share its canonical's build ID`,
    );
    assert.notEqual(V2_ACTIVATION[name], CANONICAL_ACTIVATION[name],
      `${name} must not share its canonical's activation marker`);
  }
});

// ---------------------------------------------------------- the workflow --

test("the recovery workflow is owner-gated, exact-main, and read-only to the repo", () => {
  const workflow = fs.readFileSync(WORKFLOW, "utf8");
  assert.match(workflow, /github\.actor == 'bright4862-design'/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /github\.event_name == 'workflow_dispatch'/);
  assert.match(workflow, /permissions:\s*\n\s*contents: read/);
  assert.match(workflow, /persist-credentials: false/);
  assert.match(workflow, /RECREATE-STALE-BASE44-V2-RUNTIME/);
  assert.match(workflow, /environment: fixlist-production-owner/);
  assert.match(workflow, /rm -rf "\$HOME\/\.base44"/, "the owner session must not outlive the run");
  // It shares the hosted-controls concurrency group, so it cannot run beside a
  // publish or the canonical recovery.
  assert.match(workflow, /group: fixlist-base44-hosted-controls-v2/);
});

test("the publication path verifies the runtime and this does not bypass it", () => {
  // The publish workflow runs deploy-base44-beta-site.sh, and that script is
  // where the runtime gate lives -- before and after the site goes out.
  const publish = fs.readFileSync(".github/workflows/fixlist-base44-release-publish.yml", "utf8");
  assert.match(publish, /deploy-base44-beta-site\.sh/);
  const siteDeploy = fs.readFileSync("scripts/deploy-base44-beta-site.sh", "utf8");
  const gates = [...siteDeploy.matchAll(/verify-base44-functions\.sh/g)];
  assert.ok(gates.length >= 1, "publication must still prove the runtime before the site goes out");

  const workflow = fs.readFileSync(WORKFLOW, "utf8");
  assert.doesNotMatch(workflow, /deploy-base44-beta-site|verify-base44-site/,
    "recovery must not publish the site itself");
  // Recovery runs the same gate, so it cannot report success on routes the
  // publication path would then reject. This has to match the step that
  // executes it -- an earlier step merely syntax-checks the same filename, so
  // a bare filename match passes with the verification step deleted.
  assert.match(workflow, /^\s*run: \/bin\/bash scripts\/verify-base44-functions\.sh$/m);
});
