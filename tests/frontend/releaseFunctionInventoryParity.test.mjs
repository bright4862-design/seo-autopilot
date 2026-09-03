import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { RELEASE_FUNCTIONS } from "../../scripts/base44_release_manifest.mjs";

/**
 * The manifest, the publish script and the build-ID verifier must name the same
 * functions.
 *
 * They are hand-maintained lists of the same thing. A package added to the
 * manifest but not to the deploy script passes every local gate and is then
 * simply never deployed -- production keeps serving an app that has no such
 * function, and the failure only shows up as a customer-facing 404 at runtime.
 * A function deployed but absent from the verifier is worse: it is reported
 * published while the runtime may still serve an older compiled handler, which
 * is precisely how the 2026-08/09 Standard 150 outage stayed invisible.
 */

const DEPLOY = readFileSync(
  new URL("../../scripts/deploy-base44-beta-site.sh", import.meta.url),
  "utf8",
);
const VERIFIER = readFileSync(
  new URL("../../scripts/verify-base44-functions.sh", import.meta.url),
  "utf8",
);

function bashArray(source, name) {
  const open = source.indexOf(`${name}=(`);
  assert.ok(open >= 0, `${name} is missing`);
  const body = source.slice(open + `${name}=(`.length, source.indexOf(")", open));
  return body
    .split("\n")
    .map((line) => line.replace(/#.*$/, "").trim())
    .filter(Boolean);
}

const verified = bashArray(DEPLOY, "VERIFIED_FUNCTIONS");
const unverified = bashArray(DEPLOY, "UNVERIFIED_FUNCTIONS");

test("the deploy script names exactly the manifest's release functions", () => {
  assert.deepEqual([...verified, ...unverified], RELEASE_FUNCTIONS);
});

test("every deployed function is checked present in the post-deploy inventory", () => {
  // The loop iterates the composed array rather than a second hand-written
  // list, so a function cannot be deployed and left out of the check.
  assert.match(DEPLOY, /FUNCTIONS=\("\$\{VERIFIED_FUNCTIONS\[@\]\}" "\$\{UNVERIFIED_FUNCTIONS\[@\]\}"\)/);
  assert.match(DEPLOY, /for required in "\$\{FUNCTIONS\[@\]\}"; do/);
});

test("every function the deploy script calls verified is probed by the verifier", () => {
  const probed = bashArray(VERIFIER, "FUNCTION_PAIRS").map((pair) =>
    pair.replace(/^"|"$/g, "").split(":")[1],
  );
  assert.deepEqual(probed, verified);
});

test("the routes the customer path depends on are all in the verified set", () => {
  const routes = JSON.parse(
    readFileSync(new URL("../../data/base44-function-routes.json", import.meta.url), "utf8"),
  );
  assert.deepEqual(Object.values(routes.routes).sort(), [...verified].sort());
});
