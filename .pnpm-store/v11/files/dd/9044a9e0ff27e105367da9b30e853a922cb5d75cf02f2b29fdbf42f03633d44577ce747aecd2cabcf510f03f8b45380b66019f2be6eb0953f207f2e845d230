import type { ServerResponse } from "node:http";
import type { Connect, Plugin } from "vite";
import { type DocumentScript } from "./consts.js";
/**
 * Bundled dev resolves module-script `src` through the bundler instead of the
 * dev server, so a node_modules URL would break on any non-flat install. These
 * ids are mapped onto the plugin's own dist tree by `resolveId` below.
 */
export declare const BUNDLED_INJECTION_PREFIX = "virtual:base44-vite-plugin/";
/** This file lives in dist/ once built, so its directory is the served root. */
export declare const PLUGIN_DIST_DIR: string;
/**
 * `base44:document` — the same scripts `transformIndexHtml` injects, for apps
 * whose HTML document is rendered by a framework (TanStack Start, and any other
 * SSR setup) and never passes through `index.html`. The root document renders
 * `<Base44Scripts />` at the end of `<body>`; the plugin decides what that is
 * from its own options, the command and the env, exactly as for `index.html`.
 */
export declare const DOCUMENT_SPECIFIER = "base44:document";
/**
 * The document renders inline content through `dangerouslySetInnerHTML`, which
 * React does not escape; an env value carrying `</script>` would otherwise
 * close the tag early. Only string literals can carry it, where `<\/` is `</`.
 */
export declare function escapeInlineScript(code: string): string;
export declare function documentModule(scripts: DocumentScript[]): string;
export declare function resolveBundledInjection(id: string, distDir?: string): string | undefined;
/**
 * Bundled dev mounts no static/transform middleware, so the visual-edit agent's
 * dynamic `import()` of dist/statics/index.mjs would fall through to the SPA
 * fallback and receive index.html. Serve the plugin's own dist tree instead.
 */
export declare function serveDistMiddleware(distDir: string): (req: Connect.IncomingMessage, res: ServerResponse, next: Connect.NextFunction) => void;
export declare function htmlInjectionsPlugin({ hmrNotifier, navigationNotifier, visualEditAgent, analyticsTracker, tailwindCdn, }: {
    hmrNotifier: boolean;
    navigationNotifier: boolean;
    visualEditAgent: boolean;
    analyticsTracker: boolean;
    /** Mirrors the sandbox-only `visualEditPlugin`, which adds the CDN to `index.html`. */
    tailwindCdn?: boolean;
}): Plugin[];
//# sourceMappingURL=html-injections-plugin.d.ts.map