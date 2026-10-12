/**
 * Serves `base44:runtime` to full-stack server routes, so a route reads secrets
 * and schedules background work with the SAME import a backend function uses:
 *
 *   import { secrets, waitUntil } from "base44:runtime";
 *
 * WHY A BUILD-TIME VIRTUAL MODULE. The Workers runtime cannot resolve a custom
 * scheme: the legacy module registry special-cases only `node:` / `cloudflare:` /
 * `workerd:`, and the new registry (`new_module_registry`) explicitly rejects a
 * bundle module whose name carries a non-`file:` scheme. Import maps are not
 * supported either. So `base44:runtime` has to be resolved before upload — there
 * is no runtime path to it, and no amount of wrapping the deployed entry creates
 * one.
 *
 * WHY NO ASYNCLOCALSTORAGE / NO WRAPPER ENTRY. Cloudflare now ships both
 * primitives ambiently from `cloudflare:workers` (`env` since 2025-03-17,
 * `waitUntil` since 2025-08-08), backed by workerd's own AsyncContextFrame and
 * IoContext. The backend-function bundler predates that and threads a context
 * through `globalThis.Base44` because it owns the generated entry; here the
 * framework owns the entry, and borrowing the platform's ambient accessors means
 * we never have to.
 */
const SPECIFIER = "base44:runtime";
// Rollup convention: a resolved virtual id starts with NUL so no other plugin
// (and no filesystem lookup) tries to claim it.
const RESOLVED = "\0base44:runtime";
// Reserved so a route importing it fails with an explanation instead of a bare
// "failed to resolve import". Actors are never imported — they live in the app's
// actors directory, in server routes exactly as in backend functions.
const ACTORS_REASON = "Actors are defined in the app's actors directory, not imported into a route.";
function unsupportedReason(id) {
    if (id === "base44:runtime/actors")
        return ACTORS_REASON;
    return null;
}
/**
 * `cloudflare:workers` stays external — workerd provides it, and Nitro's
 * cloudflare preset already treats `cloudflare:*` that way.
 *
 * There is deliberately no separate dev body. Nitro's `cloudflareDev` preset
 * (aliased for `cloudflare-module`, which is what these apps build with) sets
 * `devServer.runner: "miniflare"`, so dev runs in workerd too and the same
 * import resolves there. A `process.env` fallback would buy nothing and cost a
 * dev/prod behaviour split — the shape that makes background work silently
 * vanish locally while working in production. If someone overrides the runner
 * away from workerd, this fails loudly at resolution rather than quietly
 * serving a different value.
 *
 * `waitUntil` is WRAPPED rather than re-exported: ours returns the promise so it
 * composes (`infra/base44-userapp-bundler/src/runtime/index.ts` in apper),
 * Cloudflare's returns void. A bare re-export would make `const p = waitUntil(x)`
 * work in a backend function and silently yield `undefined` here — one specifier
 * with two behaviours is the exact failure this module exists to prevent.
 */
const RUNTIME_MODULE = `
import { env, waitUntil as cfWaitUntil } from "cloudflare:workers";

export function waitUntil(promise) {
  cfWaitUntil(promise);
  return promise;
}

export const secrets = {
  get(name) {
    const value = env[name];
    return typeof value === "string" ? value : undefined;
  },
};
`;
export function base44RuntimePlugin() {
    return {
        name: "base44-runtime",
        // Ahead of Vite's own resolution so the bare `base44:` specifier is never
        // mistaken for a URL protocol.
        enforce: "pre",
        resolveId(id) {
            const reason = unsupportedReason(id);
            if (reason) {
                this.error(`"${id}" is not available in server routes. ${reason}`);
            }
            if (id !== SPECIFIER)
                return null;
            // `cloudflare:workers` has no browser equivalent, so a client-side import
            // would bundle a module that cannot run. Fail with the reason instead.
            if (this.environment?.name === "client") {
                this.error(`"${SPECIFIER}" is server-only. Move this import into a server route.`);
            }
            return RESOLVED;
        },
        load(id) {
            return id === RESOLVED ? RUNTIME_MODULE : null;
        },
    };
}
//# sourceMappingURL=base44-runtime-plugin.js.map