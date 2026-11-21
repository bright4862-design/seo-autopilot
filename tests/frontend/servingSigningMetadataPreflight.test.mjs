import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

// Only read-only describes are permitted by this allowlisted fake gcloud.
const SCRIPT = "scripts/inspect-serving-worker-signing-metadata.sh";
const WORKER = "fixlist-standard150-worker";
const REV_7 = `${WORKER}-00007`;
const REV_8 = `${WORKER}-00008`;
const secret = (version) => ({
  name: "SCAN_EVIDENCE_SIGNING_KEY",
  valueFrom: { secretKeyRef: { name: "synthetic-key", key: version } },
});
const service = (desired = "7", serving = REV_7) => ({
  metadata: { name: WORKER, generation: 4 },
  status: {
    observedGeneration: 4,
    conditions: [{ type: "Ready", status: "True" }],
    traffic: [{ revisionName: serving, percent: 100 }],
  },
  spec: { template: { spec: { containers: [{ env: [secret(desired)] }] } } },
});
const revision = (name) => ({
  metadata: { name, labels: { "serving.knative.dev/service": WORKER } },
  status: { conditions: [{ type: "Ready", status: "True" }] },
  spec: { containers: [{ env: [secret("7")] }] },
});

const GCLOUD = [
  "#!/usr/bin/env bash",
  "set -euo pipefail",
  'case "$1 $2 $3" in',
  '  "run services describe")',
  '    printf "service\\n" >> "$FAKE_EVENTS"',
  '    if [[ "$FAKE_DENY" == "1" ]]; then echo "PERMISSION_DENIED: synthetic" >&2; exit 33; fi',
  '    n=0',
  '    if [[ -f "$FAKE_COUNTER" ]]; then n="$(cat "$FAKE_COUNTER")"; fi',
  '    n=$((n + 1))',
  '    printf "%s" "$n" > "$FAKE_COUNTER"',
  '    variant="$(printf "%s" "$FAKE_SEQUENCE" | cut -d, -f "$n")"',
  '    if [[ -z "$variant" ]]; then variant="$(printf "%s" "$FAKE_SEQUENCE" | awk -F, \u0027{print $NF}\u0027)"; fi',
  '    cat "$FAKE_FIXTURES/service-$variant.json"',
  '    ;;',
  '  "run revisions describe")',
  '    printf "revision\\n" >> "$FAKE_EVENTS"',
  '    cat "$FAKE_FIXTURES/revision-$4.json"',
  '    ;;',
  '  *)',
  '    printf "FORBIDDEN %s\\n" "$*" >> "$FAKE_EVENTS"',
  '    exit 95',
  '    ;;',
  'esac',
].join("\n") + "\n";

function scenario(sequence, { deny = false, overrides = {} } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-keyless-preflight-"));
  const bin = path.join(dir, "bin");
  const fixtures = path.join(dir, "fixtures");
  fs.mkdirSync(bin);
  fs.mkdirSync(fixtures);
  for (const [name, body] of Object.entries({
    "service-ok": service(),
    "service-ahead": service("8"),
    "service-unready": { ...service(), status: { ...service().status, conditions: [{ type: "Ready", status: "False" }] } },
    "service-switched": service("7", REV_8),
    "service-foreign": { ...service(), metadata: { name: "other", generation: 4 } },
    [`revision-${REV_7}`]: revision(REV_7),
    [`revision-${REV_8}`]: revision(REV_8),
  })) fs.writeFileSync(path.join(fixtures, name + ".json"), JSON.stringify(body));
  fs.writeFileSync(path.join(bin, "gcloud"), GCLOUD, { mode: 0o700 });
  const events = path.join(dir, "events");
  const env = {
    ...process.env,
    PATH: bin + path.delimiter + process.env.PATH,
    GCP_PROJECT: "seo-autopilot-501517",
    GCP_REGION: "europe-west1",
    CLOUD_RUN_SERVICE: WORKER,
    FAKE_FIXTURES: fixtures,
    FAKE_EVENTS: events,
    FAKE_COUNTER: path.join(dir, "counter"),
    FAKE_SEQUENCE: sequence.join(","),
    FAKE_DENY: deny ? "1" : "0",
    ...overrides,
  };
  try {
    const run = spawnSync("bash", [SCRIPT], { cwd: process.cwd(), env, encoding: "utf8", timeout: 20000 });
    if (run.error) throw run.error;
    const observed = fs.existsSync(events) ? fs.readFileSync(events, "utf8").trim().split("\n") : [];
    assert.ok(observed.every((event) => event === "service" || event === "revision"),
      "preflight must perform only read-only describes: " + observed.join(","));
    return { status: run.status, stdout: run.stdout, stderr: run.stderr, observed };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

test("aligned two-observation preflight reports metadata only", () => {
  const result = scenario(["ok", "ok"]);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.observed, ["service", "revision", "service", "revision"]);
  assert.ok(result.stdout.includes(`KEYLESS_METADATA_PREFLIGHT_OK project=seo-autopilot-501517 region=europe-west1 service=${WORKER} revision=${REV_7}`));
  assert.match(result.stdout, /does NOT prove/);
  assert.doesNotMatch(result.stdout + result.stderr, /synthetic-key|SCAN_EVIDENCE_SIGNING_KEY/);
});

test("desired template ahead of serving revision refuses without a second observation", () => {
  const result = scenario(["ahead", "ahead"]);
  assert.notEqual(result.status, 0);
  assert.deepEqual(result.observed, ["service", "revision"]);
  assert.match(result.stderr, /desired-template signing key differs/);
  assert.doesNotMatch(result.stdout, /PREFLIGHT_OK/);
});

test("unready service refuses before any revision lookup", () => {
  const result = scenario(["unready"]);
  assert.notEqual(result.status, 0);
  assert.deepEqual(result.observed, ["service"]);
  assert.match(result.stderr, /Cloud Run service is not confirmed Ready/);
});

test("same-key serving revision switch between two observations is rejected", () => {
  const result = scenario(["ok", "switched"]);
  assert.notEqual(result.status, 0);
  assert.deepEqual(result.observed, ["service", "revision", "service", "revision"]);
  assert.match(result.stderr, /revision identity changed/);
  assert.doesNotMatch(result.stdout, /PREFLIGHT_OK/);
});

test("response for a foreign service cannot authorize a receipt", () => {
  const result = scenario(["foreign"]);
  assert.notEqual(result.status, 0);
  assert.deepEqual(result.observed, ["service"]);
  assert.match(result.stderr, /service name differs/);
});

test("read denied is unknown, not absent or successful", () => {
  const result = scenario(["ok"], { deny: true });
  assert.notEqual(result.status, 0);
  assert.deepEqual(result.observed, ["service"]);
  assert.doesNotMatch(result.stdout, /PREFLIGHT_OK|not_deployed/);
});

test("metadata preflight refuses foreign project, region and service before Cloud Run reads", () => {
  const cases = [
    { GCP_PROJECT: "unrelated-project-12345" },
    { GCP_REGION: "us-central1" },
    { CLOUD_RUN_SERVICE: "other-worker" },
  ];
  for (const overrides of cases) {
    const result = scenario(["ok", "ok"], { overrides });
    assert.notEqual(result.status, 0, JSON.stringify(overrides));
    assert.deepEqual(result.observed, [], "incorrect namespace must not query gcloud");
    assert.match(result.stderr, /production scope mismatch/);
    assert.doesNotMatch(result.stdout, /PREFLIGHT_OK/);
  }
});
