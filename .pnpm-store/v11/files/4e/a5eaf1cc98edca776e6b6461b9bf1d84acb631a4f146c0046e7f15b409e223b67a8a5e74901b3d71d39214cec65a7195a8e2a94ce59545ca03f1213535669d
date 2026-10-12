import type { Plugin } from "vite";
import { registerRouteRequestLogHandler } from "./nitro-module.js";

type PluginWithNitroModule = Plugin & { nitro: typeof registerRouteRequestLogHandler };

export const routeRequestLogPlugin = (): PluginWithNitroModule => ({
  name: "base44-route-request-log",
  nitro: registerRouteRequestLogHandler,
});
