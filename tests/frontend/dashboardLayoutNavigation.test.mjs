import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { build } from "esbuild";

const layoutPath = new URL("../../src/components/layout/DashboardLayout.jsx", import.meta.url);
const source = readFileSync(layoutPath, "utf8");

// Bundle the real layout. Only the auth hook is replaced; React, the router and
// icons resolve to the same module instances this test renders with.
const bundled = await build({
  entryPoints: [layoutPath.pathname],
  bundle: true,
  write: false,
  format: "esm",
  jsx: "transform",
  logLevel: "silent",
  plugins: [{
    name: "dashboard-layout-test",
    setup(builder) {
      builder.onResolve({ filter: /^@\/lib\/AuthContext$/ }, () => ({ path: "auth", namespace: "stub" }));
      builder.onLoad({ filter: /.*/, namespace: "stub" }, () => ({
        contents: "export function useAuth() { return { logout: async () => {} }; }",
        loader: "js",
      }));
      builder.onResolve({ filter: /^(react|react\/jsx-runtime|react-router-dom|lucide-react)$/ }, (args) => ({
        path: import.meta.resolve(args.path),
        external: true,
      }));
    },
  }],
});
const { default: DashboardLayout } = await import(
  `data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString("base64")}`
);

function render(pathname) {
  return renderToStaticMarkup(
    React.createElement(MemoryRouter, { initialEntries: [pathname] }, React.createElement(DashboardLayout)),
  );
}

function navigations(html) {
  const navs = [...html.matchAll(/<nav\b[^>]*>[\s\S]*?<\/nav>/g)].map((match) => match[0]);
  assert.equal(navs.length, 2, "one direct desktop navigation and one mobile menu");
  const [desktop, mobile] = navs;
  return { desktop, mobile };
}

function links(nav) {
  return [...nav.matchAll(/<a\b([^>]*)>([^<]*)<\/a>/g)].map(([, attributes, label]) => ({
    label,
    href: attributes.match(/href="([^"]+)"/)?.[1],
    current: /aria-current="page"/.test(attributes),
  }));
}

const ROUTES = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "New scan", href: "/onboarding" },
  { label: "Billing", href: "/billing" },
  { label: "Account", href: "/account" },
];

test("both navigations expose all four routes and logout, with no scroll-clipped overflow", () => {
  const { desktop, mobile } = navigations(render("/dashboard"));
  for (const nav of [desktop, mobile]) {
    assert.deepEqual(links(nav).map(({ label, href }) => ({ label, href })), ROUTES);
    assert.match(nav, /<button[^>]*type="button"[^>]*>Log out<\/button>/);
  }
  assert.doesNotMatch(source, /overflow-x-auto|overflow-hidden/);
});

test("desktop keeps direct links while small screens get a compact disclosure menu", () => {
  const html = render("/billing");
  const { desktop, mobile } = navigations(html);
  assert.match(desktop, /^<nav class="[^"]*\bhidden\b[^"]*\bsm:flex\b/);
  const toggle = html.match(/<button[^>]*aria-expanded="false"[^>]*>[\s\S]*?Menu<\/button>/);
  assert.ok(toggle, "a collapsed Menu toggle is rendered");
  assert.match(toggle[0], /\bsm:hidden\b/);
  const controls = toggle[0].match(/aria-controls="([^"]+)"/)?.[1];
  assert.ok(controls, "toggle names the menu it controls");
  assert.match(mobile, new RegExp(`^<nav id="${controls.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"[^>]*\\bhidden=""`));
  assert.match(mobile, /\bsm:hidden\b/);
  // Menu rows are comfortable touch targets.
  assert.equal((mobile.match(/min-h-11/g) || []).length, 5);
});

test("the header aligns with the 880px results column", () => {
  const html = render("/dashboard");
  assert.match(html, /<header[\s\S]*?mx-auto flex h-14 max-w-\[880px\]/);
});

for (const [pathname, expected] of [
  ["/dashboard", "Dashboard"],
  ["/fix-list", "Dashboard"],
  ["/issues", "Dashboard"],
  ["/onboarding", "New scan"],
  ["/scan", "New scan"],
  ["/crawl-status", "New scan"],
  ["/billing", "Billing"],
  ["/billing/receipt", "Billing"],
  ["/account", "Account"],
  ["/accounting", null],
  ["/login", null],
]) {
  test(`exact active route for ${pathname} is identical in both navigations`, () => {
    const { desktop, mobile } = navigations(render(pathname));
    for (const nav of [desktop, mobile]) {
      const current = links(nav).filter((link) => link.current).map((link) => link.label);
      assert.deepEqual(current, expected ? [expected] : []);
    }
  });
}

test("menu behaviour closes on navigation and Escape and keeps the logout contract", () => {
  // Interaction itself is exercised in a browser; these pin the wiring.
  assert.match(source, /onClick=\{\(\) => closeMenu\(true\)\}/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /previousPathRef\.current === location\.pathname/);
  assert.match(source, /menuButtonRef\.current\?\.focus\(\)/);
  assert.equal((source.match(/onClick=\{handleLogout\}/g) || []).length, 2);
  assert.match(source, /await logout\(false\)/);
  assert.match(source, /navigate\("\/login", \{ replace: true \}\)/);
});
