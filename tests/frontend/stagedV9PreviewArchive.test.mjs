import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";

test("the exact V9 preview archive includes the browser's scanner route manifest", () => {
  const preview = readFileSync(new URL("../../scripts/preview-base44-v9.mjs", import.meta.url), "utf8");
  const inputList = preview.match(/const FRONTEND_INPUTS = \[([\s\S]*?)\];/)?.[1];
  assert.ok(inputList, "preview archive input list is missing");
  const inputs = Array.from(inputList.matchAll(/"([^"]+)"/g), ([, file]) => file);
  const archive = execFileSync("git", ["archive", "HEAD", ...inputs], { maxBuffer: 64 * 1024 * 1024 });
  const entries = execFileSync("tar", ["-tf", "-"], { input: archive, encoding: "utf8" }).split("\n");
  assert.ok(entries.includes("src/lib/scanFunctionRouting.js"));
  assert.ok(entries.includes("data/base44-function-routes.json"), "preview would omit the route manifest imported by the frontend");
});
