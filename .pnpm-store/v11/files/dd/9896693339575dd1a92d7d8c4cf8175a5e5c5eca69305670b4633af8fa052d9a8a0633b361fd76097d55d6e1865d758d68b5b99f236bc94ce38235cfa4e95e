import { fileURLToPath } from "node:url";

type RouteHandlerRegistration = { route: string; middleware?: boolean; handler: string };
export type NitroDevServer = { options: { dev: boolean; handlers: RouteHandlerRegistration[] } };

const ROUTE_REQUEST_LOG_HANDLER = fileURLToPath(
  new URL("./route-request-log-handler.js", import.meta.url)
);

export function registerRouteRequestLogHandler(nitro: NitroDevServer) {
  if (!nitro.options.dev) return;
  nitro.options.handlers.push({
    route: "/**",
    middleware: true,
    handler: ROUTE_REQUEST_LOG_HANDLER,
  });
}
