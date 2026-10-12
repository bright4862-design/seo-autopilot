export type PageHeightBridgeController = {
    freezeVhUnits: (override?: number) => void;
    measurePageHeight: (origin: string, settleMs?: number) => void;
    teardown: () => void;
};
/**
 * Installs the parent-driven message listener. Returns a teardown that
 * removes the listener, disconnects any observers attached as a result of
 * `freeze-vh-units`, and clears any pending response timer. Returns a
 * no-op when bailed (already started, SSR, top window).
 */
export declare function setupPageHeightBridge(): () => void;
export declare function createPageHeightBridgeController(): PageHeightBridgeController;
//# sourceMappingURL=page-height-bridge.d.ts.map