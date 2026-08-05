import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const mainSource = readFileSync(new URL("../../src/main.jsx", import.meta.url), "utf8");
const appSource = readFileSync(new URL("../../src/App.jsx", import.meta.url), "utf8");
const layoutSource = readFileSync(
  new URL("../../src/components/layout/DashboardLayout.jsx", import.meta.url),
  "utf8",
);
const authSource = readFileSync(new URL("../../src/lib/AuthContext.jsx", import.meta.url), "utf8");

test("the customer app is mounted inside the authentication provider", () => {
  assert.match(mainSource, /<AuthProvider>[\s\S]*<App \/>[\s\S]*<\/AuthProvider>/);
});

test("dashboard routes require a completed authenticated session", () => {
  assert.match(appSource, /<ProtectedRoute[\s\S]*unauthenticatedElement=\{<Navigate to="\/login" replace \/>\}/);
  assert.match(appSource, /<ProtectedRoute[\s\S]*<Route element=\{<DashboardLayout \/>\}>/);
});

test("logout clears the Base44 session before replacing the route", () => {
  assert.match(layoutSource, /await logout\(false\)/);
  assert.match(layoutSource, /navigate\("\/login", \{ replace: true \}\)/);
  assert.match(authSource, /clearCustomerBrowserCaches\(undefined, ["\']logout["\']\)/);
  assert.match(authSource, /return base44\.auth\.logout\(\)/);
  assert.ok(
    authSource.indexOf("clearCustomerBrowserCaches(undefined, 'logout')") < authSource.indexOf("base44.auth.logout"),
    "customer caches must be cleared before the Base44 logout request",
  );
  assert.match(authSource, /clearCustomerAuthBoundary\(/);
  assert.match(authSource, /CUSTOMER_BOUNDARY_EVENT/);
  assert.match(authSource, /event\?\.detail\?\.reason !== 'auth_expired'/);
  assert.match(authSource, /synchronizeAuthenticatedOwner\(currentUser\?\.id\)/);
});

test("app-state failures finish the auth check instead of leaving a permanent spinner", () => {
  const occurrences = authSource.match(/setAuthChecked\(true\)/g) || [];
  assert.ok(occurrences.length >= 4, "every auth/app-state terminal branch must finish the auth check");
});
