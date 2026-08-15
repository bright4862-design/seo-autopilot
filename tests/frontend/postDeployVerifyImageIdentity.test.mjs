// Image identity of the Standard 150 candidate revision.
//
// Activation stopped at step 3/7 with "image mismatch" against a candidate that
// was in fact correct: the verifier compared the SERVICE TEMPLATE's image (the
// tag written at deploy time) against an EXPECTED_IMAGE the activation helper
// had read off the REVISION, where Cloud Run stores it already resolved to a
// digest. A tag string can never equal a digest string, so that comparison
// could only ever fail.
//
// These tests drive the real script with a stubbed `gcloud`, so they exercise
// the comparison itself rather than asserting on its source text. Each one
// fails against the pre-fix script.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const SCRIPT = path.resolve("scripts/post_deploy_verify.sh");

const PROJECT = "seo-autopilot-501517";
const REGION = "europe-west1";
const SERVICE = "fixlist-standard150-worker";
const REPO = `${REGION}-docker.pkg.dev/${PROJECT}/fixlist/standard150-worker`;
const TAG = `${REPO}:release-499d6479`;
const DIGEST = "sha256:8f89f89da3acea6033cb1adab1bb3f6664a25c8d05b59b0e7b4d688aa8e43201";
const OTHER_DIGEST = "sha256:1111111111111111111111111111111111111111111111111111111111111111";

const CANDIDATE = "fixlist-standard150-worker-00003-abc";
const OLD_READY = "fixlist-standard150-worker-00002-kud";

const RUNTIME_SA = `fixlist-standard150-worker@${PROJECT}.iam.gserviceaccount.com`;
const INVOKER_SA = `fixlist-standard150-invoker@${PROJECT}.iam.gserviceaccount.com`;
const SIGNING_SECRET = "scan-evidence-signing-key";
const SIGNING_VERSION = "3";

// A correct revision: created from a digest reference, Ready, 0% traffic.
function revisionJson(overrides = {}) {
  const base = {
    metadata: { name: CANDIDATE },
    spec: {
      serviceAccountName: RUNTIME_SA,
      timeoutSeconds: 480,
      containerConcurrency: 1,
      containers: [
        {
          image: `${REPO}@${DIGEST}`,
          env: [
            { name: "BASE44_APP_ID", value: "app_123" },
            { name: "TASKS_INVOKER_SERVICE_ACCOUNT", value: INVOKER_SA },
            {
              name: "SCAN_EVIDENCE_SIGNING_KEY",
              valueFrom: { secretKeyRef: { name: SIGNING_SECRET, key: SIGNING_VERSION } },
            },
          ],
        },
      ],
    },
    status: {
      imageDigest: `${REPO}@${DIGEST}`,
      conditions: [{ type: "Ready", status: "True" }],
    },
  };
  return { ...base, ...overrides };
}

// The service still serves the OLD revision, and its template still carries the
// TAG. This is exactly the shape that produced the 3/7 failure.
function serviceJson(overrides = {}) {
  return {
    metadata: { name: SERVICE },
    spec: { template: { spec: { containers: [{ image: TAG, env: [] }] } } },
    status: {
      // Empty on purpose: the unauthenticated probe must skip, never reach out.
      url: "",
      latestReadyRevisionName: OLD_READY,
      traffic: [
        { revisionName: OLD_READY, percent: 100 },
        { revisionName: CANDIDATE, percent: 0 },
      ],
    },
    ...overrides,
  };
}

const IAM_POLICY = {
  bindings: [{ role: "roles/run.invoker", members: [`serviceAccount:${INVOKER_SA}`] }],
};

// Stub gcloud: answers the four read-only queries the verifier makes, from
// files on disk. Unknown invocations exit non-zero so nothing passes by luck.
const GCLOUD_STUB = `#!/usr/bin/env bash
D="$FIXTURES"
case "$1 $2 $3" in
  "run services describe")      cat "$D/service.json" ;;
  "run revisions describe")     if [ -f "$D/revision-$4.json" ]; then cat "$D/revision-$4.json"; else exit 1; fi ;;
  "run services get-iam-policy") cat "$D/iam.json" ;;
  "artifacts docker images")
    KEY=$(printf "%s" "$5" | tr -c 'A-Za-z0-9' '_')
    if [ -f "$D/registry-$KEY" ]; then cat "$D/registry-$KEY"; else exit 1; fi ;;
  *) echo "unstubbed gcloud: $*" >&2; exit 1 ;;
esac
`;

function runVerifier({ script = SCRIPT, service, revisions, registry = {}, env = {} } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pdv-"));
  const bin = path.join(dir, "bin");
  fs.mkdirSync(bin);
  fs.writeFileSync(path.join(dir, "service.json"), JSON.stringify(service ?? serviceJson()));
  fs.writeFileSync(path.join(dir, "iam.json"), JSON.stringify(IAM_POLICY));
  for (const [name, body] of Object.entries(revisions ?? { [CANDIDATE]: revisionJson() })) {
    fs.writeFileSync(path.join(dir, `revision-${name}.json`), JSON.stringify(body));
  }
  for (const [ref, digest] of Object.entries(registry)) {
    const key = ref.replace(/[^A-Za-z0-9]/g, "_");
    fs.writeFileSync(path.join(dir, `registry-${key}`), `${digest}\n`);
  }
  fs.writeFileSync(path.join(bin, "gcloud"), GCLOUD_STUB, { mode: 0o755 });

  const result = spawnSync("bash", [script], {
    encoding: "utf8",
    env: {
      ...process.env,
      FIXTURES: dir,
      PATH: `${bin}:${process.env.PATH}`,
      WORKER_SERVICE: SERVICE,
      REGION,
      PROJECT,
      CANDIDATE_REVISION: CANDIDATE,
      EXPECTED_IMAGE: `${REPO}@${DIGEST}`,
      EXPECTED_RUNTIME_SA: RUNTIME_SA,
      EXPECTED_INVOKER_SA: INVOKER_SA,
      EXPECTED_SIGNING_SECRET: SIGNING_SECRET,
      EXPECTED_SIGNING_VERSION: SIGNING_VERSION,
      ...env,
    },
  });
  fs.rmSync(dir, { recursive: true, force: true });
  return { ...result, out: `${result.stdout || ""}${result.stderr || ""}` };
}

// The reported failure, reproduced: the helper reads the image off the revision
// (a digest) while the service template still holds the tag.
test("a tag-deployed service whose candidate resolves to the expected digest verifies", () => {
  const { status, out } = runVerifier({
    registry: { [TAG]: DIGEST },
    env: { EXPECTED_IMAGE: TAG },
  });
  assert.match(out, /PASS {2}expected digest: sha256:8f89f89d.*Artifact Registry/);
  assert.match(out, /PASS {2}candidate image digest matches expected/);
  assert.doesNotMatch(out, /FAIL {2}image/);
  assert.equal(status, 0, out);
});

test("a digest EXPECTED_IMAGE matches the candidate's resolved digest", () => {
  const { status, out } = runVerifier();
  assert.match(out, /PASS {2}candidate image digest matches expected/);
  assert.equal(status, 0, out);
});

// Identity is not weakened to "same repository": the digest must match too.
test("a different digest in the right repository fails", () => {
  const { status, out } = runVerifier({ env: { EXPECTED_IMAGE: `${REPO}@${OTHER_DIGEST}` } });
  assert.match(out, /FAIL {2}image digest mismatch/);
  assert.notEqual(status, 0);
});

// ...and not to "same digest anywhere": the repository must match too.
test("the expected digest in a different repository fails", () => {
  const { status, out } = runVerifier({
    env: { EXPECTED_IMAGE: `${REGION}-docker.pkg.dev/${PROJECT}/other-repo/worker@${DIGEST}` },
  });
  assert.match(out, /FAIL {2}image repository mismatch/);
  assert.notEqual(status, 0);
});

test("a tag that cannot be resolved to a digest fails closed", () => {
  const { status, out } = runVerifier({ env: { EXPECTED_IMAGE: TAG } });
  assert.match(out, /FAIL {2}could not resolve EXPECTED_IMAGE to a digest/);
  assert.doesNotMatch(out, /PASS {2}candidate image digest matches/);
  assert.notEqual(status, 0);
});

// Without an explicit candidate the verifier has no subject: the only other
// choice is the service template, which describes a future deploy, not the
// object under test.
test("CANDIDATE_REVISION is required", () => {
  const { status, out } = runVerifier({ env: { CANDIDATE_REVISION: "" } });
  assert.match(out, /CANDIDATE_REVISION is required/);
  assert.equal(status, 2, out);
});

test("a named candidate that does not exist fails closed", () => {
  const { status, out } = runVerifier({ env: { CANDIDATE_REVISION: "no-such-revision" } });
  assert.match(out, /Could not describe revision no-such-revision/);
  assert.equal(status, 2, out);
});

// The old ready revision must never stand in for the candidate. Here it carries
// a DIFFERENT image; verifying it instead would wrongly pass.
test("the service's latestReadyRevisionName is not the verification subject", () => {
  const stale = revisionJson();
  stale.metadata = { name: OLD_READY };
  stale.spec.containers[0].image = `${REPO}@${OTHER_DIGEST}`;
  stale.status.imageDigest = `${REPO}@${OTHER_DIGEST}`;

  const { status, out } = runVerifier({
    revisions: { [CANDIDATE]: revisionJson(), [OLD_READY]: stale },
  });
  assert.match(out, new RegExp(`PASS {2}candidate under test: ${CANDIDATE}`));
  assert.match(out, new RegExp(`SKIP {2}service latestReadyRevisionName: ${OLD_READY}`));
  assert.match(out, new RegExp(`PASS {2}candidate resolved digest: ${REPO}@${DIGEST}`));
  assert.doesNotMatch(out, new RegExp(OTHER_DIGEST));
  assert.equal(status, 0, out);
});

test("a candidate that is not Ready fails", () => {
  const notReady = revisionJson();
  notReady.status.conditions = [{ type: "Ready", status: "False" }];
  const { status, out } = runVerifier({ revisions: { [CANDIDATE]: notReady } });
  assert.match(out, /FAIL {2}candidate revision is not Ready/);
  assert.notEqual(status, 0);
});

// Verification must precede promotion, so a candidate already taking traffic is
// a failure regardless of how correct its image is.
test("a candidate already serving traffic fails", () => {
  const serving = serviceJson();
  serving.status.traffic = [{ revisionName: CANDIDATE, percent: 100 }];
  const { status, out } = runVerifier({ service: serving });
  assert.match(out, /FAIL {2}candidate already serves 100% traffic/);
  assert.notEqual(status, 0);
});

// Runtime config, secret mount and Grok flags must be read off the candidate,
// not the template. The template here is deliberately empty of all of them.
test("runtime, env and secret checks read the candidate, not the service template", () => {
  const { status, out } = runVerifier();
  assert.match(out, new RegExp(`PASS {2}runtime service account: ${RUNTIME_SA}`));
  assert.match(out, /PASS {2}timeout 480s/);
  assert.match(out, /PASS {2}concurrency 1/);
  assert.match(out, /PASS {2}TASKS_INVOKER_SERVICE_ACCOUNT matches/);
  assert.match(out, new RegExp(`PASS {2}signing secret version pinned to ${SIGNING_VERSION}`));
  assert.equal(status, 0, out);
});
