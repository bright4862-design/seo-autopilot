import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const manifest = JSON.parse(fs.readFileSync("tests/fixtures/stage1-blueprint-corpus.json", "utf8"));
const runner = fs.readFileSync("scripts/assertCorpusRun.mjs", "utf8");
const ci = fs.readFileSync(".github/workflows/ci.yml", "utf8");

const EXPECTED_HOSTS = [
  "https://pretto.fr",
  "https://centerstreetlending.com",
  "https://www.ikessandwich.com",
  "https://locations.ikessandwich.com",
  "https://getfixlist.com",
  "https://ironwoodcrecapital.com",
];

test("named blueprint synthetic corpus includes all required hosts and stays explicitly synthetic", () => {
  assert.equal(manifest.provenance, "synthetic");
  assert.equal(manifest.full_30_site_gate, "not_assessed");
  assert.equal(manifest.cases.length, 14);
  const hosts = [...new Set(manifest.cases.map((row) => row.origin))].sort();
  assert.deepEqual(hosts, [...EXPECTED_HOSTS].sort());
  assert.ok(manifest.cases.every((row) => row.provenance === "synthetic"));
  assert.ok(manifest.cases.some((row) => row.id === "ironwood_siteground_200"));
  assert.ok(manifest.cases.some((row) => row.id === "ironwood_siteground_403"));
  assert.ok(manifest.cases.some((row) => row.id === "ironwood_truncated"));
});

test("the named corpus validator refuses to upgrade synthetic evidence into the 30-site gate", () => {
  assert.match(runner, /report\.provenance === "synthetic"/);
  assert.match(runner, /report\.full_30_site_gate === "not_assessed"/);
  assert.doesNotMatch(runner, /full_30_site_gate:\s*"pass"/);
});

test("exact-source CI executes the actual Python corpus producer and assertion runner", () => {
  assert.match(ci, /python scanner-api\/tests\/test_stage1_blueprint_corpus\.py --output \/tmp\/stage1-corpus\.json/);
  assert.match(ci, /node scripts\/assertCorpusRun\.mjs \/tmp\/stage1-corpus\.json/);
});
