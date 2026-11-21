import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workflow = readFileSync(new URL("../../.github/workflows/ci.yml", import.meta.url), "utf8");

test("Standard 150 stacked PRs have exact-head CI without widening push", () => {
  const push = workflow.match(/^  push:\n    branches: \[([^\]]+)\]/m);
  const pull = workflow.match(/^  pull_request:\n(?:    #[^\n]*\n)*    branches: \[([^\]]+)\]/m);
  assert.ok(push, "push branch filter is present");
  assert.ok(pull, "pull_request branch filter is present");
  assert.equal(push[1], "main", "only main pushes trigger CI");
  assert.deepEqual(
    pull[1].split(",").map((item) => item.trim().replace(/^['"]|['"]$/g, "")),
    ["main", "investigation/standard150-**"],
    "PRs targeting main or an isolated Standard 150 parent may run CI",
  );
  assert.doesNotMatch(workflow, /^  pull_request_target:/m);
});

test("both CI jobs still build the immutable PR head instead of a synthetic merge", () => {
  const head = "github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha";
  const expected = `${"${{"} ${head} }}`;
  const refs = workflow.match(/^          ref: .*$/gm) || [];
  const environments = workflow.match(/^          EXPECTED_SHA: .*$/gm) || [];
  assert.equal(refs.length, 2);
  assert.equal(environments.length, 2);
  assert.ok(refs.every((line) => line.includes(expected)));
  assert.ok(environments.every((line) => line.includes(expected)));
  assert.equal((workflow.match(/test "\$\(git rev-parse HEAD\)" = "\$EXPECTED_SHA"/g) || []).length, 2);
});

test("PR CI has read-only token permission and never persists checkout credentials", () => {
  assert.match(workflow, /^permissions:\n  contents: read$/m);
  assert.doesNotMatch(workflow, /id-token:\s*write/);
  assert.equal((workflow.match(/^          persist-credentials: false$/gm) || []).length, 2);
});
