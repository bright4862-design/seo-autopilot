import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const GUARD = "scripts/select-serving-worker-signing-ref.py";
const secret = (version) => ({
  name: "SCAN_EVIDENCE_SIGNING_KEY",
  valueFrom: { secretKeyRef: { name: "synthetic-scan-key", key: version } },
});
const service = (templateVersion = "7", traffic = [{ revisionName: "worker-00007", percent: 100 }]) => ({
  metadata: { name: "worker", generation: 4 },
  status: { observedGeneration: 4, traffic },
  spec: { template: { spec: { containers: [{ env: [secret(templateVersion)] }] } } },
});
const revision = (version = "7", ready = "True") => ({
  metadata: {
    name: "worker-00007",
    labels: { "serving.knative.dev/service": "worker" },
  },
  spec: { containers: [{ env: [secret(version)] }] },
  status: { conditions: [{ type: "Ready", status: ready }] },
});

function invoke(mode, svc, rev = revision(), initialRef) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-serving-ref-"));
  const svcPath = path.join(dir, "service.json");
  const revPath = path.join(dir, "revision.json");
  const refPath = path.join(dir, "ref.txt");
  try {
    fs.writeFileSync(svcPath, JSON.stringify(svc));
    fs.writeFileSync(revPath, JSON.stringify(rev));
    if (initialRef !== undefined) fs.writeFileSync(refPath, initialRef);
    const args = mode === "revision-name"
      ? [GUARD, mode, svcPath]
      : [GUARD, mode, svcPath, revPath, refPath];
    const run = spawnSync("python3", args, { encoding: "utf8" });
    return { status: run.status, stdout: run.stdout, stderr: run.stderr,
      ref: fs.existsSync(refPath) ? fs.readFileSync(refPath, "utf8") : null };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

test("selects only the observed Ready 100%-serving revision's pinned reference", () => {
  const selected = invoke("select", service(), revision());
  assert.equal(selected.status, 0, selected.stderr);
  assert.equal(selected.ref, "synthetic-scan-key 7\n");
  assert.equal(invoke("revision-name", service()).stdout, "worker-00007\n");
  const verified = invoke("verify", service(), revision(), selected.ref);
  assert.equal(verified.status, 0, verified.stderr);
});

const invalid = [
  ["desired template ahead of serving revision", service("8")],
  ["missing observed traffic", service("7", [])],
  ["split serving traffic", service("7", [
    { revisionName: "worker-00007", percent: 50 },
    { revisionName: "worker-00008", percent: 50 },
  ])],
  ["not yet observed service generation", {
    ...service(), status: { observedGeneration: 3, traffic: service().status.traffic },
  }],
  ["traffic without an explicit revision identity", service("7", [{ latestRevision: true, percent: 100 }])],
];

for (const [label, svc] of invalid) {
  test("rejects " + label, () => {
    const result = invoke("select", svc);
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /ERROR:/);
    assert.equal(result.ref, null);
  });
}

test("rejects an unready serving revision", () => {
  assert.notEqual(invoke("select", service(), revision("7", "False")).status, 0);
});

test("rejects an unmatched revision name", () => {
  const other = revision();
  other.metadata.name = "worker-00006";
  assert.notEqual(invoke("select", service(), other).status, 0);
});

test("rejects foreign revision service identity", () => {
  const other = revision();
  other.metadata.labels["serving.knative.dev/service"] = "foreign-worker";
  assert.notEqual(invoke("select", service(), other).status, 0);
});

test("rejects unpinned latest and duplicate signing-key references", () => {
  assert.notEqual(invoke("select", service("latest"), revision("latest")).status, 0);
  const duplicated = revision();
  duplicated.spec.containers[0].env.push(secret("7"));
  assert.notEqual(invoke("select", service(), duplicated).status, 0);
});

test("accepts a zero-percent tagged revision alongside the sole serving revision", () => {
  const tagged = service("7", [
    { revisionName: "worker-00007", percent: 100 },
    { revisionName: "worker-00006", percent: 0, tag: "preview" },
  ]);
  assert.equal(invoke("select", tagged).status, 0);
});

test("refuses changed key or traffic during pre-import verification", () => {
  assert.notEqual(invoke("verify", service("8"), revision(), "synthetic-scan-key 7\n").status, 0);
  const moved = service("7", [{ revisionName: "worker-00008", percent: 100 }]);
  assert.notEqual(invoke("verify", moved, revision(), "synthetic-scan-key 7\n").status, 0);
  assert.notEqual(invoke("verify", service(), revision(), "synthetic-scan-key 8\n").status, 0);
});
