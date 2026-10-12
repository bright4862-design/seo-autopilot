import { errorOverlayCode } from "./ErrorOverlay.js";
import { isBundledDev } from "./bundled-dev.js";
// Vite <=6 emits `class ErrorOverlay extends HTMLElement`, Vite >=7
// `var ErrorOverlay = class extends HTMLElement`. This is Vite's bundled output,
// not an API, so match the shape rather than the version; `\s` so a reformatted
// or minified emit still matches.
const VITE_OVERLAY_DECL = /class ErrorOverlay(?=\s+extends)|\b(var|let|const)\s+ErrorOverlay(?=\s*=\s*class)/;
export function errorOverlayPlugin() {
    return {
        name: "error-overlay",
        apply: (config) => config.mode === "development",
        // Bundled dev never serves client.mjs, so the swap below cannot run. Turn
        // Vite's overlay off and let sandbox-build-error-notifier forward the error.
        config: (config) => isBundledDev(config) ? { server: { hmr: { overlay: false } } } : null,
        // `config` sees only the user config; a later plugin or CLI flag can still
        // turn bundled dev on, leaving Vite's overlay up next to the notifier.
        configResolved(config) {
            const hmr = config.server.hmr;
            if (isBundledDev(config) && hmr !== false && (hmr === true || hmr?.overlay !== false)) {
                console.warn("[error-overlay] Bundled dev mode is on but server.hmr.overlay is not false — " +
                    "Vite's own overlay will show alongside the app_error sent to the parent.");
            }
        },
        transform(code, id, opts = {}) {
            if (opts?.ssr)
                return;
            if (!id.includes("vite/dist/client/client.mjs"))
                return;
            const patched = code.replace(VITE_OVERLAY_DECL, (_match, declaration) => errorOverlayCode +
                "\n" +
                (declaration ? `${declaration} OldErrorOverlay` : "class OldErrorOverlay"));
            // replace() returns the input unchanged on a miss, so a new shape would
            // silently restore Vite's red overlay — as it did for every Vite >=7.
            if (patched === code) {
                console.warn("[error-overlay] Could not find Vite's ErrorOverlay declaration in " +
                    "client.mjs — Vite's own overlay stays active and app_error will not " +
                    "be sent. @base44/vite-plugin needs updating for this Vite version.");
                // Returning the identical string would still cost client.mjs its sourcemap.
                return;
            }
            return patched;
        },
    };
}
//# sourceMappingURL=error-overlay-plugin.js.map