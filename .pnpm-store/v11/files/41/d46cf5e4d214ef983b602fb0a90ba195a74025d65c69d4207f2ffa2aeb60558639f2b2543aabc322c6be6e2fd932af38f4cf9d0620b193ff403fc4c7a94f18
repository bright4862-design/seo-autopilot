if (window.self !== window.top) {
    const observer = new MutationObserver((mutations) => {
        const nodesAdded = mutations.some((mutation) => mutation.addedNodes.length > 0);
        const nodesRemoved = mutations.some((mutation) => mutation.removedNodes.length > 0);
        if (nodesAdded || nodesRemoved) {
            const foundElmWithDataAttribute = document.body.querySelectorAll("[data-source-location], [data-dynamic-content]").length > 0;
            if (foundElmWithDataAttribute) {
                window.parent?.postMessage({ type: "sandbox:onMounted" }, "*");
            }
            else {
                window.parent?.postMessage({ type: "sandbox:onUnmounted" }, "*");
            }
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
}
export {};
//# sourceMappingURL=sandbox-mount-observer.js.map