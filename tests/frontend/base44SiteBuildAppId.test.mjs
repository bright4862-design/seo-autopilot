import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { transformSync } from "esbuild";
import test from "node:test";

const deploy = readFileSync("scripts/deploy-base44-beta-site.sh", "utf8");
const appParams = readFileSync("src/lib/app-params.js", "utf8");
const appId = "6a498732ec779dfaaeab0e53";
const sourceSha = "1111111111111111111111111111111111111111";

function captureBuildEnvironment({ targetAppId = appId, ambientAppId } = {}) {
  // Execute the release script's real build command in bash. Only npm is
  // intercepted: no CLI authentication, function deployment or site mutation.
  const commands = deploy.split("\n").filter((line) =>
    !line.trim().startsWith("#") && /\bnpm run build\s*$/.test(line));
  assert.equal(commands.length, 1, "release must have one identifiable build boundary");
  const env = { ...process.env, APP_ID: targetAppId, SOURCE_SHA: sourceSha,
    FIXLIST_TEST_NODE: process.execPath };
  delete env.VITE_BASE44_APP_ID;
  delete env.VITE_FIXLIST_SOURCE_SHA;
  if (ambientAppId !== undefined) env.VITE_BASE44_APP_ID = ambientAppId;
  const command = `npm() {
    test "$#" -eq 2 && test "$1" = run && test "$2" = build || return 70
    "$FIXLIST_TEST_NODE" -e 'process.stdout.write(JSON.stringify({appId:process.env.VITE_BASE44_APP_ID ?? null,sourceSha:process.env.VITE_FIXLIST_SOURCE_SHA ?? null}))'
  }
  ${commands[0]}`;
  return JSON.parse(execFileSync("bash", ["-e", "-c", command], { env, encoding: "utf8" }));
}

function evaluateFreshVisitor(build) {
  // Transpile the actual client parameter module using the values received
  // by the build. Empty storage and no query parameters model a first visit.
  const compiled = transformSync(appParams, {
    loader: "js", format: "cjs", target: "es2022",
    define: {
      "import.meta.env.VITE_BASE44_APP_ID": build.appId === null ? "undefined" : JSON.stringify(build.appId),
      "import.meta.env.VITE_BASE44_APP_BASE_URL": "undefined",
    },
  }).code;
  const saved = new Map();
  const localStorage = {
    getItem: (key) => saved.get(key) ?? null,
    setItem: (key, value) => saved.set(key, String(value)),
    removeItem: (key) => saved.delete(key),
  };
  const context = {
    module: { exports: {} }, URLSearchParams, document: { title: "FixList" },
    window: { localStorage,
      location: { search: "", pathname: "/", hash: "", href: "https://getfixlist.com/" },
      history: { replaceState() {} } },
  };
  runInNewContext(compiled, context, { timeout: 1000 });
  return context.module.exports.appParams;
}

test("release build configures a first-time visitor without cached app identity", () => {
  const build = captureBuildEnvironment();
  assert.equal(build.sourceSha, sourceSha, "the exact release SHA must still reach Vite");
  assert.equal(build.appId, appId, "the deployment app ID must reach Vite without external env setup");
  const visitor = evaluateFreshVisitor(build);
  assert.equal(visitor.appId, appId);
  assert.equal(visitor.token, null, "a clean visitor must not need an existing owner session");
});

test("release build cannot inherit an app ID belonging to another deployment", () => {
  const build = captureBuildEnvironment({ ambientAppId: "aaaaaaaaaaaaaaaaaaaaaaaa" });
  assert.equal(build.appId, appId);
  assert.equal(evaluateFreshVisitor(build).appId, appId);
});

test("release build uses the resolved deployment APP_ID rather than a second hardcoded app", () => {
  const targetAppId = "bbbbbbbbbbbbbbbbbbbbbbbb";
  const build = captureBuildEnvironment({ targetAppId });
  assert.equal(build.appId, targetAppId);
  assert.equal(evaluateFreshVisitor(build).appId, targetAppId);
});
