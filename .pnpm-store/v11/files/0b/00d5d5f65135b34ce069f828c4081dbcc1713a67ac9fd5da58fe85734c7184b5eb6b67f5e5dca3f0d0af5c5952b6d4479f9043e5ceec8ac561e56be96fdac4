/**
 * Vite 8's experimental full-bundle dev mode (`experimental.bundledDev`) serves
 * the client from an in-memory rolldown build. It mounts neither the transform
 * nor the static middlewares, so raw `/node_modules/...` and `/@vite/client`
 * URLs stop resolving, and build errors surface through the environment logger
 * instead of the websocket broadcast. Plugins that assume the middleware-based
 * dev server branch on this.
 */
export function isBundledDev(config) {
    const experimental = config
        ?.experimental;
    return Boolean(experimental?.bundledDev);
}
//# sourceMappingURL=bundled-dev.js.map