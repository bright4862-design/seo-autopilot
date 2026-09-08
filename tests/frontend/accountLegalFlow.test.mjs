import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync("src/App.jsx", "utf8");
const layout = readFileSync("src/components/layout/DashboardLayout.jsx", "utf8");
const billing = readFileSync("src/pages/Billing.jsx", "utf8");
const account = readFileSync("src/pages/Account.jsx", "utf8");

test("the authenticated app exposes an Account page in the protected shell", () => {
  assert.match(app, /import Account from ["']@\/pages\/Account["']/);
  assert.match(app, /<Route path="\/account" element=\{<Account \/>\} \/>/);
  assert.match(layout, /\{ name: "Account", href: "\/account" \}/);
});

test("successful Stripe return hands the customer from Billing to Account", () => {
  const successBlock = billing.match(/access\?\.fullAccess \? \([\s\S]*?\) : checkoutSuppressed/)?.[0] || "";
  assert.match(successBlock, /returnedFromCheckout/);
  assert.match(successBlock, /navigate\("\/account"\)/);
  assert.match(successBlock, /Continue to your account/);
});

test("Account gives paid customers clear product access and legal information", () => {
  assert.match(account, /Your FixList access/);
  assert.match(account, /Standard 150/);
  assert.match(account, /Run a scan/);
  assert.match(account, /Terms & Conditions/);
  assert.match(account, /Privacy & Data/);
  assert.match(account, /publicly accessible website/);
  assert.match(account, /does not guarantee rankings/i);
});

test("Account does not misstate access when the access lookup fails", () => {
  assert.match(account, /accessUnavailable/);
  assert.match(account, /Access status temporarily unavailable/);
});

test("privacy copy accurately describes payment and operational data handling", () => {
  assert.match(account, /Stripe/);
  assert.match(account, /full card details/i);
  assert.match(account, /submitted website URLs/i);
  assert.match(account, /scan results and history/i);
  assert.match(account, /usage events/i);
  assert.match(account, /do not sell/i);
});
