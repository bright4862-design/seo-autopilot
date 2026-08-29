import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// The recovery script deletes production functions. Everything that keeps that
// narrow -- the allowlist, the pre-delete proof, the one-at-a-time ordering --
// is a safety property, not a style choice, so it is asserted here.
const recovery = readFileSync("scripts/recover-base44-unrouted-functions.sh", "utf8");

// The header documents the operations the script must never perform, so a
// forbidden-operation sweep has to read executable lines only or it matches the
// prose that forbids them. Whole-line comments only: `${#ARRAY[@]}` is code.
const recoveryCode = recovery
  .split("\n")
  .filter((line) => !/^\s*#/.test(line))
  .join("\n");

const RECOVERABLE = [
  "ownerScanDebugControl",
  "durableScanWorkerControl",
  "persistDurableScanAuthority",
  "persistLimitedScanResult",
  "deleteCustomerScanData",
];

// These four answer production traffic today. stripeWebhook takes payment
// callbacks and startStandardScanJob is scan intake, so a delete here is not
// recoverable by redeploying.
const PROTECTED = [
  "startStandardScanJob",
  "getCustomerScanResult",
  "createAccessCheckout",
  "stripeWebhook",
];

function arrayLiteral(name) {
  const match = recovery.match(new RegExp(`${name}=\\(([^)]*)\\)`));
  assert.ok(match, `${name} array not found in the recovery script`);
  return match[1].split("\n").map((line) => line.trim()).filter(Boolean);
}

test("recovery touches exactly the five unrouted functions, canary first", () => {
  assert.deepEqual(arrayLiteral("RECOVERY_FUNCTIONS"), RECOVERABLE);
  // ownerScanDebugControl is owner-only with no worker dependency, so it proves
  // the delete/recreate mechanism before the durable scan path moves.
  assert.equal(arrayLiteral("RECOVERY_FUNCTIONS")[0], "ownerScanDebugControl");
});

test("the four live functions are declared protected and never recovered", () => {
  assert.deepEqual(arrayLiteral("PROTECTED_FUNCTIONS"), PROTECTED);
  const recoveryList = arrayLiteral("RECOVERY_FUNCTIONS");
  for (const name of PROTECTED) {
    assert.ok(
      !recoveryList.includes(name),
      `${name} serves live traffic and must never be in RECOVERY_FUNCTIONS`,
    );
  }
  // A future edit that moves a protected name into the recovery list must fail
  // closed at runtime too, not just here.
  assert.match(recovery, /must never be deleted/);
});

test("a function is deleted only after its route is proven unregistered", () => {
  assert.match(recovery, /route_is_recovered/);
  assert.match(recovery, /not deleting a live route/);
  assert.match(recovery, /ROUTER_MISSING_MARKER="user worker not found"/);
  // The delete must come after the pre-state check inside recover_one. Assert
  // both markers are present first: a bare index comparison passes on -1, so
  // deleting the check outright would otherwise satisfy the ordering.
  const body = recovery.slice(recovery.indexOf("recover_one() {"));
  const guardAt = body.indexOf("route_is_unregistered");
  const deleteAt = body.indexOf("functions delete");
  assert.ok(guardAt >= 0, "recover_one must call route_is_unregistered");
  assert.ok(deleteAt >= 0, "recover_one must be the only place that deletes");
  assert.ok(
    guardAt < deleteAt,
    "recover_one must prove the router-level 404 before deleting",
  );
});

test("each recreation is confirmed by inventory membership and a live probe", () => {
  // `functions delete` reports failures in prose and still exits zero, so the
  // outcome is read back from `functions list` instead of parsed from output.
  assert.match(recovery, /still present in the remote inventory after delete/);
  assert.match(recovery, /did not reappear in the remote inventory after deploy/);
  assert.match(recovery, /require_handled_route "\$name"/);
  assert.match(recovery, /did not answer 405 method_not_allowed after recreation/);
});

test("recovery keeps the release guards and adds no new privilege", () => {
  assert.match(recovery, /release-source-guard\.sh/);
  assert.match(recovery, /base44-pinned-cli\.sh/);
  assert.match(recovery, /fixlist_require_exact_main "\$REPO_ROOT" "\$SOURCE_SHA" "\$CONFIRM"/);
  assert.match(recovery, /fixlist_install_base44_cli/);
  assert.match(recovery, /fixlist_require_base44_owner "\$BASE44_EXPECTED_OWNER"/);
  assert.match(recovery, /base44_release_manifest\.mjs" verify/);
  // Owner session only: the workspace-key path skips the identity assertion.
  assert.match(recovery, /unset BASE44_API_KEY and use the owner device-code session/);
});

test("recovery cannot prune, publish the site, or move release state", () => {
  assert.doesNotMatch(recoveryCode, /--force/);
  assert.doesNotMatch(recoveryCode, /site deploy/);
  assert.doesNotMatch(recoveryCode, /secrets set/);
  assert.doesNotMatch(recoveryCode, /fixlist_set_base44_release_source_sha/);
  assert.doesNotMatch(recoveryCode, /barrier|acceptance|cohort/i);
  assert.doesNotMatch(recoveryCode, /entities\s+push/);
  assert.doesNotMatch(recoveryCode, /fixlist-cloud-operator\.sh/);
});

test("the route probe is a read-only GET", () => {
  assert.match(recoveryCode, /curl -sS -o "\$body_file" -w '%\{http_code\}'/);
  assert.doesNotMatch(recoveryCode, /curl[^\n]*(-X\s*(POST|PUT|DELETE)|--data|-d\s)/);
});
