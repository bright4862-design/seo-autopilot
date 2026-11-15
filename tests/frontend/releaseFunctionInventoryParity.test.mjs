import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

import { RELEASE_FUNCTIONS } from "../../scripts/base44_release_manifest.mjs";
import stagedRoutes from "../../data/generated-staged-v9-routes.json" with { type: "json" };

/**
 * Standard 150 keeps its deterministic guarded release inventory separate from
 * workflow-backed publishers. Base44 apps with Workflows enabled reject legacy
 * automation deployment through `functions deploy`, so those publishers must
 * not be added to the Standard 150 post-site function reconciliation list.
 */

const DEPLOY = readFileSync(
  new URL("../../scripts/deploy-base44-beta-site.sh", import.meta.url),
  "utf8",
);
const VERIFIER = readFileSync(
  new URL("../../scripts/verify-base44-functions.sh", import.meta.url),
  "utf8",
);
const BLOG_SCHEMA = JSON.parse(
  readFileSync(new URL("../../base44/entities/BlogPost.jsonc", import.meta.url), "utf8"),
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

const resolver = "scripts/lib/base44-public-routes.mjs";
const [generation, ...verified] = execFileSync(process.execPath, [resolver], { encoding: "utf8" }).trim().split(" ");
const unverified = bashArray(DEPLOY, "UNVERIFIED_FUNCTIONS");
const deployed = [...verified, ...unverified];

test("the guarded site deploy preserves the Standard 150 V8 release inventory", () => {
  assert.deepEqual(deployed.filter((name) => !/V9B[0-9a-f]{16}$/.test(name)), RELEASE_FUNCTIONS);
});

test("workflow-backed blog publisher is not sent through legacy functions deploy", () => {
  assert.ok(
    !deployed.includes("generateDailyBlog"),
    "generateDailyBlog must stay out of guarded legacy functions deploy when Workflows are enabled",
  );
});

test("the BlogPost schema is public-read and admin-write", () => {
  assert.equal(BLOG_SCHEMA.name, "BlogPost");
  assert.equal(BLOG_SCHEMA.rls?.read, true);
  assert.deepEqual(BLOG_SCHEMA.rls?.create, { user_condition: { role: "admin" } });
  assert.deepEqual(BLOG_SCHEMA.rls?.update, { user_condition: { role: "admin" } });
  assert.deepEqual(BLOG_SCHEMA.rls?.delete, { user_condition: { role: "admin" } });
});

test("every deployed function is checked present in the post-deploy inventory", () => {
  assert.match(DEPLOY, /FUNCTIONS=\("\$\{VERIFIED_FUNCTIONS\[@\]\}" "\$\{UNVERIFIED_FUNCTIONS\[@\]\}"\)/);
  assert.match(DEPLOY, /for required in "\$\{FUNCTIONS\[@\]\}"; do/);
});

test("every function the deploy script calls verified is probed by the verifier", () => {
  assert.ok(DEPLOY.includes(resolver));
  assert.ok(VERIFIER.includes(resolver));
  assert.match(DEPLOY, /VERIFIED_FUNCTIONS=\("\$\{ROUTE_FIELDS\[@\]:1\}"\)/);
  assert.match(VERIFIER, /FUNCTION_ROUTES=\("\$\{ROUTE_FIELDS\[@\]:1\}"\)/);
});

test("the routes the customer scan path depends on are all in the verified set", () => {
  const routes = JSON.parse(
    readFileSync(new URL("../../data/base44-function-routes.json", import.meta.url), "utf8"),
  );
  const retained = generation === "v9" ? Object.values(routes.historical_routes.v8) : [];
  const active = Object.values(routes.routes).map((name) => generation === "v9" ? stagedRoutes.functions[name].route_name : name);
  assert.equal(generation, routes.generation);
  assert.deepEqual([...active, ...retained].sort(), [...verified].sort());
});
