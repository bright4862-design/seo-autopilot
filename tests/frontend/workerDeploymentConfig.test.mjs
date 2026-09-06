import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function cloudBuildStepArgs(source, stepId) {
  const lines = source.split(/\r?\n/);
  const start = lines.findIndex((line) => line.trim() === `- id: ${stepId}`);
  assert.notEqual(start, -1, `missing Cloud Build step ${stepId}`);

  const argsStart = lines.findIndex((line, index) => index > start && line.trim() === "args:");
  assert.notEqual(argsStart, -1, `missing args for Cloud Build step ${stepId}`);

  const args = [];
  for (const line of lines.slice(argsStart + 1)) {
    const match = line.match(/^\s{6}-\s(.+)$/);
    if (!match) break;
    args.push(match[1]);
  }
  return args;
}

test("durable Standard 150 worker is staged with the bounded production runtime contract", () => {
  const manifest = readFileSync("cloudbuild.durable-worker.yaml", "utf8");
  const args = cloudBuildStepArgs(manifest, "deploy-private-worker");

  assert.ok(args.includes("--memory=1Gi"), "worker memory must safely exceed the observed 512 MiB peak");
  assert.ok(args.includes("--timeout=480"), "worker request timeout must remain bounded at 480 seconds");
  assert.ok(args.includes("--concurrency=1"), "one scan at a time must run in each worker instance");
  assert.ok(args.includes("--max-instances=40"), "worker fleet capacity must retain its release bound");
  assert.ok(args.includes("--no-traffic"), "new worker revisions must remain isolated until promotion");
});
