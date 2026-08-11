import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ACCESS_APP_ID,
  ACCESS_PLAN_ID,
  evaluatePaidAccess,
} from "../../base44/functions/startStandardScanJob/entitlement.js";

const checkout = readFileSync("base44/functions/createAccessCheckout/entry.ts", "utf8");
const webhook = readFileSync("base44/functions/stripeWebhook/entry.ts", "utf8");
const accessClient = readFileSync("src/lib/access.js", "utf8");
const billing = readFileSync("src/pages/Billing.jsx", "utf8");
const scanForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const persistence = readFileSync("base44/functions/persistDurableScanAuthority/index.ts", "utf8");
const accessSchema = JSON.parse(readFileSync("base44/entities/Access.jsonc", "utf8"));

const user = { id: "user-1", email: "paid@example.com" };
const active = {
  id: "access-1",
  owner_user_id: user.id,
  user_email: user.email,
  has_full_access: true,
  access_status: "active",
  plan_id: ACCESS_PLAN_ID,
  grant_source: "stripe_checkout",
  app_id: ACCESS_APP_ID,
  paid_at: "2026-08-11T12:00:00.000Z",
  stripe_checkout_session_id: "cs_paid_1",
};

test("checkout, webhook and customer copy share one $50 contract", () => {
  assert.match(checkout, /unit_amount: 5000/);
  assert.match(webhook, /const EXPECTED_AMOUNT = 5000;/);
  assert.match(accessClient, /UNLOCK_PRICE_LABEL = "\$50"/);
  assert.match(billing, /price: "\$50 one-time"/);

  for (const [name, source] of Object.entries({ checkout, webhook, accessClient, billing, scanForm })) {
    assert.doesNotMatch(source, /\$30|\$75|unit_amount:\s*3000|unit_amount:\s*7500/, name);
  }
});

test("customer copy is paid-only and contains no free-scan promise", () => {
  for (const [name, source] of Object.entries({ accessClient, billing, scanForm })) {
    assert.doesNotMatch(source, /free test scan|one free scan|Run free scan/i, name);
  }
  assert.match(billing, /one-time payment/i);
  assert.match(billing, /Standard 150 beta/);
});

test("paid admission fails closed for missing, unpaid and duplicate rows", () => {
  assert.deepEqual(evaluatePaidAccess({ rows: [], user }), {
    ok: false,
    failureCode: "paid_access_required",
  });
  assert.equal(evaluatePaidAccess({ rows: [{ ...active, has_full_access: false }], user }).ok, false);
  assert.equal(evaluatePaidAccess({ rows: [active, { ...active, id: "access-2" }], user }).failureCode, "paid_access_conflict");
  assert.equal(evaluatePaidAccess({ rows: [active], user }).ok, true);
});

test("an entitlement is bound to the exact owner, email, app and Stripe grant", () => {
  for (const changed of [
    { owner_user_id: "other" },
    { user_email: "other@example.com" },
    { app_id: "other-app" },
    { plan_id: "other-plan" },
    { grant_source: "manual" },
    { stripe_checkout_session_id: "" },
    { paid_at: "" },
  ]) {
    assert.equal(evaluatePaidAccess({ rows: [{ ...active, ...changed }], user }).ok, false);
  }
});

test("Access writes are backend-only and completion is billing-independent", () => {
  for (const action of ["create", "update", "delete"]) {
    assert.equal(accessSchema.rls[action].user_condition.role, "admin");
  }
  assert.ok(accessSchema.rls.read.$or.some((rule) => rule.owner_user_id === "{{user.id}}"));
  assert.ok(accessSchema.rls.read.$or.some((rule) => rule.user_email === "{{user.email}}"));
  assert.equal("scans_used" in accessSchema.properties, false);
  assert.doesNotMatch(scanForm, /recordScanUsed|Access\.create|Access\.update|scans_used/);
  assert.doesNotMatch(persistence, /entities\.Access|scans_used|ensureAllowanceConsumed/);
});
