import { fileURLToPath } from "node:url";
const ROUTE_REQUEST_LOG_HANDLER = fileURLToPath(new URL("./route-request-log-handler.js", import.meta.url));
export function registerRouteRequestLogHandler(nitro) {
    if (!nitro.options.dev)
        return;
    nitro.options.handlers.push({
        route: "/**",
        middleware: true,
        handler: ROUTE_REQUEST_LOG_HANDLER,
    });
}
//# sourceMappingURL=nitro-module.js.map