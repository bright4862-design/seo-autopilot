import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const access = readFileSync("src/lib/access.js", "utf8");

test("frontend access mirrors the exact owner-bound manual grant policy", () => {
  assert.match(access, /normalizeEmail\(record\.user_email\) === email/);
  assert.match(access, /String\(record\.owner_user_id \|\| ""\) === userId/);
  assert.match(access, /record\.grant_source === "manual_grant" && Boolean\(record\.granted_at\)/);
  assert.match(access, /return identityMatches && activeGrant && \(paidGrant \|\| ownerTestGrant \|\| manualGrant\)/);
  assert.doesNotMatch(access, /!record\.owner_user_id|!String\(record\.owner_user_id/);
});
