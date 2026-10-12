if (import.meta.hot) {
    import.meta.hot.on("vite:beforeUpdate", () => {
        window.parent?.postMessage({ type: "sandbox:beforeUpdate" }, "*");
    });
    import.meta.hot.on("vite:afterUpdate", () => {
        window.parent?.postMessage({ type: "sandbox:afterUpdate" }, "*");
    });
}
export {};
//# sourceMappingURL=sandbox-hmr-notifier.js.map