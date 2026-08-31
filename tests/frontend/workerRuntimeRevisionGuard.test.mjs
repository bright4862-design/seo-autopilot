import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

// A worker can be built from the right commit, run the right image, declare the
// right routes, hold the right timeout -- and still compute a release identity
// no commit in this repository produces. persistDurableScanAuthority rejects
// exactly that, so every scan such a revision serves dies as
// authority_snapshot_not_eligible__beta_revision_fingerprint behind a green
// promotion. These exercise the real comparator and the real probe-URL
// resolver, extracted from the operator script and run against fixtures, not
// the script's prose.
const SCRIPT = "scripts/fixlist-cloud-operator.sh";
const WORKFLOW = ".github/workflows/fixlist-cloud-operator.yml";
const operator = fs.readFileSync(SCRIPT, "utf8");
const workflow = fs.readFileSync(WORKFLOW, "utf8");

// Both blocks are unindented heredoc bodies terminated by a bare `PY`, so the
// marker comment plus that terminator delimits them exactly.
function pythonBlock(marker) {
  const start = operator.indexOf(`# ${marker}\n`);
  assert.notEqual(start, -1, `${marker} block must exist in ${SCRIPT}`);
  const end = operator.indexOf("\nPY\n", start);
  assert.notEqual(end, -1, `${marker} block must be heredoc-terminated`);
  return operator.slice(start, end + 1);
}

const COMPARATOR = pythonBlock("runtime-revision-comparator");
const PROBE_URL = pythonBlock("runtime-revision-probe-url");

function runPython(source, args) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "runtime-revision-guard-"));
  const file = path.join(dir, "block.py");
  fs.writeFileSync(file, source);
  try {
    const stdout = execFileSync("python3", [file, ...args], { encoding: "utf8" });
    return { status: 0, stdout };
  } catch (error) {
    return { status: error.status, stdout: String(error.stdout || "") };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

function withFixtures(files, fn) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "runtime-revision-fixture-"));
  try {
    const paths = {};
    for (const [name, value] of Object.entries(files)) {
      paths[name] = path.join(dir, `${name}.json`);
      fs.writeFileSync(paths[name], typeof value === "string" ? value : JSON.stringify(value));
    }
    return fn(paths);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

// The component set as of the release under test. Only the names matter for the
// comparison; the values are what the diagnostic has to echo back.
const COMPONENTS = {
  review_version: "review_v9",
  failure_evidence_dedup_version: "failure_evidence_dedup_v1_generator_group",
  repair_coverage_version: "repair_coverage_v3_unknown_mixed_scope",
  frontier_policy_version: "frontier_policy_v2",
};

const RECORDED = {
  schema_version: "beta_crawler_revision_v1",
  fingerprint: "5d94e93c54a9efb6",
  component_versions: COMPONENTS,
};

function compare(live, recorded = RECORDED, expectedSha = "") {
  return withFixtures({ live, recorded }, (paths) =>
    runPython(COMPARATOR, [paths.live, paths.recorded, expectedSha]),
  );
}

test("a worker computing the recorded identity passes", () => {
  const result = compare({
    schema_version: "beta_crawler_revision_v1",
    component_versions: COMPONENTS,
    fingerprint: "5d94e93c54a9efb6",
    source_sha: "a".repeat(40),
  }, RECORDED, "a".repeat(40));
  assert.equal(result.status, 0);
  assert.match(result.stdout, /runtime fingerprint:  5d94e93c54a9efb6/);
});

test("a divergent fingerprint fails and names the component that diverged", () => {
  // This is the shape of the production incident: one component behind, every
  // other component identical, so the fingerprint alone says only "different".
  const drifted = { ...COMPONENTS, failure_evidence_dedup_version: "failure_evidence_dedup_v0_stale" };
  const result = compare({
    schema_version: "beta_crawler_revision_v1",
    component_versions: drifted,
    fingerprint: "e18b72b2d0e159b8",
    source_sha: "a".repeat(40),
  });
  assert.equal(result.status, 1, "a divergent runtime fingerprint must fail");
  assert.match(result.stdout, /authority_snapshot_not_eligible__beta_revision_fingerprint/);
  assert.match(result.stdout, /divergent markers/);
  assert.match(
    result.stdout,
    /failure_evidence_dedup_version: failure_evidence_dedup_v0_stale -> failure_evidence_dedup_v1_generator_group/,
    "the operator must be told which component diverged, and in which direction",
  );
  // A component that matches is noise in that list and must not appear.
  assert.doesNotMatch(result.stdout, /^ {2}review_version:/m);
});

test("a component the runtime has and the record lacks is still reported", () => {
  const result = compare({
    component_versions: { ...COMPONENTS, unrecorded_version: "v1" },
    fingerprint: "1111111111111111",
  });
  assert.equal(result.status, 1);
  assert.match(result.stdout, /unrecorded_version: v1 -> \(absent\)/);
});

test("a component the record has and the runtime dropped is still reported", () => {
  const { frontier_policy_version, ...missing } = COMPONENTS;
  const result = compare({ component_versions: missing, fingerprint: "2222222222222222" });
  assert.equal(result.status, 1);
  assert.match(result.stdout, /frontier_policy_version: \(absent\) -> frontier_policy_v2/);
});

test("an identical component set behind a different fingerprint is called out as such", () => {
  // Same components, different hash means the divergence is in how the
  // fingerprint is computed -- silently printing an empty diff would read as
  // "nothing is wrong".
  const result = compare({ component_versions: COMPONENTS, fingerprint: "3333333333333333" });
  assert.equal(result.status, 1);
  assert.match(result.stdout, /divergence is in how the fingerprint is/);
  assert.doesNotMatch(result.stdout, /divergent markers/);
});

test("a missing fingerprint is a failure, never a pass by absence", () => {
  for (const live of [{ component_versions: COMPONENTS }, { fingerprint: "", component_versions: COMPONENTS }]) {
    const result = compare(live);
    assert.equal(result.status, 1, "an absent runtime fingerprint must not pass");
    assert.match(result.stdout, /FAIL/);
  }
  const unrecorded = compare({ fingerprint: "5d94e93c54a9efb6" }, { component_versions: COMPONENTS });
  assert.equal(unrecorded.status, 1, "an absent recorded fingerprint must not pass");
});

test("a non-JSON or non-object body is a failure", () => {
  for (const body of ["<html>403 Forbidden</html>", "", '["5d94e93c54a9efb6"]', '"5d94e93c54a9efb6"']) {
    const result = withFixtures({ live: body, recorded: RECORDED }, (paths) =>
      runPython(COMPARATOR, [paths.live, paths.recorded, ""]),
    );
    assert.equal(result.status, 1, `${body.slice(0, 20)} must not pass as a revision answer`);
  }
});

test("a container built from a different commit than its image provenance fails", () => {
  const live = {
    component_versions: COMPONENTS,
    fingerprint: "5d94e93c54a9efb6",
    source_sha: "b".repeat(40),
  };
  const result = compare(live, RECORDED, "a".repeat(40));
  assert.equal(result.status, 1, "a source_sha contradiction must fail even when the fingerprint matches");
  assert.match(result.stdout, /bbbbbbbb/);
  assert.match(result.stdout, /aaaaaaaa/);
  // Same value on both sides is not a contradiction.
  assert.equal(compare({ ...live, source_sha: "a".repeat(40) }, RECORDED, "a".repeat(40)).status, 0);
});

test("an unstamped container is a hard failure, not a warning", () => {
  // Tying running bytes to a reviewed commit is the whole point of the gate, so
  // a container that cannot say what it was built from is unpromotable even
  // when every marker it does carry matches.
  for (const expected of ["a".repeat(40), ""]) {
    const result = compare(
      { component_versions: COMPONENTS, fingerprint: "5d94e93c54a9efb6" },
      RECORDED,
      expected,
    );
    assert.equal(result.status, 1, "an unstamped container must never pass");
    assert.match(result.stdout, /FAIL: the container declares no FIXLIST_WORKER_SOURCE_SHA/);
    assert.doesNotMatch(result.stdout, /WARNING/);
  }
});

test("the release markers must match exactly, not merely hash to the same value", () => {
  // The fingerprint is a hash of the marker set, so this is what catches a
  // response carrying the right hash with a truncated or padded marker set --
  // the shape a doctored or half-built container would produce.
  const truncated = compare({
    component_versions: { review_version: COMPONENTS.review_version },
    fingerprint: RECORDED.fingerprint,
    source_sha: "a".repeat(40),
  });
  assert.equal(truncated.status, 1, "a truncated marker set must fail");
  assert.match(truncated.stdout, /release markers differ/);
  assert.match(truncated.stdout, /divergent markers/);

  const padded = compare({
    component_versions: { ...COMPONENTS, extra_version: "v1" },
    fingerprint: RECORDED.fingerprint,
    source_sha: "a".repeat(40),
  });
  assert.equal(padded.status, 1, "an extra marker must fail");
  assert.match(padded.stdout, /extra_version: v1 -> \(absent\)/);

  const absent = compare({ fingerprint: RECORDED.fingerprint, source_sha: "a".repeat(40) });
  assert.equal(absent.status, 1, "no marker set at all must fail");
  assert.match(absent.stdout, /returned no release markers/);
});

function resolveProbeUrl(service, revision, audience = "") {
  return withFixtures({ service }, (paths) =>
    runPython(PROBE_URL, [paths.service, revision, audience]),
  ).stdout.trim();
}

const SERVICE_URL = "https://fixlist-standard150-worker-abc-uc.a.run.app";
const TAG_URL = "https://candidate---fixlist-standard150-worker-abc-uc.a.run.app";

test("a revision holding all traffic is probed on the service URL", () => {
  const service = {
    status: { url: SERVICE_URL, traffic: [{ revisionName: "worker-00054-trs", percent: 100 }] },
  };
  assert.equal(resolveProbeUrl(service, "worker-00054-trs"), SERVICE_URL);
});

test("a tagged revision is probed on its own URL even at zero traffic", () => {
  const service = {
    status: {
      url: SERVICE_URL,
      traffic: [
        { revisionName: "worker-00053-abc", percent: 100 },
        { revisionName: "worker-00054-trs", percent: 0, tag: "candidate", url: TAG_URL },
      ],
    },
  };
  assert.equal(resolveProbeUrl(service, "worker-00054-trs"), TAG_URL);
});

test("an untagged revision that does not hold all traffic yields no probe URL", () => {
  // The service URL would answer, but from whichever revision holds traffic --
  // attributing that answer to the candidate is how a bad build gets promoted.
  const split = {
    status: {
      url: SERVICE_URL,
      traffic: [
        { revisionName: "worker-00053-abc", percent: 90 },
        { revisionName: "worker-00054-trs", percent: 10 },
      ],
    },
  };
  assert.equal(resolveProbeUrl(split, "worker-00054-trs"), "");
  const zero = {
    status: {
      url: SERVICE_URL,
      traffic: [
        { revisionName: "worker-00053-abc", percent: 100 },
        { revisionName: "worker-00054-trs", percent: 0 },
      ],
    },
  };
  assert.equal(resolveProbeUrl(zero, "worker-00054-trs"), "");
  assert.equal(resolveProbeUrl(zero, "worker-00099-nope"), "", "an unknown revision yields nothing");
});

// Running the real operation end to end against stubbed gcloud/curl is the only
// way to prove the refusal paths refuse. Asserting on their prose would pass a
// guard that printed INDETERMINATE and then fell through to PASS.
function runGuard({ service, revision = "", body, code = "200", token = "stub-token", audience = "", probeUrl = "", sourceSha = "" }) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "runtime-revision-e2e-"));
  const bin = path.join(dir, "bin");
  fs.mkdirSync(bin);
  const servicePath = path.join(dir, "service.json");
  const bodyPath = path.join(dir, "revision.json");
  const curlLog = path.join(dir, "curl.log");
  fs.writeFileSync(servicePath, JSON.stringify(service));
  fs.writeFileSync(bodyPath, typeof body === "string" ? body : JSON.stringify(body));
  fs.writeFileSync(
    path.join(bin, "gcloud"),
    `#!/usr/bin/env bash
if [ "$1 $2" = "config set" ]; then exit 0; fi
if [ "$1 $2 $3" = "run services describe" ]; then cat "${servicePath}"; exit 0; fi
echo "unexpected gcloud: $*" >&2; exit 1
`,
    { mode: 0o755 },
  );
  fs.writeFileSync(
    path.join(bin, "curl"),
    `#!/usr/bin/env bash
printf '%s\\n' "$*" >> "${curlLog}"
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --output) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$out" ] && cp "${bodyPath}" "$out"
printf '%s' "${code}"
`,
    { mode: 0o755 },
  );
  const env = {
    ...process.env,
    PATH: `${bin}:${process.env.PATH}`,
    GCP_PROJECT: "stub-project",
    GCP_REGION: "us-central1",
    CLOUD_RUN_SERVICE: "fixlist-standard150-worker",
    CLOUD_TASKS_QUEUE: "fixlist-standard150",
    TASKS_INVOKER_SERVICE_ACCOUNT: "stub@stub.iam.gserviceaccount.com",
    OPERATION: "verify-worker-runtime-revision",
    TARGET_REVISION: revision,
    FIXLIST_WORKER_ID_TOKEN: token,
    FIXLIST_WORKER_TOKEN_AUDIENCE: audience || service?.status?.url || "",
    FIXLIST_WORKER_PROBE_URL: probeUrl,
    SOURCE_SHA: sourceSha,
  };
  try {
    const stdout = execFileSync("bash", [SCRIPT], { encoding: "utf8", env, stdio: ["ignore", "pipe", "pipe"] });
    return { status: 0, stdout, curl: fs.readFileSync(curlLog, "utf8") };
  } catch (error) {
    return {
      status: error.status,
      stdout: String(error.stdout || ""),
      curl: fs.existsSync(curlLog) ? fs.readFileSync(curlLog, "utf8") : "",
    };
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

// The committed freeze is the recorded side of every end-to-end comparison, so
// the fixtures stay true when the release identity is re-frozen.
const FREEZE = JSON.parse(fs.readFileSync("data/beta-crawler-revision.json", "utf8"));
const PROMOTED_SHA = "a".repeat(40);
const LIVE_MATCHING = {
  schema_version: FREEZE.schema_version,
  component_versions: FREEZE.component_versions,
  fingerprint: FREEZE.fingerprint,
  source_sha: PROMOTED_SHA,
};
const serving = (revisionName, extra = {}) => ({
  status: {
    url: SERVICE_URL,
    traffic: [{ revisionName, percent: 100, ...extra }],
  },
});

test("end to end: a worker serving the recorded identity passes", () => {
  const result = runGuard({ service: serving("worker-00054-trs"), revision: "worker-00054-trs", body: LIVE_MATCHING });
  assert.equal(result.status, 0, result.stdout);
  assert.match(result.stdout, /PASS: the running worker computes/);
  assert.match(result.curl, new RegExp(`${SERVICE_URL}/revision`));
  assert.match(result.curl, /authorization: Bearer stub-token/);
});

test("end to end: a worker serving a different identity fails and is diagnosed", () => {
  const drifted = {
    ...LIVE_MATCHING,
    fingerprint: "e18b72b2d0e159b8",
    component_versions: { ...FREEZE.component_versions, failure_evidence_dedup_version: "stale_v0" },
  };
  const result = runGuard({ service: serving("worker-00054-trs"), revision: "worker-00054-trs", body: drifted });
  assert.notEqual(result.status, 0, "a divergent runtime identity must fail the operation");
  assert.doesNotMatch(result.stdout, /PASS:/);
  assert.match(result.stdout, /failure_evidence_dedup_version: stale_v0 -> /);
});

test("end to end: an answer that cannot be attributed never passes", () => {
  // The service URL would answer here, from the revision that holds traffic.
  // Accepting it is precisely how a bad candidate gets a green promotion.
  const split = {
    status: {
      url: SERVICE_URL,
      traffic: [
        { revisionName: "worker-00053-abc", percent: 100 },
        { revisionName: "worker-00054-trs", percent: 0 },
      ],
    },
  };
  const result = runGuard({ service: split, revision: "worker-00054-trs", body: LIVE_MATCHING });
  assert.notEqual(result.status, 0, "an unattributable probe must not pass");
  assert.doesNotMatch(result.stdout, /PASS:/);
  assert.equal(result.curl, "", "it must not probe at all rather than probe the wrong revision");
});

test("end to end: a tagged revision is addressed by its tag, never by the traffic split", () => {
  // Even at 100% the tag is the safer address: traffic can move between the
  // describe and the probe, and the tag cannot.
  const tagged = {
    status: {
      url: SERVICE_URL,
      traffic: [{ revisionName: "worker-00054-trs", percent: 100, tag: "candidate", url: TAG_URL }],
    },
  };
  const live = runGuard({ service: tagged, revision: "worker-00054-trs", body: LIVE_MATCHING, probeUrl: TAG_URL });
  assert.equal(live.status, 0, live.stdout);
  assert.match(live.curl, new RegExp(`${TAG_URL}/revision`));
  assert.doesNotMatch(live.curl, new RegExp(`${SERVICE_URL}/revision`));

  const candidate = {
    status: {
      url: SERVICE_URL,
      traffic: [
        { revisionName: "worker-00053-abc", percent: 100 },
        { revisionName: "worker-00054-trs", percent: 0, tag: "candidate", url: TAG_URL },
      ],
    },
  };
  const zero = runGuard({ service: candidate, revision: "worker-00054-trs", body: LIVE_MATCHING, probeUrl: TAG_URL });
  assert.equal(zero.status, 0, "a tag makes a zero-traffic candidate verifiable before promotion");
  assert.match(zero.curl, new RegExp(`${TAG_URL}/revision`));
});

test("end to end: an unreadable runtime is a refusal, not a pass", () => {
  const service = serving("worker-00054-trs");
  const cases = [
    { name: "no identity token supplied", opts: { token: "" } },
    { name: "token rejected", opts: { code: "403", body: "<html>Forbidden</html>" } },
    { name: "endpoint absent", opts: { code: "404", body: '{"detail":"Not Found"}' } },
    { name: "transport failure", opts: { code: "000", body: "" } },
    { name: "gateway error", opts: { code: "502", body: "<html>Bad Gateway</html>" } },
  ];
  for (const { name, opts } of cases) {
    const result = runGuard({ service, revision: "worker-00054-trs", body: LIVE_MATCHING, ...opts });
    assert.notEqual(result.status, 0, `${name} must fail the operation`);
    assert.doesNotMatch(result.stdout, /PASS:/, `${name} must not report a pass`);
  }
});

test("end to end: the status decides, not whatever the body happens to contain", () => {
  // An edge, a cache, or an error page can carry a body that parses as the
  // recorded revision. Only a 200 from the worker is an answer about the
  // worker, so the correct-looking body must not rescue a failed request.
  const service = serving("worker-00054-trs");
  for (const code of ["401", "403", "404", "500", "502", "000", "301"]) {
    const result = runGuard({ service, revision: "worker-00054-trs", body: LIVE_MATCHING, code });
    assert.notEqual(result.status, 0, `HTTP ${code} carrying a matching body must still fail`);
    assert.doesNotMatch(result.stdout, /PASS:/, `HTTP ${code} must not report a pass`);
  }
});

test("a declared audience decides the probe URL, because no other URL accepts the token", () => {
  // The token is minted before the URL is known and is valid for exactly one
  // audience. Probing a different URL with it earns a 403 that reads like a
  // broken worker, so the audience is honoured -- but only where it genuinely
  // addresses the revision under test.
  const both = {
    status: {
      url: SERVICE_URL,
      traffic: [{ revisionName: "worker-00054-trs", percent: 100, tag: "candidate", url: TAG_URL }],
    },
  };
  assert.equal(resolveProbeUrl(both, "worker-00054-trs", SERVICE_URL), SERVICE_URL);
  assert.equal(resolveProbeUrl(both, "worker-00054-trs", TAG_URL), TAG_URL);
  assert.equal(resolveProbeUrl(both, "worker-00054-trs"), TAG_URL, "with no audience the tag is the precise address");

  // An audience that cannot address this revision yields no probe at all.
  assert.equal(resolveProbeUrl(both, "worker-00054-trs", "https://elsewhere.example"), "");
  const zero = {
    status: {
      url: SERVICE_URL,
      traffic: [
        { revisionName: "worker-00053-abc", percent: 100 },
        { revisionName: "worker-00054-trs", percent: 0, tag: "candidate", url: TAG_URL },
      ],
    },
  };
  assert.equal(
    resolveProbeUrl(zero, "worker-00054-trs", SERVICE_URL),
    "",
    "the service URL does not address a zero-traffic candidate, whatever the token says",
  );
  assert.equal(resolveProbeUrl(zero, "worker-00054-trs", TAG_URL), TAG_URL);
});

test("end to end: the promotion path probes the URL its token was minted for", () => {
  const service = serving("worker-00054-trs");
  const ok = runGuard({
    service,
    revision: "worker-00054-trs",
    body: LIVE_MATCHING,
    audience: SERVICE_URL,
  });
  assert.equal(ok.status, 0, ok.stdout);
  assert.match(ok.curl, new RegExp(`${SERVICE_URL}/revision`));

  const mismatched = runGuard({
    service,
    revision: "worker-00054-trs",
    body: LIVE_MATCHING,
    audience: "https://fixlist-standard150-worker-stale-uc.a.run.app",
  });
  assert.notEqual(mismatched.status, 0, "a token minted for another URL must not be spent on a guess");
  assert.doesNotMatch(mismatched.stdout, /PASS:/);
  assert.equal(mismatched.curl, "", "it must not probe with a token the URL will reject");
});

test("end to end: with no revision named, the one serving all traffic is the subject", () => {
  const result = runGuard({ service: serving("worker-00054-trs"), body: LIVE_MATCHING });
  assert.equal(result.status, 0, result.stdout);
  assert.match(result.stdout, /revision under test: worker-00054-trs/);

  const none = {
    status: {
      url: SERVICE_URL,
      traffic: [
        { revisionName: "worker-00053-abc", percent: 50 },
        { revisionName: "worker-00054-trs", percent: 50 },
      ],
    },
  };
  const ambiguous = runGuard({ service: none, body: LIVE_MATCHING });
  assert.notEqual(ambiguous.status, 0, "a split with no single serving revision has no subject");
  assert.doesNotMatch(ambiguous.stdout, /PASS:/);
  // It must say there is no subject, not invent one and then send the operator
  // off to tag a revision that does not exist.
  assert.match(ambiguous.stdout, /none serves 100% of traffic/);
  assert.doesNotMatch(ambiguous.stdout, /revision under test:/);
});

test("the operator exposes the check as a read-only operation", () => {
  // SOURCE_SHA reaches the guard so the container's own provenance stamp is
  // checked against the release being promoted, not left as dead code.
  assert.match(
    operator,
    /^ {2}verify-worker-runtime-revision\)\n {4}verify_worker_runtime_revision "\$TARGET_REVISION" "\$SOURCE_SHA"$/m,
  );
  const block = operator.match(/verify-worker-runtime-revision\)\n {4}[^\n]*\n {4};;/)[0];
  assert.match(
    workflow,
    /SOURCE_SHA: \$\{\{ steps\.command\.outputs\.source_sha \}\}\n {10}FIXLIST_WORKER_ID_TOKEN:/,
    "the promotion step must pass the release SHA alongside the worker token",
  );
  assert.doesNotMatch(block, /require_confirmation|update-traffic|deploy/);
});

test("the candidate is verified before any traffic moves", () => {
  // This is the ordering the whole gate rests on: a candidate that computes the
  // wrong release identity must be caught while it still holds 0% traffic, so
  // the failure costs a tag rather than a promotion and a rollback.
  const at = (name) => {
    const index = workflow.indexOf(`- name: ${name}`);
    assert.notEqual(index, -1, `workflow step missing: ${name}`);
    return index;
  };
  const discover = at("Discover exact zero-traffic candidate and rollback revision");
  const tag = at("Tag the exact zero-traffic candidate");
  const resolveAudience = at("Resolve candidate token audience");
  const mint = at("Mint candidate invoker identity token");
  const gate = at("Verify candidate runtime release identity before promotion");
  const promote = at("Promote exact candidate with automatic rollback on failed post-check");

  assert.ok(discover < tag, "the candidate must be discovered before it is tagged");
  assert.ok(tag < resolveAudience, "the tag URL must exist before the token audience is resolved");
  assert.ok(resolveAudience < mint, "the canonical service URL must be resolved before the token is minted");
  assert.ok(mint < gate, "the token must exist before the gate probes with it");
  assert.ok(gate < promote, "the gate must run before promotion, not after it");

  // The gate sends the request to the tag but spends a token minted for the canonical service audience.
  const gateStep = workflow.slice(gate, promote);
  assert.match(gateStep, /OPERATION: verify-worker-runtime-revision/);
  assert.match(gateStep, /FIXLIST_WORKER_PROBE_URL: \$\{\{ steps\.candidate-tag\.outputs\.url \}\}/);
  assert.match(gateStep, /FIXLIST_WORKER_TOKEN_AUDIENCE: \$\{\{ steps\.candidate-service-url\.outputs\.url \}\}/);
  assert.match(gateStep, /SOURCE_SHA: \$\{\{ steps\.command\.outputs\.source_sha \}\}/);
  // Nothing may soften it: a failed gate has to fail the job before promotion.
  assert.doesNotMatch(gateStep, /continue-on-error|\|\| true/);

  const mintStep = workflow.slice(mint, gate);
  assert.match(mintStep, /id_token_audience: \$\{\{ steps\.candidate-service-url\.outputs\.url \}\}/);
  assert.doesNotMatch(mintStep, /id_token_audience: \$\{\{ steps\.candidate-tag\.outputs\.url \}\}/);
  assert.match(mintStep, /create_credentials_file: false/);
});

test("tagging addresses the candidate without moving traffic", () => {
  const tagFn = operator.match(/^tag_worker_candidate\(\) \{$[\s\S]*?^\}$/m)[0];
  // --set-tags would drop every tag this release does not know about.
  assert.match(tagFn, /--update-tags=/);
  assert.doesNotMatch(tagFn, /--set-tags=/);
  // Tagging a revision that already serves would prove nothing about a candidate.
  assert.match(tagFn, /already receives \$\{percent\}% of traffic/);
  // And it re-reads rather than trusting that tagging left traffic alone.
  assert.equal(
    (tagFn.match(/Tagging moved traffic to \$revision/g) || []).length,
    1,
    "the tag operation must verify traffic did not move",
  );
  assert.match(tagFn, /require_confirmation "\$revision"/, "tagging is a mutation and must be confirmed");
  assert.doesNotMatch(tagFn, /update-traffic[\s\S]{0,120}--to-revisions/, "tagging must never route traffic");
});

test("a failed gate leaves the candidate at zero traffic", () => {
  // The gate precedes promotion and the job stops on failure, so there is no
  // path from a failed identity check to a revision serving customers.
  const gate = workflow.indexOf("- name: Verify candidate runtime release identity before promotion");
  const promote = workflow.indexOf("- name: Promote exact candidate with automatic rollback on failed post-check");
  const between = workflow.slice(gate, promote);
  assert.doesNotMatch(between, /update-traffic|to-revisions|promote-worker/, "nothing may route traffic between the gate and promotion");
});

test("promotion rolls back when the promoted revision computes the wrong identity", () => {
  const promote = workflow.match(/name: Promote exact candidate[\s\S]*?\n {6}- name: Publish exact promotion status/)[0];
  assert.match(promote, /OPERATION=verify-worker-runtime-revision/, "promotion must read runtime truth");
  const call = promote.match(/if ! OPERATION=verify-worker-runtime-revision[\s\S]*?\n {10}fi/)[0];
  assert.match(call, /TARGET_REVISION="\$REVISION"/, "it must check the revision just promoted");
  assert.match(call, /rollback/, "a wrong identity must roll traffic back");
  assert.match(call, /exit 1/);
  assert.doesNotMatch(call, /\|\| true|continue-on-error/, "the guard must not be advisory");
  // It has to run after traffic actually moves, or it reads the old revision.
  assert.ok(
    promote.indexOf("Expected 100% traffic on") < promote.indexOf("OPERATION=verify-worker-runtime-revision"),
    "the runtime check must follow the traffic assertion",
  );
});

test("the worker invoker token is minted by the workflow, not by gcloud", () => {
  // Same failure the coordinator token already hit: an external_account
  // credential cannot mint an audience-scoped identity token, so a script that
  // tries makes every promotion INDETERMINATE and rolls back a healthy release.
  assert.doesNotMatch(operator, /print-identity-token/);
  const consumed = operator.match(/token="\$(FIXLIST_WORKER_ID_TOKEN)"/);
  assert.ok(consumed, "the guard no longer reads its token from a named environment variable");
  const produced = workflow.match(
    /(FIXLIST_WORKER_ID_TOKEN): \$\{\{ steps\.([A-Za-z0-9_-]+)\.outputs\.id_token \}\}/,
  );
  assert.ok(produced, "the workflow never hands a worker id_token to the promotion step");
  const mint = workflow.match(new RegExp(`id: ${produced[2]}\\n[\\s\\S]*?create_credentials_file: false`));
  assert.ok(mint, "the worker token is not minted with create_credentials_file: false");
  assert.match(mint[0], /token_format: id_token/);
  // The audience must be the canonical Cloud Run service URL. A traffic-tag
  // probe is a separate destination, so the workflow must not bind the token
  // audience to the tag URL.
  const gate = workflow.indexOf("- name: Verify candidate runtime release identity before promotion", mint);
  assert.notEqual(gate, -1, "candidate runtime gate is missing after token mint");
  const audienceStep = workflow.slice(mint, gate).match(/id_token_audience: \$\{\{ steps\.([A-Za-z0-9_-]+)\.outputs\.([a-z_]+) \}\}/);
  assert.ok(audienceStep, "the worker token is not bound to the canonical service URL");
  assert.equal(audienceStep[1], "candidate-service-url");
  assert.match(
    workflow,
    /FIXLIST_WORKER_PROBE_URL: \$\{\{ steps\.candidate-tag\.outputs\.url \}\}/,
    "the candidate request must still target the exact tagged revision",
  );
  assert.match(operator, /FIXLIST_WORKER_TOKEN_AUDIENCE="\$\{FIXLIST_WORKER_TOKEN_AUDIENCE:-\}"/);
});

test("end to end: a container stamped with a different commit than the release fails", () => {
  const service = serving("worker-00054-trs");
  const promoted = "a".repeat(40);
  const mismatch = runGuard({
    service,
    revision: "worker-00054-trs",
    body: { ...LIVE_MATCHING, source_sha: "b".repeat(40) },
    sourceSha: promoted,
  });
  assert.notEqual(mismatch.status, 0, "a container built from another commit must not pass");
  assert.doesNotMatch(mismatch.stdout, /PASS:/);
  const agreeing = runGuard({
    service,
    revision: "worker-00054-trs",
    body: { ...LIVE_MATCHING, source_sha: promoted },
    sourceSha: promoted,
  });
  assert.equal(agreeing.status, 0, agreeing.stdout);
});
