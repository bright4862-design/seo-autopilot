/// <reference types="vite/client" />
// Query param the editor adds to the preview URL when it can swap in a fresh
// iframe on a full reload (mirrors builder_bridge_inject.py in base44-dev/apper).
export const PREVIEW_FE_VERSION_PARAM = "previewFE_version";
export function attachHmrSocketRelay(hot, win = window) {
    win.__base44_bundled_dev__ = true;
    if (win.self === win.top)
        return;
    const previewFEVersion = Number(new URLSearchParams(win.location.search).get(PREVIEW_FE_VERSION_PARAM)) || 0;
    hot.on("vite:ws:connect", () => {
        win.parent?.postMessage({ type: "SANDBOX_WS_CONNECT" }, "*");
    });
    hot.on("vite:ws:disconnect", () => {
        win.parent?.postMessage({ type: "SANDBOX_WS_DISCONNECT" }, "*");
    });
    // Vite's bundled client awaits `vite:beforeFullReload` listeners before it
    // reloads (verified against vite 8.2 bundledDevClient), so a never-settling
    // promise holds the reload and lets the editor swap in a fresh iframe instead.
    hot.on("vite:beforeFullReload", () => {
        win.parent?.postMessage({ type: "sandbox:beforeFullReload" }, "*");
        return previewFEVersion > 0 ? new Promise(() => { }) : undefined;
    });
}
// The socket opens asynchronously, after the whole bundle has evaluated, so the
// listeners above are always registered before the first connect event.
if (import.meta.hot)
    attachHmrSocketRelay(import.meta.hot);
//# sourceMappingURL=sandbox-hmr-socket-relay.js.map