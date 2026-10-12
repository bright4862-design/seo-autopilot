/// <reference types="vite/client" />
export function reportBuildError(payload, win = window) {
    const err = payload?.err ?? {};
    const message = typeof err.message === "string" ? err.message : "Build error";
    const stack = typeof err.stack === "string" ? err.stack : undefined;
    const loc = err.loc;
    const file = loc?.file ?? (typeof err.id === "string" ? err.id : undefined);
    const where = file && loc?.line != null ? `${file}:${loc.line}:${loc.column ?? 0}` : file;
    const details = [where, typeof err.frame === "string" ? err.frame : undefined, stack]
        .filter(Boolean)
        .join("\n");
    win.parent?.postMessage({
        type: "app_error",
        error: {
            title: message,
            details: details || undefined,
            componentName: undefined,
            originalError: { message, stack, plugin: err.plugin, id: err.id, loc },
            stack,
        },
    }, "*");
}
if (import.meta.hot) {
    import.meta.hot.on("vite:error", (payload) => reportBuildError(payload));
}
//# sourceMappingURL=sandbox-build-error-notifier.js.map