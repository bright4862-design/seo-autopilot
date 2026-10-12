import { createReadStream, existsSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadEnv } from "vite";
import { isBundledDev } from "./bundled-dev.js";
import { TAILWIND_CDN_SRC } from "./consts.js";
const ANALYTICS_TRACKER_SCRIPT = `
if (window.self === window.top) {
  let lastPath = "";
  function getPageNameFromPath(path) {
    const segments = path.split("/").filter(Boolean);
    return segments[0] || null;
  }
  function trackPageView() {
    const path = window.location.pathname;
    if (path === lastPath) return;
    lastPath = path;
    const pageName = getPageNameFromPath(path) || "home";
    const appId = import.meta.env.VITE_BASE44_APP_ID;
    if (!appId) return;
    fetch(\`/api/app-logs/\${appId}/log-user-in-app/\${pageName}\`, {
      method: "POST",
    }).catch(() => {});
  }
  const originalPushState = history.pushState.bind(history);
  history.pushState = function (...args) {
    originalPushState(...args);
    trackPageView();
  };
  const originalReplaceState = history.replaceState.bind(history);
  history.replaceState = function (...args) {
    originalReplaceState(...args);
    trackPageView();
  };
  window.addEventListener("popstate", trackPageView);
  trackPageView();
}
`;
const DIST_URL_PREFIX = "/node_modules/@base44/vite-plugin/dist";
/**
 * Bundled dev resolves module-script `src` through the bundler instead of the
 * dev server, so a node_modules URL would break on any non-flat install. These
 * ids are mapped onto the plugin's own dist tree by `resolveId` below.
 */
export const BUNDLED_INJECTION_PREFIX = "virtual:base44-vite-plugin/";
const INJECTIONS = {
    unhandledErrors: {
        file: "injections/unhandled-errors-handlers.js",
        injectTo: "head",
        mode: "dev",
    },
    sandboxMount: {
        file: "injections/sandbox-mount-observer.js",
        injectTo: "body",
        mode: "dev",
    },
    hmrNotifier: {
        file: "injections/sandbox-hmr-notifier.js",
        injectTo: "head",
        mode: "dev",
    },
    navigationNotifier: {
        file: "injections/navigation-notifier.js",
        injectTo: "head",
        mode: "dev",
    },
    buildErrorNotifier: {
        file: "injections/sandbox-build-error-notifier.js",
        injectTo: "head",
        mode: "dev",
        bundledOnly: true,
    },
    hmrSocketRelay: {
        file: "injections/sandbox-hmr-socket-relay.js",
        injectTo: "head",
        mode: "dev",
        bundledOnly: true,
    },
    analyticsTracker: {
        injectTo: "head",
        mode: "production",
        inlineContent: ANALYTICS_TRACKER_SCRIPT,
    },
};
const CONTENT_TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".map": "application/json",
};
/** This file lives in dist/ once built, so its directory is the served root. */
export const PLUGIN_DIST_DIR = path.dirname(fileURLToPath(import.meta.url));
const VISUAL_EDIT_AGENT_FILE = "statics/index.mjs";
const SSR_MOUNT_SIGNAL_FILE = "injections/ssr-mount-signal.js";
/**
 * `base44:document` — the same scripts `transformIndexHtml` injects, for apps
 * whose HTML document is rendered by a framework (TanStack Start, and any other
 * SSR setup) and never passes through `index.html`. The root document renders
 * `<Base44Scripts />` at the end of `<body>`; the plugin decides what that is
 * from its own options, the command and the env, exactly as for `index.html`.
 */
export const DOCUMENT_SPECIFIER = "base44:document";
const DOCUMENT_RESOLVED = "\0base44:document";
/**
 * The document renders inline content through `dangerouslySetInnerHTML`, which
 * React does not escape; an env value carrying `</script>` would otherwise
 * close the tag early. Only string literals can carry it, where `<\/` is `</`.
 */
export function escapeInlineScript(code) {
    return code.replace(/<\/(script)/gi, "<\\/$1");
}
export function documentModule(scripts) {
    return `
import { createElement, Fragment } from "react";

const SCRIPTS = ${JSON.stringify(scripts)};

export function base44DocumentScripts() {
  return SCRIPTS;
}

export function Base44Scripts() {
  return createElement(
    Fragment,
    null,
    ...SCRIPTS.map((script, index) =>
      "src" in script
        ? createElement("script", { key: index, type: script.classic ? undefined : "module", src: script.src })
        : createElement("script", {
            key: index,
            type: "module",
            suppressHydrationWarning: true,
            dangerouslySetInnerHTML: { __html: script.children },
          }),
    ),
  );
}
`;
}
export function resolveBundledInjection(id, distDir = PLUGIN_DIST_DIR) {
    if (!id.startsWith(BUNDLED_INJECTION_PREFIX))
        return undefined;
    return path.join(distDir, id.slice(BUNDLED_INJECTION_PREFIX.length));
}
/**
 * Bundled dev mounts no static/transform middleware, so the visual-edit agent's
 * dynamic `import()` of dist/statics/index.mjs would fall through to the SPA
 * fallback and receive index.html. Serve the plugin's own dist tree instead.
 */
export function serveDistMiddleware(distDir) {
    return (req, res, next) => {
        const url = (req.url ?? "").split("?")[0] ?? "";
        if (!url.startsWith(`${DIST_URL_PREFIX}/`))
            return next();
        if (req.method !== "GET" && req.method !== "HEAD")
            return next();
        let relative;
        try {
            relative = decodeURIComponent(url.slice(DIST_URL_PREFIX.length + 1));
        }
        catch {
            return next();
        }
        const filePath = path.resolve(distDir, relative);
        const type = CONTENT_TYPES[path.extname(filePath)];
        if (!type ||
            !filePath.startsWith(distDir + path.sep) ||
            !existsSync(filePath) ||
            !statSync(filePath).isFile()) {
            return next();
        }
        res.statusCode = 200;
        res.setHeader("Content-Type", type);
        res.setHeader("Cache-Control", "no-store");
        // Headers are already out, so a read failure can only end the response.
        createReadStream(filePath).on("error", () => res.end()).pipe(res);
    };
}
export function htmlInjectionsPlugin({ hmrNotifier, navigationNotifier, visualEditAgent, analyticsTracker, tailwindCdn = false, }) {
    // The two bundled-only scripts stand in for things that are unconditional in
    // the middleware server (the error overlay swap and the preview bridge's
    // `/@vite/client` import), so they do not follow the opt-in toggles.
    const enabledInjections = {
        unhandledErrors: true,
        sandboxMount: true,
        hmrNotifier,
        navigationNotifier,
        buildErrorNotifier: true,
        hmrSocketRelay: true,
        analyticsTracker,
    };
    // Written by `dev.configResolved`; the three plugins below are always
    // registered together and read this shared state.
    let resolvedEnv = {};
    let isServe = false;
    let bundled = false;
    let configMode = "";
    const tagsFor = (mode, useBundled = bundled) => Object.entries(INJECTIONS)
        .filter(([key, injection]) => enabledInjections[key] &&
        injection.mode === mode &&
        (!injection.bundledOnly || useBundled))
        .map(([, injection]) => {
        if (injection.inlineContent) {
            // Vite doesn't replace import.meta.env inside injected inline scripts.
            const content = injection.inlineContent.replace(/import\.meta\.env\.(\w+)/g, (_, envKey) => JSON.stringify(resolvedEnv[envKey] ?? ""));
            return {
                tag: "script",
                attrs: { type: "module" },
                children: content,
                injectTo: injection.injectTo,
            };
        }
        const src = useBundled
            ? `${BUNDLED_INJECTION_PREFIX}${injection.file}`
            : `${DIST_URL_PREFIX}/${injection.file}`;
        return {
            tag: "script",
            attrs: { src, type: "module" },
            injectTo: injection.injectTo,
        };
    });
    const visualEditAgentTag = () => ({
        tag: "script",
        attrs: { type: "module" },
        children: [
            `if (window.self !== window.top) {`,
            `  const mode = new URLSearchParams(location.search).get("sandbox-bridge");`,
            `  const url = mode === "local"`,
            `    ? "https://localhost:3201/index.mjs"`,
            `    : "${DIST_URL_PREFIX}/statics/index.mjs";`,
            `  import(url)`,
            `    .then(mod => {`,
            `      if (typeof mod.setupVisualEditAgent === "function") mod.setupVisualEditAgent();`,
            `    })`,
            `    .catch(e => console.error("[visual-edit-agent] Failed to load:", e));`,
            `}`,
        ].join("\n"),
        injectTo: "body",
    });
    const devTags = (useBundled = bundled) => {
        const tags = tagsFor("dev", useBundled);
        if (visualEditAgent)
            tags.push(visualEditAgentTag());
        return tags;
    };
    const dev = {
        name: "html-injections",
        configResolved(config) {
            resolvedEnv = loadEnv(config.mode, config.root, "");
            // `ctx.server` is absent in bundled dev, where the HTML runs through the
            // build-shaped transform; the command is the only reliable dev signal.
            isServe = config.command === "serve";
            bundled = isBundledDev(config);
            configMode = config.mode;
        },
        configureServer(server) {
            if (!bundled)
                return;
            if (visualEditAgent && !existsSync(path.join(PLUGIN_DIST_DIR, VISUAL_EDIT_AGENT_FILE))) {
                console.warn(`[html-injections] ${VISUAL_EDIT_AGENT_FILE} not found under ${PLUGIN_DIST_DIR}; ` +
                    "the visual edit agent will not load in bundled dev mode.");
            }
            server.middlewares.use(serveDistMiddleware(PLUGIN_DIST_DIR));
        },
        transformIndexHtml: {
            handler() {
                return isServe && !bundled ? devTags() : [];
            },
        },
    };
    // Pre-order tags are part of the HTML entry, so bundled dev folds them into
    // the bundle (with `import.meta.hot`) instead of leaving raw node_modules URLs
    // that nothing serves. Kept separate so the middleware-based dev server keeps
    // injecting after its own HTML processing, exactly as before.
    const devBundled = {
        name: "html-injections-bundled",
        resolveId(id) {
            return resolveBundledInjection(id);
        },
        transformIndexHtml: {
            order: "pre",
            handler() {
                return isServe && bundled ? devTags() : [];
            },
        },
    };
    const production = {
        name: "html-injections-production",
        transformIndexHtml: {
            handler() {
                return isServe ? [] : tagsFor("production");
            },
        },
    };
    // The framework's dev server is middleware-based, so the document never takes
    // the bundled form: node_modules URLs, and none of the `import.meta.hot`-gated
    // bundled-only scripts, which would be silent no-ops served raw. The SSR mount
    // signal stands in for the mutation-driven observer, which never fires on a
    // hydrated page.
    const documentScripts = () => {
        const tags = isServe ? devTags(false) : tagsFor("production", false);
        if (isServe) {
            tags.push({
                tag: "script",
                attrs: { src: `${DIST_URL_PREFIX}/${SSR_MOUNT_SIGNAL_FILE}`, type: "module" },
                injectTo: "body",
            });
        }
        // index.html runs `head` injections before the app entry and `body` ones
        // after it; module scripts run in document order, so head entries go first.
        const ordered = [
            ...tags.filter((tag) => tag.injectTo === "head"),
            ...tags.filter((tag) => tag.injectTo !== "head"),
        ];
        const scripts = ordered.map((tag) => {
            if (typeof tag.children === "string")
                return { children: escapeInlineScript(tag.children) };
            const src = tag.attrs?.src;
            if (typeof src !== "string") {
                throw new Error(`[base44-document] injection has neither src nor inline content: ${JSON.stringify(tag)}`);
            }
            return { src };
        });
        const wantsTailwindCdn = tailwindCdn && isServe && configMode === "development";
        // A classic script, as `visualEditPlugin` injects it into index.html.
        if (wantsTailwindCdn)
            scripts.unshift({ src: TAILWIND_CDN_SRC, classic: true });
        return scripts;
    };
    const document = {
        name: "base44-document",
        // Ahead of Vite's own resolution so the bare `base44:` specifier is never
        // mistaken for a URL protocol.
        enforce: "pre",
        resolveId(id) {
            return id === DOCUMENT_SPECIFIER ? DOCUMENT_RESOLVED : null;
        },
        load(id) {
            return id === DOCUMENT_RESOLVED ? documentModule(documentScripts()) : null;
        },
    };
    return [dev, devBundled, production, document];
}
//# sourceMappingURL=html-injections-plugin.js.map