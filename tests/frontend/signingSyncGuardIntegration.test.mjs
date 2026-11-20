import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";

// The real shell runs only against synthetic, PATH-overridden executables.
// No production GCP, Base44, signing secret, customer scan, or queue is touched.
const SCRIPT = "scripts/sync-base44-signing-key.sh";
const ARCHIVE = "fixture-not-a-real-base44-package";
const secret = (version) => ({
  name: "SCAN_EVIDENCE_SIGNING_KEY",
  valueFrom: { secretKeyRef: { name: "synthetic-key", key: version } },
});
const service = (templateVersion, revisionName = "worker-00007") => ({
  metadata: { name: "worker", generation: 4 },
  status: { observedGeneration: 4, traffic: revisionName ? [{ revisionName, percent: 100 }] : [] },
  spec: { template: { spec: { containers: [{ env: [secret(templateVersion)] }] } } },
});
const revision = (name, version) => ({
  metadata: { name, labels: { "serving.knative.dev/service": "worker" } },
  spec: { containers: [{ env: [secret(version)] }] },
  status: { conditions: [{ type: "Ready", status: "True" }] },
});

const GCLOUD = [
  "#!/usr/bin/env bash", "set -euo pipefail",
  'case "$1 $2 $3" in',
  '  "config set project") exit 0 ;;',
  '  "run services describe")',
  '    n=0',
  '    if test -f "$FAKE_COUNTER"; then n="$(cat "$FAKE_COUNTER")"; fi',
  '    n=$((n + 1))',
  '    printf "%s" "$n" > "$FAKE_COUNTER"',
  '    variant="$(awk -F, -v n="$n" \u0027{if(n>NF)n=NF;print $n}\u0027 <<< "$FAKE_SEQUENCE")"',
  '    cat "$FAKE_FIXTURES/service-$variant.json"',
  '    ;;',
  '  "run revisions describe") cat "$FAKE_FIXTURES/revision-$4.json" ;;',
  '  "secrets versions access")',
  '    printf "secret-read\n" >> "$FAKE_EVENTS"',
  '    printf "synthetic-key-bytes-not-production\n"',
  '    ;;',
  '  *) echo "unexpected fake gcloud call: $*" >&2; exit 87 ;;',
  'esac',
].join("\n") + "\n";

const NPM = [
  "#!/usr/bin/env bash", "set -euo pipefail", 'case "$1" in',
  '  pack)',
  '    while (($#)); do',
  '      if [[ "$1" == "--pack-destination" ]]; then destination="$2"; break; fi',
  '      shift',
  '    done',
  "    printf 'fixture-not-a-real-base44-package' > \"$destination/base44-0.1.9.tgz\"",
  '    printf "npm-pack\n" >> "$FAKE_EVENTS"',
  '    ;;',
  '  install)',
  '    while (($#)); do',
  '      if [[ "$1" == "--prefix" ]]; then prefix="$2"; break; fi',
  '      shift',
  '    done',
  '    mkdir -p "$prefix/node_modules/.bin"',
  '    cat > "$prefix/node_modules/.bin/base44" <<\u0027CLI\u0027',
  '#!/usr/bin/env bash',
  'set -euo pipefail',
  'if [[ "$*" == "login" ]]; then',
  '  printf "login\n" >> "$FAKE_EVENTS"',
  'elif [[ "$*" == *"secrets set --env-file"* ]]; then',
  '  printf "base44-import\n" >> "$FAKE_EVENTS"',
  'else',
  '  echo "unexpected fake Base44 command" >&2',
  '  exit 88',
  'fi',
  'CLI',
  '    chmod +x "$prefix/node_modules/.bin/base44"',
  '    ;;',
  '  *) echo "unexpected fake npm call: $*" >&2; exit 89 ;;',
  'esac',
].join("\n") + "\n";

function scenario(sequence) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-sync-guard-"));
  const fixtures = path.join(dir, "fixtures");
  const bin = path.join(dir, "bin");
  fs.mkdirSync(fixtures);
  fs.mkdirSync(bin);
  for (const [name, body] of Object.entries({
    "service-ok.json": service("7"),
    "service-desired-ahead.json": service("8"),
    "service-switched.json": service("7", "worker-00008"),
    "service-no-traffic.json": service("7", null),
    "revision-worker-00007.json": revision("worker-00007", "7"),
    "revision-worker-00008.json": revision("worker-00008", "7"),
  })) fs.writeFileSync(path.join(fixtures, name), JSON.stringify(body));
  fs.writeFileSync(path.join(bin, "gcloud"), GCLOUD, { mode: 0o700 });
  fs.writeFileSync(path.join(bin, "npm"), NPM, { mode: 0o700 });
  const events = path.join(dir, "events");
  const counter = path.join(dir, "counter");
  const env = {
    ...process.env,
    PATH: bin + path.delimiter + process.env.PATH,
    FAKE_FIXTURES: fixtures,
    FAKE_SEQUENCE: sequence.join(","),
    FAKE_EVENTS: events,
    FAKE_COUNTER: counter,
    BASE44_CLI_SHA512: "sha512-" + crypto.createHash("sha512").update(ARCHIVE).digest("base64"),
  };
  try {
    const run = spawnSync("bash", [SCRIPT], { env, encoding: "utf8", timeout: 20000 });
    if (run.error) throw run.error;
    return {
      code: run.status,
      output: run.stdout + "\n" + run.stderr,
      events: fs.existsSync(events) ? fs.readFileSync(events, "utf8").trim().split("\n") : [],
      probes: fs.existsSync(counter) ? Number(fs.readFileSync(counter, "utf8")) : 0,
    };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

test("desired template ahead of serving worker fails before CLI or key access", () => {
  const run = scenario(["desired-ahead"]);
  assert.notEqual(run.code, 0);
  assert.match(run.output, /desired-template signing key differs/);
  assert.deepEqual(run.events, []);
  assert.equal(run.probes, 1);
});

test("no observed serving traffic fails before CLI or key access", () => {
  const run = scenario(["no-traffic"]);
  assert.notEqual(run.code, 0);
  assert.match(run.output, /no observed Cloud Run serving traffic/);
  assert.deepEqual(run.events, []);
});

test("same-key revision switch during login fails before secret read", () => {
  const run = scenario(["ok", "switched"]);
  assert.notEqual(run.code, 0);
  assert.match(run.output, /revision identity changed/);
  assert.deepEqual(run.events, ["npm-pack", "login"]);
  assert.equal(run.probes, 2);
});

test("same-key revision switch after synthetic key read refuses import", () => {
  const run = scenario(["ok", "ok", "switched"]);
  assert.notEqual(run.code, 0);
  assert.match(run.output, /revision identity changed/);
  assert.deepEqual(run.events, ["npm-pack", "login", "secret-read"]);
  assert.equal(run.probes, 3);
});

test("aligned synthetic serving revision passes all three gates", () => {
  const run = scenario(["ok", "ok", "ok"]);
  assert.equal(run.code, 0, run.output);
  assert.deepEqual(run.events, ["npm-pack", "login", "secret-read", "base44-import"]);
  assert.equal(run.probes, 3);
  assert.match(run.output, /KEY_SYNC_COMPLETE/);
  assert.doesNotMatch(run.output, /synthetic-key-bytes-not-production/);
});
