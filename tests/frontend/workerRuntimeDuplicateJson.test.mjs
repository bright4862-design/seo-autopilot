import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

// A syntactically valid HTTP 200 /revision JSON body can carry two different
// fingerprints (or two values of one component). Python's default json.load
// silently keeps the last one. The authenticated release identity comparator
// must fail closed rather than accepting a conveniently ordered contradiction.
// Execute the actual embedded Python comparator with local fixture files only.
const operator = fs.readFileSync("scripts/fixlist-cloud-operator.sh", "utf8");
const start = operator.indexOf("# runtime-revision-comparator\n");
assert.notEqual(start, -1);
const end = operator.indexOf("\nPY\n", start);
assert.notEqual(end, -1);
const comparator = operator.slice(start, end + 1);
const freeze = JSON.parse(fs.readFileSync("data/beta-crawler-revision.json", "utf8"));
const sha = "a".repeat(40);
const matching = {
  fingerprint: freeze.fingerprint,
  component_versions: freeze.component_versions,
  source_sha: sha,
};

function evaluate(raw) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-duplicate-runtime-json-"));
  const script = path.join(dir, "comparator.py");
  const response = path.join(dir, "revision.json");
  const recorded = path.join(dir, "freeze.json");
  fs.writeFileSync(script, comparator);
  fs.writeFileSync(response, raw);
  fs.writeFileSync(recorded, JSON.stringify(freeze));
  try {
    return {
      status: 0,
      stdout: execFileSync("python3", [script, response, recorded, sha], { encoding: "utf8" }),
    };
  } catch (error) {
    return { status: error.status, stdout: String(error.stdout || "") };
  } finally {
    fs.rmSync(dir, { force: true, recursive: true });
  }
}

test("unambiguous /revision response remains accepted", () => {
  const result = evaluate(JSON.stringify(matching));
  assert.equal(result.status, 0, result.stdout);
  assert.match(result.stdout, /runtime fingerprint:/);
});

test("two contradictory fingerprint members fail, even if the last is correct", () => {
  const response = `{"fingerprint":"foreign","fingerprint":${JSON.stringify(freeze.fingerprint)},"component_versions":${JSON.stringify(freeze.component_versions)},"source_sha":${JSON.stringify(sha)}}`;
  const result = evaluate(response);
  assert.equal(result.status, 1);
  assert.match(result.stdout, /ambiguous JSON/);
  assert.doesNotMatch(result.stdout, /PASS:/);
});

test("two contradictory source SHA members fail, even if the last is correct", () => {
  const response = `{"fingerprint":${JSON.stringify(freeze.fingerprint)},"component_versions":${JSON.stringify(freeze.component_versions)},"source_sha":"${"b".repeat(40)}","source_sha":${JSON.stringify(sha)}}`;
  const result = evaluate(response);
  assert.equal(result.status, 1);
  assert.match(result.stdout, /ambiguous JSON/);
});

test("duplicate component marker fails, including a foreign value hidden by the final matching value", () => {
  const [name, value] = Object.entries(freeze.component_versions)[0];
  assert.ok(name && value);
  const componentsWithDuplicate = JSON.stringify(freeze.component_versions).replace(
    /^\{/,
    `{${JSON.stringify(name)}:"foreign",`,
  );
  const response = `{"fingerprint":${JSON.stringify(freeze.fingerprint)},"component_versions":${componentsWithDuplicate},"source_sha":${JSON.stringify(sha)}}`;
  const result = evaluate(response);
  assert.equal(result.status, 1);
  assert.match(result.stdout, /ambiguous JSON/);
});

test("identical duplicate and nested unrelated duplicate members also fail", () => {
  const cases = [
    `{"fingerprint":${JSON.stringify(freeze.fingerprint)},"fingerprint":${JSON.stringify(freeze.fingerprint)},"component_versions":${JSON.stringify(freeze.component_versions)},"source_sha":${JSON.stringify(sha)}}`,
    `{"fingerprint":${JSON.stringify(freeze.fingerprint)},"component_versions":${JSON.stringify(freeze.component_versions)},"source_sha":${JSON.stringify(sha)},"extra":{"same":1,"same":1}}`,
  ];
  for (const response of cases) {
    const result = evaluate(response);
    assert.equal(result.status, 1, result.stdout);
    assert.match(result.stdout, /ambiguous JSON/);
  }
});
