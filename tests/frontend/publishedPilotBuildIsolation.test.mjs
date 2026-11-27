import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

function project(t) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "published-pilot-isolation-"));
  const root = path.join(temp, "checkout");
  fs.mkdirSync(root);
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const write = (name, content, mode) => {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, content, { mode });
  };
  const copy = name => write(name, fs.readFileSync(name));
  function run(command, args, env = {}) {
    return spawnSync(command, args, { cwd: root, encoding: "utf8", env: { ...process.env, ...env } });
  }
  return { temp, root, write, copy, run };
}

test("authenticated V9 readback can replace its own SDK without modifying release dependencies", t => {
  const { root, write, copy, run } = project(t);
  const sdk = "node_modules/@base44/sdk/package.json";
  write(sdk, '{"version":"0.8.63"}');
  for (const name of ["data/beta-crawler-revision.json", "data/generated-staged-v9-routes.json",
    "scripts/deploy-base44-staged-functions.sh"]) copy(name);
  write("fake-cli", `#!/bin/sh
set -eu
cat >/dev/null
test -f package.json
mkdir -p node_modules/@base44/sdk
echo '{"version":"0.8.39"}' >node_modules/@base44/sdk/package.json
echo BASE44_ACTIVE_V9_INTAKE_DISABLED
`, 0o755);
  const result = run("bash", ["-c", `
source scripts/deploy-base44-staged-functions.sh
FIXLIST_BASE44_CLI="$PWD/fake-cli"
fixlist_assert_active_v9_intake_closed "$PWD" test-app bright4862@gmail.com
`]);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(root, sdk))), { version: "0.8.63" });
});

test("pilot build uses only tracked source and a newly installed, lock-matched SDK", t => {
  const { root, temp, write, copy, run } = project(t);
  copy("scripts/build-published-pilot-site.sh");
  write("package-lock.json", JSON.stringify({ packages: { "node_modules/@base44/sdk": { version: "0.8.63" } } }));
  const git = args => execFileSync("git", args, { cwd: root });
  git(["init", "-q"]); git(["add", "."]);
  git(["-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"]);
  const sha = git(["rev-parse", "HEAD"]).toString().trim();
  write("node_modules/@base44/sdk/package.json", '{"version":"0.8.39"}');
  write("untracked.txt", "local");
  write("tools/npm", `#!/bin/sh
set -eu
test ! -e untracked.txt
if [ "$1" = ci ]; then
  test ! -e node_modules
  mkdir -p node_modules/@base44/sdk
  printf '{"version":"%s"}' "$FIXTURE_SDK" >node_modules/@base44/sdk/package.json
elif [ "$1 $2" = "run build" ]; then
  test "$VITE_SCAN_FUNCTION_GENERATION" = PUBLISHED_PILOT
  test "$VITE_FIXLIST_SOURCE_SHA" = "$FIXTURE_SHA"
  test "$VITE_BASE44_APP_ID" = 6a498732ec779dfaaeab0e53
  mkdir dist
  echo built >dist/index.html
else exit 1; fi
`, 0o755);
  const native = run("bash", ["scripts/build-published-pilot-site.sh", sha, "PUBLISHED_PILOT", path.join(temp, "native")], {
    VITE_BASE44_BUILD_COMMIT: "a".repeat(40),
  });
  assert.equal(native.status, 2);
  assert.match(native.stderr, /does not take a native hosting commit/);
  assert.equal(fs.existsSync(path.join(temp, "native")), false);
  for (const version of ["0.8.63", "0.8.39"]) {
    const destination = path.join(temp, version);
    const result = run("bash", ["scripts/build-published-pilot-site.sh", sha, "PUBLISHED_PILOT", destination], {
      PATH: path.join(root, "tools") + path.delimiter + process.env.PATH,
      FIXTURE_SDK: version, FIXTURE_SHA: sha,
    });
    assert.equal(result.status === 0, version === "0.8.63", result.stderr);
    assert.equal(fs.existsSync(path.join(destination, "dist/index.html")), version === "0.8.63");
  }
});

test("published intake resume checks the active pilot mode before setting intake", t => {
  const { temp, copy, write, run } = project(t);
  copy("scripts/set-base44-scan-intake.sh");
  write("scripts/lib/release-source-guard.sh", 'fixlist_require_exact_main() { FIXLIST_EXACT_SOURCE_SHA="$SOURCE_SHA"; }');
  write("scripts/lib/base44-pinned-cli.sh", 'fixlist_install_base44_cli() { FIXLIST_BASE44_CLI="$PWD/fake-cli"; }\nfixlist_require_base44_owner() { true; }');
  write("scripts/verify-base44-scan-intake-runtime.sh", 'echo "readback $ACTION" >>"$TRACE"');
  write("scripts/verify-base44-site.sh", 'echo "$1 $2" >>"$TRACE"\n[[ "$STALE" != yes ]]');
  write("fake-cli", '#!/bin/sh\necho "$*" >>"$TRACE"\n', 0o755);
  for (const [generation, mode] of [["v8", "PUBLISHED_PILOT"], ["v9", "PAID_PILOT"]]) {
    write("data/base44-function-routes.json", JSON.stringify({ generation }));
    for (const stale of [true, false]) {
      const trace = path.join(temp, generation + stale);
      const sha = "a".repeat(40);
      const result = run("bash", ["scripts/set-base44-scan-intake.sh"], {
        ACTION: "resume-published-pilot", SOURCE_SHA: sha,
        CONFIRM: "RESUME-PUBLISHED-PILOT-SCAN-INTAKE:" + sha, TRACE: trace, STALE: stale ? "yes" : "",
      });
      assert.equal(result.status === 0, !stale, result.stderr);
      const events = fs.readFileSync(trace, "utf8").trim().split("\n");
      assert.equal(events[0], "--published-pilot " + mode);
      if (stale) assert.equal(events.length, 1);
      else assert.deepEqual(events.slice(1), ["--app-id 6a498732ec779dfaaeab0e53 secrets set BETA_SCAN_INTAKE_ENABLED=true", "readback resume"]);
    }
  }
});
