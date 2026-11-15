#!/usr/bin/env node
// Serve the exact committed V9 frontend on this computer against the FixList app.
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, readdir, realpath, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import stagedDeployments from "../data/generated-staged-v9-routes.json" with { type: "json" };

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const APP_ID = "6a498732ec779dfaaeab0e53";
const APP_ORIGIN = "https://getfixlist.base44.app";
const PUBLIC_SETTINGS = `/api/apps/public/prod/public-settings/by-id/${APP_ID}`;
const AUTH_CALLBACK = "/api/apps/auth/final-callback";
const APP_API_PATH = new RegExp(`^/api/apps/${APP_ID}/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*$`);
const FRONTEND_INPUTS = [
  "index.html", "src", "public", "base44", "package.json", "package-lock.json",
  "vite.config.js", "postcss.config.js", "tailwind.config.js", "data/base44-function-routes.json",
  "data/generated-staged-v9-routes.json",
];
const BUNDLE_MARKERS = [
  "__FIXLIST_SOURCE_SHA__",
  ...["startStandardScanJobV9", "getCustomerScanResultV9", "deleteCustomerScanDataV9"]
    .map(name => stagedDeployments.functions[name].route_name),
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function fixlistApiProxy() {
  return {
    target: APP_ORIGIN,
    changeOrigin: true,
    configure(proxy) {
      // This frontend takes its user session from Base44's normal browser login.
      // Local cookies must not travel upstream or overwrite preview cookies.
      proxy.on("proxyReq", (request) => request.removeHeader("cookie"));
      proxy.on("proxyRes", (response) => { delete response.headers["set-cookie"]; });
    },
  };
}

export function isPreviewAuthCallback(path, method, query, origin) {
  if (path !== AUTH_CALLBACK || method !== "GET" || query.size !== 2) return false;
  const code = query.get("login_code");
  const data = query.get("state");
  if (!/^[A-Za-z0-9_-]{16,500}$/.test(code ?? "") || !data || data.length > 3000) return false;
  try {
    const state = JSON.parse(data);
    const target = new URL(state.from_url);
    return state.app_id === APP_ID && state.domain === origin && target.origin === origin
      && !target.username && !target.password && !target.hash;
  } catch {
    return false;
  }
}

function restrictApiPaths(origin) {
  return {
    name: "fixlist-preview-scope",
    configurePreviewServer(server) {
      server.middlewares.use((request, response, next) => {
        const requestUrl = String(request.url || "");
        const rawPath = requestUrl.split("?", 1)[0];
        // Refuse ambiguity up front, before Vite parses the URL for proxying.
        const absolutePath = rawPath.startsWith("/") && !rawPath.startsWith("//") && !rawPath.includes("\\");
        const localApi = rawPath === "/api" || rawPath.startsWith("/api/");
        const publicSettings = rawPath === PUBLIC_SETTINGS && ["GET", "HEAD"].includes(request.method);
        const sameApp = APP_API_PATH.test(rawPath) && !rawPath.split("/").some((part) => part === "." || part === "..");
        const query = new URLSearchParams(requestUrl.slice(rawPath.length));
        const authCallback = isPreviewAuthCallback(rawPath, request.method, query, origin);
        // The application normally accepts app parameters from the entry URL.
        // Keep those parameters pinned even on an auth callback.
        const expectedApp = query.getAll("app_id").every((id) => id === APP_ID)
          && query.getAll("app_base_url").every((url) => url === APP_ORIGIN);
        if (absolutePath && expectedApp && (!localApi || publicSettings || sameApp || authCallback)) {
          next();
          return;
        }
        response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
        response.end("Preview route unavailable.");
      });
    },
  };
}

async function verifyBundle(dist, source) {
  const names = await readdir(join(dist, "assets"));
  const scripts = names.filter((name) => name.endsWith(".js"));
  const chunks = await Promise.all(scripts.map((name) => readFile(join(dist, "assets", name), "utf8")));
  for (const marker of [...BUNDLE_MARKERS, source]) {
    assert(chunks.some((chunk) => chunk.includes(marker)), "The preview build is missing its source or V9 route markers.");
  }
}

async function main() {
  const { values } = parseArgs({
    options: {
      "source-sha": { type: "string" },
      port: { type: "string", default: "4173" },
      check: { type: "boolean" },
      help: { type: "boolean", short: "h" },
    },
  });
  if (values.help) {
    console.log("Usage: node scripts/preview-base44-v9.mjs --source-sha <checked-out full SHA> [--port 4173] [--check]");
    console.log("Use the repository's pinned Node 20.19.5 and npm ci. --check builds, probes FixList public settings and exits.");
    return;
  }
  const source = values["source-sha"];
  assert(/^[0-9a-f]{40}$/.test(source || ""), "Pass the exact checked-out SHA with --source-sha.");
  const head = execFileSync("git", ["rev-parse", "HEAD"], { cwd: ROOT, encoding: "utf8" }).trim();
  assert(source === head, "The requested source must match the checkout.");
  const port = Number(values.port);
  assert(/^[0-9]{1,5}$/.test(values.port) && port >= 1024 && port <= 65535, "Use a preview port from 1024 to 65535.");

  const { build, preview } = await import("vite");
  const directory = await realpath(await mkdtemp(join(tmpdir(), "fixlist-v9-preview-")));
  const previousDirectory = process.cwd();
  let server;
  try {
    const tar = execFileSync("git", ["archive", source, ...FRONTEND_INPUTS], { cwd: ROOT, maxBuffer: 64 * 1024 * 1024 });
    execFileSync("tar", ["-xf", "-", "-C", directory], { input: tar });
    await symlink(join(ROOT, "node_modules"), join(directory, "node_modules"), "dir");
    process.chdir(directory);
    const expected = {
      VITE_BASE44_APP_ID: APP_ID,
      VITE_BASE44_APP_BASE_URL: APP_ORIGIN,
      VITE_SCAN_FUNCTION_GENERATION: "V9",
      VITE_FIXLIST_SOURCE_SHA: source,
    };
    for (const name of Object.keys(process.env)) {
      if (name.startsWith("VITE_")) delete process.env[name];
    }
    Object.assign(process.env, expected);
    const config = {
      root: directory,
      envDir: false,
      configFile: join(directory, "vite.config.js"),
      logLevel: "warn",
    };
    await build({
      ...config,
      plugins: [{
        name: "fixlist-preview-environment",
        configResolved(resolved) {
          for (const [key, value] of Object.entries(expected)) {
            assert(resolved.env[key] === value, "Vite did not resolve the expected FixList preview environment.");
          }
        },
      }],
    });
    await verifyBundle(join(directory, "dist"), source);
    const origin = `http://127.0.0.1:${port}`;
    server = await preview({
      ...config,
      plugins: [restrictApiPaths(origin)],
      preview: {
        host: "127.0.0.1",
        port,
        strictPort: true,
        cors: false,
        headers: { "X-Robots-Tag": "noindex, noarchive" },
        proxy: { "/api/": fixlistApiProxy() },
      },
    });
    const settings = await fetch(origin + PUBLIC_SETTINGS, { redirect: "error", signal: AbortSignal.timeout(10000) });
    assert(settings.ok && settings.headers.get("content-type")?.includes("application/json"), "FixList public settings did not reach the preview.");
    const body = await settings.json();
    assert(body?.id === APP_ID, "The preview public settings did not identify the FixList app.");
    const wrongApp = await fetch(origin + "/api/apps/preview-probe-wrong-app/entities/User/me", { signal: AbortSignal.timeout(5000) });
    assert(wrongApp.status === 404 && await wrongApp.text() === "Preview route unavailable.", "The preview proxy did not enforce its app scope.");
    console.log(`FIXLIST_V9_PREVIEW_READY source=${source} url=${origin} public_settings_http=${settings.status}`);
    if (!values.check) {
      await new Promise((resolve) => {
        process.once("SIGINT", resolve);
        process.once("SIGTERM", resolve);
      });
    }
  } finally {
    if (server) {
      server.httpServer.closeAllConnections?.();
      await new Promise((resolve) => server.httpServer.close(resolve));
    }
    process.chdir(previousDirectory);
    await rm(directory, { recursive: true, force: true });
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  main().catch((error) => {
    console.error(`FixList preview failed: ${error.message}`);
    process.exitCode = 1;
  });
}
