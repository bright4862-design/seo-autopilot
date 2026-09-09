import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const claimPath = "base44/functions/claimComplimentaryAccess/entry.ts";
const accessPath = "src/lib/access.js";

test("frontend claims only an exact-email unbound manual grant before deciding access", () => {
  const accessSource = readFileSync(accessPath, "utf8");
  assert.match(accessSource, /grant_source === "manual_grant"/);
  assert.match(accessSource, /!String\(record\.owner_user_id \|\| ""\)\.trim\(\)/);
  assert.match(accessSource, /invoke\("claimComplimentaryAccess"/);
});

test("complimentary claim binds an eligible exact-email grant to the authenticated user once", async () => {
  assert.equal(existsSync(claimPath), true, "claimComplimentaryAccess function must exist");
  const source = readFileSync(claimPath, "utf8");
  const withoutImports = source.replace(/^import .*;\s*$/gm, "");
  const moduleSource = `const { createClientFromRequest, console = globalThis.console } = globalThis.__complimentaryClaimHarness;\n${withoutImports}`;
  let accessRecord = {
    id: "access-ryan",
    user_email: "rlane@loveandsandwiches.com",
    owner_user_id: "",
    access_status: "active",
    plan_id: "standard150_lifetime",
    grant_source: "manual_grant",
    app_id: "6a498732ec779dfaaeab0e53",
    has_full_access: true,
    granted_at: "2026-09-09T16:00:00.000Z",
  };
  let updates = 0;
  let authUser = { id: "user-ryan", email: "rlane@loveandsandwiches.com" };

  const Access = {
    async filter(query) {
      return query.user_email === accessRecord.user_email ? [{ ...accessRecord }] : [];
    },
    async update(id, fields) {
      assert.equal(id, accessRecord.id);
      updates += 1;
      accessRecord = { ...accessRecord, ...fields };
      return { ...accessRecord };
    },
  };
  globalThis.__complimentaryClaimHarness = {
    createClientFromRequest: () => ({
      auth: { me: async () => ({ ...authUser }) },
      asServiceRole: { entities: { Access } },
    }),
    console: { error: () => {} },
  };

  try {
    const { default: handler } = await import(
      `data:text/javascript;base64,${Buffer.from(moduleSource).toString("base64")}`
    );
    const invoke = () => handler(new Request("https://function.test", { method: "POST" }));

    const first = await invoke();
    assert.equal(first.status, 200);
    const firstBody = await first.json();
    assert.equal(firstBody.success, true);
    assert.equal(firstBody.claimed, true);
    assert.equal(firstBody.access.owner_user_id, "user-ryan");
    assert.equal(updates, 1);

    const replay = await invoke();
    assert.equal(replay.status, 200);
    const replayBody = await replay.json();
    assert.equal(replayBody.claimed, false);
    assert.equal(replayBody.access.owner_user_id, "user-ryan");
    assert.equal(updates, 1, "replay must not rewrite the grant");

    authUser = { id: "user-other", email: "other@example.com" };
    const other = await invoke();
    assert.equal(other.status, 404);
    assert.equal(updates, 1, "another email cannot claim Ryan's grant");
  } finally {
    delete globalThis.__complimentaryClaimHarness;
  }
});
