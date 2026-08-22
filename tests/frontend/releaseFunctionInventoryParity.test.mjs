import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { RELEASE_FUNCTIONS } from "../../scripts/base44_release_manifest.mjs";

/**
 * The manifest and the publish script must name the same functions.
 *
 * They are two hand-maintained lists of the same thing. A package added to the
 * manifest but not to the deploy script passes every local gate and is then
 * simply never deployed -- production keeps serving an app that has no such
 * function, and the failure only shows up as a customer-facing 404 at runtime.
 */

const DEPLOY = readFileSync(
  new URL("../../scripts/deploy-base44-beta-site.sh", import.meta.url),
  "utf8",
);

test("every release function is in the deploy list", () => {
  const list = DEPLOY.slice(DEPLOY.indexOf("FUNCTIONS=("), DEPLOY.indexOf(")", DEPLOY.indexOf("FUNCTIONS=(")));
  const declared = list.split("\n").map((line) => line.trim()).filter((line) => line && !line.startsWith("FUNCTIONS"));

  assert.deepEqual(declared, RELEASE_FUNCTIONS);
});

test("every release function is verified in the post-deploy inventory check", () => {
  const check = DEPLOY.slice(DEPLOY.indexOf("for required in"), DEPLOY.indexOf("\ndo", DEPLOY.indexOf("for required in")));
  for (const fn of RELEASE_FUNCTIONS) {
    assert.ok(check.includes(fn), `${fn} is deployed but never verified present afterwards`);
  }
});
