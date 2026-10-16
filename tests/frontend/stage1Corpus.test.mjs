import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { assertCorpusRun } from "../../scripts/assertCorpusRun.mjs";

const root = fileURLToPath(new URL("../../", import.meta.url));
let observed;

function actualRun() {
  if (observed) return observed;
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-stage1-corpus-"));
  const output = path.join(directory, "observed.json");
  try {
    const localPython = path.join(root, ".venv", "bin", "python");
    const python = process.env.FIXLIST_TEST_PYTHON
      || (fs.existsSync(localPython) ? localPython : "python3");
    const result = spawnSync(python, ["scanner-api/tests/test_stage1_blueprint_corpus.py", "--output", output], {
      cwd: root, encoding: "utf8", timeout: 120_000,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
    });
    assert.equal(result.status, 0, result.stderr || result.stdout || String(result.error));
    observed = JSON.parse(fs.readFileSync(output, "utf8"));
    return observed;
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

test("the named synthetic corpus checks actual Python scanner and local-review output", () => {
  const summary = assertCorpusRun(actualRun());
  assert.equal(summary.provenance, "synthetic");
  assert.equal(summary.full_30_site_gate, "not_assessed");
  assert.ok(summary.assertions >= 35);
});

test("a missing mandatory scenario cannot pass", () => {
  const result = structuredClone(actualRun());
  result.cases = result.cases.filter(item => item.id !== "ironwood_siteground_200");
  assert.throws(() => assertCorpusRun(result), /missing.*ironwood_siteground_200/i);
});

test("a claimed passing status cannot hide an actual failed observation", () => {
  const result = structuredClone(actualRun());
  result.passed = true;
  const item = result.cases.find(row => row.id === "pretto_published_routes");
  item.passed = true;
  item.review.recommendations = [];
  assert.throws(() => assertCorpusRun(result), /pretto_published_routes.*affected/i);
});

test("unlabelled or live-labelled output is rejected", () => {
  for (const provenance of [undefined, "live", "captured"]) {
    const result = structuredClone(actualRun());
    result.provenance = provenance;
    assert.throws(() => assertCorpusRun(result), /provenance/i);
  }
});

test("unknown source, wrong fixture identity and duplicate cases are rejected", () => {
  const noSource = structuredClone(actualRun());
  delete noSource.source.source_tree_sha256;
  assert.throws(() => assertCorpusRun(noSource), /source/i);
  const noVersions = structuredClone(actualRun());
  noVersions.source.versions = {};
  assert.throws(() => assertCorpusRun(noVersions), /version/i);
  const wrongFixture = structuredClone(actualRun());
  wrongFixture.manifest_sha256 = "0".repeat(64);
  assert.throws(() => assertCorpusRun(wrongFixture), /manifest/i);
  const duplicate = structuredClone(actualRun());
  duplicate.cases.push(duplicate.cases[0]);
  assert.throws(() => assertCorpusRun(duplicate), /duplicate/i);
});

test("the CLI returns nonzero for incomplete observed output", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-stage1-invalid-"));
  try {
    const output = path.join(directory, "invalid.json");
    const result = structuredClone(actualRun());
    result.cases = [];
    fs.writeFileSync(output, JSON.stringify(result));
    const checked = spawnSync(process.execPath, ["scripts/assertCorpusRun.mjs", output], {
      cwd: root, encoding: "utf8",
    });
    assert.equal(checked.status, 1);
    assert.match(checked.stderr, /missing/i);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
