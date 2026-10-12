import path from "node:path";
import type { Plugin, UserConfig } from "vite";
import { loadEnv, version as viteVersion } from "vite";
import { errorOverlayPlugin } from "./error-overlay-plugin.js";
import { visualEditPlugin } from "./visual-edit-plugin.js";
import { filterPackagesInProject } from "./utils.js";
import { htmlInjectionsPlugin } from "./html-injections-plugin.js";
import { buildStatusPlugin } from "./build-status-plugin.js";
import { base44RuntimePlugin } from "./base44-runtime-plugin.js";
import { routeRequestLogPlugin } from "./route-request-log/vite-plugin.js";
export type { DocumentScript } from "./consts.js";

const isRunningInSandbox = !!process.env.MODAL_SANDBOX_ID;

// Vite 8 pre-bundles deps with Rolldown instead of esbuild and deprecates
// `optimizeDeps.esbuildOptions`. Both spellings mean the same thing here:
// treat .js files as JSX, since app code routinely puts JSX in .js.
const isVite8OrLater = Number(viteVersion.split(".")[0]) >= 8;
const jsxInJsFiles = isVite8OrLater
  ? { rolldownOptions: { moduleTypes: { ".js": "jsx" } } }
  : { esbuildOptions: { loader: { ".js": "jsx" } } };

// Every entry Vite must pre-bundle before the browser loads the app. Deep
// entries are listed explicitly: to the optimizer `react/jsx-dev-runtime` and
// `react-dom/client` are separate entries, NOT covered by `react`/`react-dom`.
// Leaving one out means Vite discovers it mid-load, re-runs the optimizer and
// mints a new browserHash — so the same page ends up holding `react.js?v=A`
// and `react.js?v=B`, two React instances, and dies on its first hook with
// "Cannot read properties of null (reading 'useState')".
export const PREBUNDLED_SANDBOX_DEPS = [
  "react",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "react-dom",
  "react-dom/client",
  "react-router-dom",
  "framer-motion",
  "lodash",
  "moment",
  "react-quill",
];

const ENV_UNSET_GUIDANCE = [
  "[base44] No Base44 backend configured — VITE_BASE44_APP_BASE_URL is not set, so /api requests have nowhere to go.",
  "[base44] Run the app through the Base44 CLI instead:",
  "[base44]   base44 dev           app + local backend (throwaway local data)",
  "[base44]   base44 dev --remote  app + your app's real backend (production data)",
].join("\n");

const BUILD_WITHOUT_APP_ID_WARNING = [
  "[base44] Warning: VITE_BASE44_APP_ID is not set — this build",
  "[base44] will not know its app id and its API calls will fail.",
  "[base44] Build with:  base44 build   (or base44 deploy --build)",
].join("\n");

export default function vitePlugin(
  opts: {
    legacySDKImports?: boolean;
    hmrNotifier?: boolean;
    navigationNotifier?: boolean;
    visualEditAgent?: boolean;
    analyticsTracker?: boolean;
  } = {}
) {
  const {
    legacySDKImports = false,
    hmrNotifier = false,
    navigationNotifier = false,
    visualEditAgent = false,
    analyticsTracker = false,
  } = opts;

  return [
    {
      name: "base44",
      config: (config, { command }) => {
        const { mode, root = process.cwd() } = config;
        const env = loadEnv(mode ?? "development", root, "");

        if (!isRunningInSandbox && command === "build" && !env.VITE_BASE44_APP_ID) {
          console.log(BUILD_WITHOUT_APP_ID_WARNING);
        }

        return {
          resolve: {
            alias: {
              "@/": "/src/",
            },
          },
          ...(legacySDKImports
            ? {
                define: {
                  "process.env.VITE_BASE44_APP_ID": JSON.stringify(
                    env.VITE_BASE44_APP_ID
                  ),
                  "process.env.VITE_BASE44_BACKEND_URL": JSON.stringify(
                    env.VITE_BASE44_BACKEND_URL
                  ),
                },
              }
            : {}),
          ...(isRunningInSandbox
            ? ({
                logLevel: "error",
                server: {
                  cors: true,
                  host: "0.0.0.0", // Bind to all interfaces for container access
                  port: 5173,
                  strictPort: true,
                  // Allow all hosts - essential for Modal tunnel URLs
                  allowedHosts: true,
                  fs: {
                    strict: true,
                    // Vite replaces its default deny list when one is provided, so preserve those defaults here.
                    deny: [
                      ".env",
                      ".env.*",
                      "*.{crt,pem}",
                      "**/.git/**",
                      // base44/ contains backend code and the Base44 manifest — never serve it from the dev server.
                      // Root-anchored on purpose: some apps have a stray src/base44/ that IS frontend code.
                      path.resolve(root, "base44").replace(/\\/g, "/") + "/**",
                    ],
                  },
                  // Route the HMR WebSocket through the preview proxy instead of
                  // the sandbox origin. When BASE44_HMR_HOST is unset (e.g. before
                  // the proxy is deployed), fall back to Vite's default behavior
                  // and connect to window.location.host.
                  ...(process.env.BASE44_HMR_HOST
                    ? { hmr: { host: process.env.BASE44_HMR_HOST } }
                    : {}),
                  watch: {
                    // Enable polling for better file change detection in containers
                    usePolling: true,
                    interval: 100, // Check every 100ms for responsive HMR
                    // Wait for file writes to complete before triggering HMR
                    awaitWriteFinish: {
                      stabilityThreshold: 150,
                      pollInterval: 50,
                    },
                  },
                },
                build: {
                  rollupOptions: {
                    onwarn(warning, warn) {
                      // Treat import errors as fatal errors
                      if (
                        warning.code === "UNRESOLVED_IMPORT" ||
                        warning.code === "MISSING_EXPORT"
                      ) {
                        throw new Error(`Build failed: ${warning.message}`);
                      }
                      // Use default for other warnings
                      warn(warning);
                    },
                  },
                },
              } as Partial<UserConfig>)
            : (() => {
                if (env.VITE_BASE44_APP_BASE_URL) {
                  console.log(
                    `[base44] Proxy enabled: /api -> ${env.VITE_BASE44_APP_BASE_URL}`
                  );
                  return {
                    server: {
                      proxy: {
                        "/api": {
                          target: env.VITE_BASE44_APP_BASE_URL,
                          changeOrigin: true,
                        },
                      },
                    },
                  };
                }
                console.log(
                  command === "serve"
                    ? ENV_UNSET_GUIDANCE
                    : "[base44] Proxy not enabled (VITE_BASE44_APP_BASE_URL not set)"
                );
                return {};
              })()),
          optimizeDeps: {
            ...(isRunningInSandbox
              ? {
                  include: filterPackagesInProject(
                    PREBUNDLED_SANDBOX_DEPS,
                    root
                  ),
                }
              : {}),
            ...jsxInJsFiles,
          },
        };
      },
      async resolveId(source, importer, options) {
        // only resolve imports in the legacy SDK if they are not in an HTML file
        // because we might have pages that include /integrations, /functions, etc.
        if (legacySDKImports && !importer?.endsWith(".html")) {
          const existingResolution = await this.resolve(
            source,
            importer,
            options
          );

          if (existingResolution) {
            return existingResolution;
          }

          // in legacy apps, the AI sometimes imports components from the Layout with `../`
          // which breaks when monving to the vite template, so this solved it by
          // resolving the path to the components folder
          if (
            importer?.endsWith("/src/Layout.jsx") &&
            source.startsWith("../components")
          ) {
            return this.resolve(
              source.replace(/^..\/components/, "@/components"),
              importer,
              options
            );
          }

          // Handle imports of Layout.js or Layout.jsx from pages directory
          if (
            importer?.includes("/pages") &&
            (source.toLowerCase().endsWith("layout.jsx") ||
              source.toLowerCase().endsWith("layout.js"))
          ) {
            return this.resolve("@/Layout.jsx", importer, options);
          }

          if (source.includes("/entities")) {
            return this.resolve(
              "@base44/vite-plugin/compat/entities.cjs",
              importer,
              options
            );
          }

          if (source.includes("/functions")) {
            return this.resolve(
              "@base44/vite-plugin/compat/functions.cjs",
              importer,
              options
            );
          }

          if (source.includes("/integrations")) {
            return this.resolve(
              "@base44/vite-plugin/compat/integrations.cjs",
              importer,
              options
            );
          }

          if (source.includes("/agents")) {
            return this.resolve(
              "@base44/vite-plugin/compat/agents.cjs",
              importer,
              options
            );
          }
        }

        return null;
      },
    } as Plugin,
    ...(isRunningInSandbox
      ? [
          {
            name: "iframe-hmr",
            configureServer(server) {
              server.middlewares.use((req, res, next) => {
                // Allow iframe embedding
                res.setHeader("X-Frame-Options", "ALLOWALL");
                res.setHeader("Content-Security-Policy", "frame-ancestors *;");
                next();
              });
            },
          } as Plugin,
          errorOverlayPlugin(),
          visualEditPlugin(),
        ]
      : []),
    // HTML injections - handles both dev (sandbox) and production injections
    ...htmlInjectionsPlugin({
      hmrNotifier,
      navigationNotifier,
      visualEditAgent,
      analyticsTracker,
      tailwindCdn: isRunningInSandbox,
    }),
    // Opt-in, loopback-gated dev-server build-status endpoint. Gated here on
    // the BASE44_BUILD_STATUS_ENABLED env var so the generated app's
    // vite.config.js doesn't need to change and the sub-plugin isn't even
    // added to the pipeline when disabled. The endpoint itself is dev-only.
    ...(process.env.BASE44_BUILD_STATUS_ENABLED === "1"
      ? [buildStatusPlugin()]
      : []),
    // Serves `base44:runtime` to full-stack server routes. Unconditional: it
    // only claims the `base44:` specifiers, so an app with no server dir never
    // notices it. Ordering comes from its own `enforce: "pre"`, not from its
    // position here — several tests index this array from the front.
    base44RuntimePlugin(),
    // Dev-only: tags a full-stack route's console output with the request's
    // X-B44-Request-Id. Registered as a Nitro module (the `nitro` property)
    // because Nitro runs dev routes in a worker whose console the Vite process
    // never sees. Inert for apps without Nitro and for requests without the id.
    routeRequestLogPlugin(),
  ];
}
