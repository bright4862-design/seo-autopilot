# @base44/vite-plugin

Vite plugin for Base44 applications running in sandboxed iframes. Provides error tracking, HMR notifications, visual editing, navigation tracking, and legacy SDK compatibility.

## Installation

```bash
npm install @base44/vite-plugin
```

## Usage

```ts
// vite.config.ts
import base44 from "@base44/vite-plugin";

export default {
  plugins: [
    base44({
      legacySDKImports: false,
      hmrNotifier: true,
      navigationNotifier: true,
      visualEditAgent: true,
    }),
  ],
};
```

### Options

| Option               | Type      | Default | Description                                         |
| -------------------- | --------- | ------- | --------------------------------------------------- |
| `legacySDKImports`   | `boolean` | `false` | Enable legacy SDK import resolution via compat layer |
| `hmrNotifier`        | `boolean` | `false` | Notify parent window of HMR update lifecycle         |
| `navigationNotifier` | `boolean` | `false` | Track URL changes and notify parent window           |
| `visualEditAgent`    | `boolean` | `false` | Enable interactive visual element editing            |

## Architecture

### Plugin Composition

The plugin registers these sub-plugins when running in a sandbox (`MODAL_SANDBOX_ID` is set):

1. **base44** — Core configuration: path aliases (`@/` → `/src/`), environment variables, dependency optimization, and legacy SDK import resolution.
2. **iframe-hmr** — Sets CORS and `frame-ancestors` headers to allow iframe embedding.
3. **error-overlay** — Replaces Vite's default error overlay with a custom one that reports errors to the parent window. Under Vite 8's bundled dev mode (`experimental.bundledDev`) Vite's client is never served, so the plugin turns the overlay off instead and `sandbox-build-error-notifier` forwards build errors to the parent in the same `app_error` shape.
4. **html-injections** — Injects sandbox-side scripts into the HTML while serving. Under bundled dev mode its sibling **html-injections-bundled** injects them instead, before the HTML is bundled.
5. **html-injections-production** — Injects the analytics tracker into production builds.

Dev and production are told apart by the Vite command (`serve` vs `build`), not by the presence of a dev server in the HTML transform context — bundled dev runs the HTML through the build-shaped transform, where no server is passed.

Outside a sandbox, only the core plugin runs (with optional API proxy support via `VITE_BASE44_APP_BASE_URL`).

### Build-status endpoint

An opt-in, dev-only (`apply: "serve"`) endpoint that reports the last build /
compile / HMR error observed by the dev server. It exists solely to let the
preview backend poll for post-load errors — it is **never** part of a
production build.

Enable it by setting the environment variable at dev-server start:

```bash
BASE44_BUILD_STATUS_ENABLED=1
```

The env var is checked when the plugin assembles its plugin list (config load),
so the generated app's `vite.config.js` does not need to change. When it is
unset, the build-status sub-plugin is not added to the pipeline at all — its
`configureServer` hook is never reached.

When enabled, the plugin serves:

```
GET /__build_status
```

- **Loopback-only.** Requests from any non-loopback `remoteAddress`
  (`127.0.0.1`, `::1`, `::ffff:127.0.0.1`) fall through as if the route did
  not exist. Non-`GET` methods fall through too.
- **Always `200`.** Health lives in the body, not the status code — a `500`
  would trip the preview proxy's own error path. The body is:

  ```json
  { "ok": true, "error": null }
  ```

  or, when an error is outstanding:

  ```json
  { "ok": false, "error": { "message": "…", "frame": "…", "loc": { "…": 0 } } }
  ```

- **Scrubbed.** Even though the endpoint is loopback-only (the backend relays a
  trimmed form onward), the error is size-capped and absolute filesystem paths
  are stripped down to basenames.
- **Fail-open.** All setup and request handling is wrapped in `try/catch` so a
  bug in this plugin can never break the dev server.

How it works: `configureServer` wraps the HMR send channel
(`server.hot ?? server.ws`). An `error` payload records the last error; a
successful `update` or `full-reload` clears it.

Under bundled dev mode failures never reach that channel — Vite reports them
through the client environment's logger and per-client sends — so the plugin
additionally records the error the logger is given, plus a failed `buildEnd`,
and clears it when a rebuild reaches `generateBundle`. Boot-time build
failures are therefore reported in this mode.

**Cold-start caveat & scope.** Errors thrown *before any client has connected*
are not sent over the HMR channel, so a boot-time transform failure may briefly
read `ok: true`. That window is already covered server-side by the existing
`dev_server_error_classifier` (install / start failures surface as `409`). This
endpoint's job is **post-load HMR / compile errors**, not cold-start failures.

### Route request logs (full-stack apps)

Dev-only. While a Nitro server route serves a request that carries
`X-B44-Request-Id`, every `console.*` line it prints goes to stdout prefixed
`[b44-req <id> <level>] `, followed by one summary line per request
(`GET /api/orders handled in 12ms`, or `threw <Error> after 12ms`). Requests
without the header are untouched. It ships as a Nitro module (the `nitro`
property on `base44-route-request-log`) because Nitro runs dev routes in a
separate runtime whose `console` a Vite middleware never sees.

### Sandbox Injections

In **dev mode**, individual `<script type="module" src="...">` tags are injected for each feature, loaded directly from `node_modules`. Under bundled dev mode the tags are injected with `order: "pre"` instead, so they become part of the HTML entry and are folded into the bundle (with `import.meta.hot` available). Their `src` is then a `virtual:base44-vite-plugin/...` id that the plugin resolves onto its own `dist/` directory, so the bundle does not depend on where npm placed the package.

- **Error handlers** (`unhandled-errors-handlers.js`) — Global `error` and `unhandledrejection` listeners that report to the parent via `postMessage`.
- **Mount observer** (`sandbox-mount-observer.js`) — `MutationObserver` that detects when instrumented elements (`data-source-location`) are rendered.
- **HMR notifier** (`sandbox-hmr-notifier.js`) — Forwards Vite's `beforeUpdate`/`afterUpdate` events to the parent.
- **Navigation notifier** (`navigation-notifier.js`) — Intercepts `pushState`, `replaceState`, and `popstate` to track URL changes.
- **Build error notifier** (`sandbox-build-error-notifier.js`, bundled dev only) — Forwards `vite:error` payloads to the parent as `app_error`, replacing the custom error overlay that cannot be installed in that mode.
- **HMR socket relay** (`sandbox-hmr-socket-relay.js`, bundled dev only) — Sets `window.__base44_bundled_dev__` and posts `SANDBOX_WS_CONNECT` / `SANDBOX_WS_DISCONNECT` / `sandbox:beforeFullReload`, the events the preview proxy's bridge otherwise collects by importing `/@vite/client`.

These are self-executing scripts — they run as soon as the browser loads them, with no setup call required.

The **visual edit agent** is the exception. It's a larger module (~560 lines) that is bundled separately via `tsup` into `dist/statics/index.mjs` and loaded via a dynamic `import()`. This allows local dev iteration: add `?sandbox-bridge=local` to load it from a local HTTPS dev server instead of `node_modules`. Bundled dev mode mounts no static middleware, so in that mode the plugin serves its own `dist/` tree (scripts and source maps only) for this import.

In **production**, an inline analytics tracker script is injected instead.

### Server-rendered documents (`base44:document`)

`transformIndexHtml` never runs for an app whose HTML document is rendered by the framework (TanStack Start and other SSR setups have no `index.html`). Those apps import the same scripts as a module and render them in `<body>`, **before the framework's own scripts**:

```jsx
import { Base44Scripts } from "base44:document";

function RootDocument({ children }) {
  return (
    <html>
      <head><HeadContent /></head>
      <body data-react-root="true">
        {children}
        <Base44Scripts />
        <Scripts />
      </body>
    </html>
  );
}
```

The module is virtual: the plugin decides its contents from the same options, command and env as the `index.html` injections, so dev gets the sandbox scripts (plus `ssr-mount-signal.js`, which reports the mount once the document is parsed because a hydrated page never triggers the mutation observer) and production gets the analytics tracker. Module scripts run in document order, so rendering the component before `<Scripts />` keeps the error handlers registered before hydration starts, as they are in `index.html`. Never render it in `<head>`: the preview proxy prepends its own scripts there, and React 19 fails hydration of a head it did not render. `base44DocumentScripts()` returns the raw `{ src, classic? }` / `{ children }` list, typed as `DocumentScript` from `@base44/vite-plugin`, for a document that renders the tags itself. Render every entry as `type="module"` except those with `classic: true`: the Tailwind CDN that the sandbox dev server loads for visual edit is a classic script.

### Local Development (Visual Edit Agent)

To iterate on the visual edit agent locally without publishing:

1. Generate local HTTPS certificates:
   ```bash
   mkcert localhost
   ```

2. Start the dev server (with optional watch mode):
   ```bash
   npm run dev       # serve dist/statics/ on https://localhost:3201
   npm run dev -- -w # same, with auto-rebuild on changes
   ```

3. Add `?sandbox-bridge=local` to your app's URL to load the agent from `localhost:3201` instead of `node_modules`.

### Legacy SDK Compatibility

When `legacySDKImports` is enabled, imports of `/entities`, `/functions`, `/integrations`, and `/agents` are resolved to compatibility modules in `compat/`. These use `Proxy` objects to route calls to the Base44 SDK client.

## Building

```bash
npm run build          # TypeScript compilation (plugin)
npm run build:bridge   # tsup bundle (bridge ES module for browsers)
```

## License

MIT
