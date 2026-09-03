import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";

/**
 * On 2026-09-03 the browser and the Cloud Run worker were cut over to the V2
 * Base44 function names, because Base44 kept serving older compiled handlers
 * for the original names through a full delete and redeploy. Publishing Base44
 * does not move the worker: an image built before that cutover still posts to
 * the legacy names, so every scan would be accepted and then persist nothing --
 * green promotion, silent outage. Build provenance is the only place to catch
 * it before traffic moves.
 */

const OPERATOR = "scripts/fixlist-cloud-operator.sh";
const source = readFileSync(OPERATOR, "utf8");

// The script runs its allowlisted operation on load, so the pieces under test
// are lifted out and evaluated on their own instead of sourcing the whole file.
function lift(pattern, label) {
  const match = source.match(pattern);
  assert.ok(match, `${label} is missing from the operator script`);
  return match[0];
}

const helper = lift(/^base44_routes_called\(\) \{[\s\S]*?^\}/m, "base44_routes_called");
const comparison = lift(
  /\n *echo "=== Base44 route generation ==="[\s\S]*?\n( *)fi\n/,
  "the route-generation comparison",
);

function routesCalledAt(ref) {
  return execFileSync("bash", ["-c", `REPO_ROOT="$PWD"\n${helper}\nbase44_routes_called ${ref}`], {
    encoding: "utf8",
  })
    .split("\n")
    .filter(Boolean);
}

function compare({ want, got }) {
  const script = `
    REPO_ROOT="$PWD"
    release_sha=stub
    verdict=0
    base44_routes_called() {
      if [ "$1" = HEAD ]; then printf '%s' ${JSON.stringify(want)}; else printf '%s' ${JSON.stringify(got)}; fi
    }
    run() {
${comparison}
    }
    run
    echo "verdict=$verdict"
  `;
  return execFileSync("bash", ["-c", script], { encoding: "utf8" });
}

test("the worker's Base44 routes are read out of its own source", () => {
  const head = routesCalledAt("HEAD");
  assert.ok(head.length > 0, "the release source must call at least one Base44 route");
  for (const route of head) {
    assert.match(route, /^[A-Za-z][A-Za-z0-9_]*$/);
  }
  // Whatever generation the source is on, the worker's persistence calls are
  // part of it -- otherwise this check would be comparing nothing that matters.
  assert.ok(
    head.some((route) => route.startsWith("persistDurableScanAuthority")),
    "the worker must still persist scan authority through Base44",
  );
});

test("a pre-cutover worker image is reported as a different generation", () => {
  // 33f471e is the last commit before the fresh-route cutover, so it stands in
  // for any image built before it.
  const before = routesCalledAt("33f471e");
  const now = routesCalledAt("HEAD");
  assert.notDeepEqual(before, now, "the fixture commit must predate the cutover");

  const result = compare({ want: now.join("\n"), got: before.join("\n") });
  assert.match(result, /FAIL: the running worker calls a different Base44 route generation/);
  assert.match(result, /verdict=1/);
});

test("a worker built from this source passes", () => {
  const now = routesCalledAt("HEAD").join("\n");
  const result = compare({ want: now, got: now });
  assert.match(result, /^PASS$/m);
  assert.match(result, /verdict=0/);
});

test("an image whose source calls no Base44 route is never treated as a match", () => {
  // Two empty sets are equal, so a naive comparison would call this a pass and
  // wave through an image that cannot persist anything at all.
  const result = compare({ want: "", got: "" });
  assert.match(result, /FAIL: the release source declares no Base44 worker routes/);
  assert.match(result, /verdict=1/);
});
