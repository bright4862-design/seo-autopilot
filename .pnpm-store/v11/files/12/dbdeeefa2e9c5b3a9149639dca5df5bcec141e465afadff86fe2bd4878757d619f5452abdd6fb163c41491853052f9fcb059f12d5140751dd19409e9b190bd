// A server-rendered page hydrates in place and never mutates the DOM, so the
// mount observer's MutationObserver never fires for it. The instrumented markup
// in the server's HTML is the mount, so it is reported as soon as the document
// is parsed — before hydration; a hydration error reaches the editor through the
// unhandled-error handlers. Streamed markup that lands later is caught by the
// `load` retry, or by the observer, which parser insertions do trigger.
export function reportSsrMount(win: Window = window, doc: Document = document): void {
  if (win.self === win.top) return;
  const report = (): boolean => {
    if (!doc.body.querySelector("[data-source-location], [data-dynamic-content]")) return false;
    win.parent?.postMessage({ type: "sandbox:onMounted" }, "*");
    return true;
  };
  const reportOrRetryOnLoad = () => {
    if (!report()) win.addEventListener("load", () => void report(), { once: true });
  };
  if (doc.readyState === "loading") {
    doc.addEventListener("DOMContentLoaded", reportOrRetryOnLoad, { once: true });
  } else {
    reportOrRetryOnLoad();
  }
}

if (typeof window !== "undefined") reportSsrMount();
