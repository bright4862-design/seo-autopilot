if (window.self !== window.top) {
    let lastUrl = window.location.href;
    function notifyNavigation() {
        const currentUrl = window.location.href;
        if (currentUrl !== lastUrl) {
            lastUrl = currentUrl;
            window.parent?.postMessage({
                type: "app_changed_url",
                url: currentUrl,
            }, "*");
        }
    }
    // Intercept history.pushState
    const originalPushState = history.pushState.bind(history);
    history.pushState = function (...args) {
        originalPushState(...args);
        notifyNavigation();
    };
    // Intercept history.replaceState
    const originalReplaceState = history.replaceState.bind(history);
    history.replaceState = function (...args) {
        originalReplaceState(...args);
        notifyNavigation();
    };
    // Handle browser back/forward navigation
    window.addEventListener("popstate", notifyNavigation);
    // Notify initial URL on load
    window.parent?.postMessage({
        type: "app_changed_url",
        url: window.location.href,
    }, "*");
}
export {};
//# sourceMappingURL=navigation-notifier.js.map