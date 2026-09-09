import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const checkoutPath = "base44/functions/createAccessCheckout/entry.ts";
const accessPath = "src/lib/access.js";
const checkoutSource = readFileSync(checkoutPath, "utf8");

async function importCheckoutWithHarness(harnessName) {
  const withoutImports = checkoutSource.replace(/^import .*;\s*$/gm, "");
  const harnessPrelude = `const { createClientFromRequest, Stripe, secrets, console = globalThis.console } = globalThis.${harnessName};`;
  return import(`data:text/javascript;base64,${Buffer.from(`${harnessPrelude}\n${withoutImports}`).toString("base64")}`);
}

test("frontend claims only an exact-email unbound manual grant before deciding access", () => {
  const accessSource = readFileSync(accessPath, "utf8");
  assert.match(accessSource, /grant_source === "manual_grant"/);
  assert.match(accessSource, /!String\(record\.owner_user_id \|\| ""\)\.trim\(\)/);
  assert.match(accessSource, /invoke\("createAccessCheckout", \{ action: "claim_complimentary_access" \}\)/);
});

test("complimentary claim binds an eligible exact-email grant to the authenticated user once without checkout", async () => {
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
  let sessionCreates = 0;
  let authUser = { id: "user-ryan", email: "rlane@loveandsandwiches.com" };

  const Access = {
    async filter(query) {
      const byOwner = query.owner_user_id && query.owner_user_id === accessRecord.owner_user_id;
      const byEmail = query.user_email && query.user_email === accessRecord.user_email;
      return byOwner || byEmail ? [{ ...accessRecord }] : [];
    },
    async update(id, fields) {
      assert.equal(id, accessRecord.id);
      updates += 1;
      accessRecord = { ...accessRecord, ...fields };
      return { ...accessRecord };
    },
    async create() { throw new Error("claim must never create access"); },
    async delete() { throw new Error("claim must never delete access"); },
  };
  const base44 = {
    auth: { me: async () => ({ ...authUser }) },
    asServiceRole: { entities: { Access } },
  };
  class FakeStripe {
    constructor() {
      this.checkout = { sessions: {
        create: async () => { sessionCreates += 1; throw new Error("claim must never open Stripe"); },
        retrieve: async () => { throw new Error("claim must never read Stripe"); },
      }};
    }
  }

  globalThis.__complimentaryCheckoutHarness = {
    createClientFromRequest: () => base44,
    Stripe: FakeStripe,
    secrets: { get: () => { throw new Error("claim must not require checkout secrets"); } },
    console: { error: () => {} },
  };

  try {
    const { default: handler } = await importCheckoutWithHarness("__complimentaryCheckoutHarness");
    const invoke = () => handler(new Request("https://function.test", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "claim_complimentary_access" }),
    }));

    const first = await invoke();
    assert.equal(first.status, 200);
    const firstBody = await first.json();
    assert.equal(firstBody.success, true);
    assert.equal(firstBody.claimed, true);
    assert.equal(firstBody.access.owner_user_id, "user-ryan");
    assert.equal(updates, 1);
    assert.equal(sessionCreates, 0);

    const replay = await invoke();
    assert.equal(replay.status, 200);
    const replayBody = await replay.json();
    assert.equal(replayBody.claimed, false);
    assert.equal(updates, 1, "replay must not rewrite the grant");

    authUser = { id: "user-other", email: "other@example.com" };
    const other = await invoke();
    assert.equal(other.status, 404);
    assert.equal(updates, 1, "another email cannot claim Ryan's grant");
  } finally {
    delete globalThis.__complimentaryCheckoutHarness;
  }
});
