import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const analytics = readFileSync("src/lib/analytics.js", "utf8");
const checkout = readFileSync("src/components/billing/UnlockAccessButton.jsx", "utf8");
const billing = readFileSync("src/pages/Billing.jsx", "utf8");
const scan = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const auth = readFileSync("src/lib/AuthContext.jsx", "utf8");

test("the paid beta funnel declares checkout, return, activation, and accepted-scan events", () => {
  for (const event of [
    "checkout_started",
    "payment_returned",
    "access_activated",
    "access_activation_delayed",
    "scan_accepted",
    "result_viewed",
    "fix_opened",
  ]) {
    assert.match(analytics, new RegExp(`${event}:`));
  }
});

test("checkout emits once per in-page attempt and resets only after a safe failure", () => {
  assert.match(checkout, /checkoutStartedRef\.current/);
  assert.match(checkout, /queueEvent\("checkout_started", \{ plan: "standard_150" \}\)/);
  const invoke = checkout.indexOf('.invoke("createAccessCheckout"');
  assert.ok(checkout.indexOf('queueEvent("checkout_started"') < invoke);
  assert.ok(checkout.lastIndexOf("checkoutStartedRef.current = false") > invoke);
});

test("queued registration and checkout events flush only after authentication is restored", () => {
  assert.match(auth, /import \{ flushQueuedEvents \} from ['"]@\/lib\/analytics['"]/);
  const authenticated = auth.match(/const currentUser = await base44\.auth\.me\(\);[\s\S]*?setAuthChecked\(true\);[\s\S]*?flushQueuedEvents\(\);/)?.[0] || "";
  assert.ok(authenticated, "authenticated app startup must flush the durable session queue");
  assert.match(analytics, /for \(const event of pending\)/);
  assert.match(analytics, /if \(!await trackEvent\(event\.eventName, event\.metadata\)\) remaining\.push\(event\)/);
  assert.match(analytics, /sessionStorage\.setItem\(QUEUE_KEY, JSON\.stringify\(remaining\.slice\(-10\)\)\)/);
});

test("Stripe return and activation outcomes are deduplicated in the Billing journey", () => {
  assert.match(billing, /paymentReturnTrackedRef/);
  assert.match(billing, /activationOutcomeTrackedRef/);
  assert.match(billing, /trackEvent\("payment_returned"/);
  assert.match(billing, /trackEvent\("access_activated"/);
  assert.match(billing, /trackEvent\("access_activation_delayed"/);
});

test("scan acceptance is emitted only after the exact durable job is accepted", () => {
  const acceptedBranch = scan.match(/if \(jobData\?\.accepted === true[\s\S]*?navigate\(`\/dashboard\?scan_id=/)?.[0] || "";
  assert.match(acceptedBranch, /asyncDispatcherStarted = true/);
  assert.match(acceptedBranch, /trackEvent\("scan_accepted", \{ scan_mode: STANDARD_SCAN_MODE \}\)/);
});
