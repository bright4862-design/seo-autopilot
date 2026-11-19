import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = path => readFileSync(new URL("../../" + path, import.meta.url), "utf8");
const doc = read("docs/fixlist-cloud-operator.md");
const workflow = read(".github/workflows/fixlist-cloud-operator.yml");
const operator = read("scripts/fixlist-cloud-operator.sh");

test("Standard 150 operator guide points to a real authenticated read-only serving probe", () => {
  assert.match(doc, /`verify-serving-worker-release`/);
  assert.match(workflow, /-\s+verify-serving-worker-release/);
  assert.match(workflow, /OPERATION:\s+verify-worker-runtime-revision/);
  assert.match(workflow, /FIXLIST_WORKER_ID_TOKEN:\s+\$\{\{\s*steps\.serving-worker-token\.outputs\.id_token\s*\}\}/);
  assert.match(operator, /verify-worker-runtime-revision\)\s*\n\s*verify_worker_runtime_revision/);
  assert.match(doc, /complete component-version map/);
  assert.match(doc, /100%-serving revision/);
});

test("legacy direct queue and beta activation instructions remain explicitly unsupported", () => {
  assert.match(operator, /pause-queue\|resume-queue\|activate-beta\)\s*\n\s*echo "Unsupported unsafe operation/);
  for (const name of ["pause-queue", "resume-queue", "activate-beta"]) {
    assert.match(doc, new RegExp("`" + name + "`"));
  }
  assert.match(doc, /unsupported unsafe operations/);
  assert.doesNotMatch(doc, /Run this before `activate-beta`/);
  assert.doesNotMatch(doc, /Run one fresh customer Funbooker scan/);
  assert.doesNotMatch(doc, /1\. Promote the explicitly named revision\./);
});

test("a runtime identity check is not documented as authorization for customer intake", () => {
  assert.match(doc, /necessary, not sufficient/);
  assert.match(doc, /independent full-access customer re-open/);
  assert.match(doc, /Incident #378 remains NO-GO/);
});