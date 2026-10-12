/// <reference types="vite/client" />
window.removeEventListener("unhandledrejection", handleUnhandledRejection);
window.removeEventListener("error", handleWindowError);
window.addEventListener("unhandledrejection", handleUnhandledRejection);
window.addEventListener("error", handleWindowError);
let shouldPropagateErrors = true;
let suppressionTimer = null;
let hadSuppressedErrors = false;
let hmrSocketConnected = false;
export function onHmrSocketConnect() {
    hmrSocketConnected = true;
}
if (import.meta.hot) {
    import.meta.hot.on("vite:ws:connect", onHmrSocketConnect);
    import.meta.hot.on("vite:beforeUpdate", () => {
        shouldPropagateErrors = false;
        hadSuppressedErrors = false;
        if (suppressionTimer) {
            clearTimeout(suppressionTimer);
        }
        suppressionTimer = setTimeout(() => {
            shouldPropagateErrors = true;
            suppressionTimer = null;
            hadSuppressedErrors = false;
            // No vite:afterUpdate after timeout — treat the stuck update as an error
            window.parent?.postMessage({ type: "sandbox:hmrErrorsSuppressed" }, "*");
        }, import.meta.env.VITE_HMR_ERROR_SUPPRESSION_DELAY ?? 10000);
    });
    import.meta.hot.on("vite:afterUpdate", () => {
        shouldPropagateErrors = true;
        if (suppressionTimer) {
            clearTimeout(suppressionTimer);
            suppressionTimer = null;
        }
        if (hadSuppressedErrors) {
            window.parent?.postMessage({ type: "sandbox:hmrErrorsSuppressed" }, "*");
            hadSuppressedErrors = false;
        }
    });
    import.meta.hot.on("vite:beforeFullReload", () => {
        shouldPropagateErrors = false;
        hadSuppressedErrors = false;
        if (suppressionTimer) {
            clearTimeout(suppressionTimer);
            suppressionTimer = null;
        }
    });
}
function onAppError({ title, details, componentName, originalError, }) {
    if (originalError?.response?.status === 402) {
        return;
    }
    if (!shouldPropagateErrors) {
        hadSuppressedErrors = true;
        return;
    }
    window.parent?.postMessage({
        type: "app_error",
        error: {
            title: title.toString(),
            details: details?.toString(),
            componentName: componentName?.toString(),
            stack: originalError?.stack?.toString(),
        },
    }, "*");
}
// extract function name from "at X (eval" where X is the function name
function extractFunctionName(stack) {
    if (typeof stack !== "string")
        return undefined;
    return stack.match(/at\s+(\w+)\s+\(eval/)?.[1];
}
// A rejection reason or error can be any value — undefined, a string, a
// null-prototype object. Throwing here masks the real error entirely.
function describeErrorValue(value) {
    try {
        return String(value);
    }
    catch {
        return Object.prototype.toString.call(value);
    }
}
// Vite 8's bundled client (verified through 8.3.0) sends `vite:client-connected`
// at bundle evaluation without a catch. When the HMR socket never opened (sandbox
// asleep or restarting) Vite still marks the transport connected, so that send
// rejects with `ws.send` on undefined. It is the only signal that the socket
// failed to attach, so report it as such instead of as an app error.
export function isHmrSocketAttachError(reason, { bundled = Boolean(window.__base44_bundled_dev__), connected = hmrSocketConnected } = {}) {
    if (connected || !bundled || !(reason instanceof TypeError))
        return false;
    return /\bsend\b/.test(`${reason.message}\n${reason.stack ?? ""}`);
}
export function handleUnhandledRejection(event) {
    const reason = event?.reason;
    if (isHmrSocketAttachError(reason)) {
        window.parent?.postMessage({ type: "SANDBOX_WS_ATTACH_FAILED", error: String(reason) }, "*");
        return;
    }
    const functionName = extractFunctionName(reason?.stack);
    const text = describeErrorValue(reason);
    const msg = functionName ? `Error in ${functionName}: ${text}` : text;
    onAppError({
        title: msg,
        details: text,
        componentName: functionName,
        originalError: reason,
    });
}
export function handleWindowError(event) {
    const error = event?.error;
    let functionName = extractFunctionName(error?.stack);
    if (functionName === "eval") {
        functionName = undefined;
    }
    // window.onerror fires with a null error for cross-origin script failures
    const text = error == null && typeof event?.message === "string"
        ? event.message
        : describeErrorValue(error);
    const msg = functionName ? `in ${functionName}: ${text}` : text;
    onAppError({
        title: msg,
        details: text,
        componentName: functionName,
        originalError: error,
    });
}
//# sourceMappingURL=unhandled-errors-handlers.js.map