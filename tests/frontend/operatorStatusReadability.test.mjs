import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";

/**
 * `show_status` used to report a missing resource and an unreadable one with the
 * same `not_deployed=` line, because it sent stderr to /dev/null and branched on
 * the exit status alone. On 2026-09-03 that made a live Standard 150 status read
 * announce `not_deployed=fixlist-standard150-drain` for a drain queue the
 * operator service account simply could not see -- which invites recreating a
 * queue that already exists.
 *
 * These run the real bash function rather than grepping for it, so the
 * classification is proven.
 */

const OPERATOR = "scripts/fixlist-cloud-operator.sh";
const source = readFileSync(OPERATOR, "utf8");
const workflow = readFileSync(".github/workflows/fixlist-cloud-operator.yml", "utf8");

// The script runs its allowlisted operation on load, so the function is lifted
// out and evaluated on its own instead of sourcing the whole file.
function describeOrExplain({ exitCode, stderr, stdout = "" }) {
  const fn = source.match(/^describe_or_explain\(\) \{[\s\S]*?^\}/m);
  assert.ok(fn, "describe_or_explain is missing from the operator script");
  const script = `
    ${fn[0]}
    stub() { printf '%s' ${JSON.stringify(stdout)}; printf '%s' ${JSON.stringify(stderr)} >&2; return ${exitCode}; }
    describe_or_explain "fixlist-standard150-drain" stub
  `;
  return execFileSync("bash", ["-c", script], { encoding: "utf8" }).trim();
}

test("an unreadable resource is reported as denied, not as missing", () => {
  const denied = describeOrExplain({
    exitCode: 1,
    stderr:
      'ERROR: (gcloud.tasks.queues.describe) PERMISSION_DENIED: The principal lacks IAM permission "cloudtasks.queues.get"',
  });
  assert.equal(denied, "read_denied=fixlist-standard150-drain");
  assert.ok(!denied.includes("not_deployed"), "a denied read must not claim the resource is absent");
});

test("a genuinely absent resource is still reported as not deployed", () => {
  const absent = describeOrExplain({
    exitCode: 1,
    stderr: "ERROR: (gcloud.tasks.queues.describe) NOT_FOUND: Queue does not exist.",
  });
  assert.equal(absent, "not_deployed=fixlist-standard150-drain");
});

test("a readable resource passes its description through unchanged", () => {
  const ok = describeOrExplain({ exitCode: 0, stderr: "", stdout: "state: RUNNING" });
  assert.equal(ok, "state: RUNNING");
});

test("the operator script no longer discards describe stderr for these reads", () => {
  for (const resource of [
    "CLOUD_TASKS_DRAIN_QUEUE",
    "ADMISSION_COORDINATOR_SERVICE",
    "STANDARD150_RECONCILER_JOB",
  ]) {
    assert.match(
      source,
      new RegExp(`describe_or_explain "\\$${resource}"`),
      `${resource} must be read through the classifying helper`,
    );
  }
  assert.doesNotMatch(
    source,
    />\/dev\/null 2>&1; then\n\s*gcloud (tasks queues|run services|scheduler jobs) describe/,
    "no status read may branch on a silenced describe",
  );
});

test("status authenticates as the identity that can actually read every resource", () => {
  // fixlist-admission-operator already holds cloudtasks.queueAdmin on both
  // queues, cloudscheduler.admin and project run.viewer. Routing the read-only
  // status operation to it makes the report truthful without widening any
  // service account.
  const identityLines = workflow
    .split("\n")
    .filter((line) => /service_account:|GCP_OPERATOR_SERVICE_ACCOUNT:/.test(line) && line.includes("fromJSON"));
  assert.equal(identityLines.length, 2, "expected exactly two identity-selection expressions");
  for (const line of identityLines) {
    assert.ok(line.includes('"status"'), "status must resolve to the admission operator identity");
  }

  // The coordinator token mint is a different list; status never calls the
  // coordinator, so it must not appear there.
  const mintLine = workflow
    .split("\n")
    .find((line) => line.trim().startsWith("if: contains(fromJSON(") && line.includes("barrier-status"));
  assert.ok(mintLine, "coordinator token-mint guard is missing");
  assert.ok(!mintLine.includes('"status"'), "status must not mint a coordinator identity token");
});

test("status reads the admission coordinator's own logs, not only the worker's", () => {
  // The coordinator decides admission. When it refuses, the browser shows one
  // deliberately vague message ("Scan admission is temporarily unavailable")
  // for admission_unreachable, a rejected signature, and an unexpected upstream
  // code alike -- so the coordinator's log is the only place the actual reason
  // exists. On 2026-09-03 a refused Funbooker scan could not be diagnosed at
  // all: status read the worker service and never the coordinator.
  const reads = [...source.matchAll(/gcloud logging read/g)];
  assert.ok(reads.length >= 4, "status must read both worker and coordinator logs");

  assert.match(
    source,
    /service_name=\\"\$ADMISSION_COORDINATOR_SERVICE\\"/,
    "the coordinator's structured logs must be read by service name",
  );
  assert.match(
    source,
    /ADMISSION_COORDINATOR_SERVICE[\s\S]*?run\.googleapis\.com%2Frequests/,
    "the coordinator's request log must be read too, so a rejection's status code is visible",
  );
  // A refusal reason is useless if the read aborts the whole status operation.
  const coordinatorBlock = source.slice(
    source.indexOf("=== Recent admission coordinator logs ==="),
    source.indexOf("=== Recent worker structured logs ==="),
  );
  assert.equal(
    (coordinatorBlock.match(/\|\| true/g) || []).length,
    2,
    "both coordinator reads must be non-fatal so status still reports the rest",
  );
});

test("every status log read is bounded to a recent window, not the oldest entries", () => {
  // gcloud does not apply --freshness when entries are ordered ascending: the
  // read returns the OLDEST matching entries. On 2026-09-03 that made a live
  // status read report coordinator activity from 2026-08-15 while an operator
  // waited on the last half hour -- the log was readable and still answered the
  // wrong question.
  assert.doesNotMatch(
    source.replace(/^\s*#.*$/gm, ""),
    /--freshness/,
    "no log read may rely on --freshness while ordering ascending",
  );
  const reads = source.match(/gcloud logging read[\s\S]*?--format=/g) || [];
  assert.ok(reads.length >= 4, "expected the worker and coordinator log reads");
  for (const read of reads) {
    assert.match(read, /timestamp>=\\"\$log_since\\"/, "each read must bound its own window");
  }
  assert.match(source, /log_since="\$\(date -u -d '-30 minutes'/, "the window must be computed once");
});

test("status reports whether the coordinator can be reached at all", () => {
  // On 2026-09-03 every customer scan died with a 401 in ~3ms and no coordinator
  // application log, because run.invoker was held only by the admission operator
  // and Base44 -- which signs claims with an HMAC and holds no Google
  // credentials by design -- had no principal it could present. Every other
  // status field showed a healthy coordinator: correct revision, 100% traffic,
  // operator calls returning 200. Reachability is the one thing that decides
  // whether a customer scan can start, and status did not report it.
  const block = source.slice(
    source.indexOf("=== Admission coordinator reachability ==="),
    source.indexOf("=== Reconciler ==="),
  );
  assert.ok(block.length > 0, "status must report coordinator reachability");
  assert.match(block, /run\.googleapis\.com\/ingress/, "ingress must be reported");
  assert.match(block, /get-iam-policy "\$ADMISSION_COORDINATOR_SERVICE"/, "the invoker policy must be reported");

  // Both reads go through the classifier, so a denied read can never be
  // mistaken for an absent setting -- the same failure that made a live status
  // read announce not_deployed= for a queue the operator simply could not see.
  assert.equal(
    (block.match(/describe_or_explain/g) || []).length,
    2,
    "both reachability reads must classify a denied read rather than reporting absence",
  );
});
