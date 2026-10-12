import type { ActorRef } from "./actors.types.js";
/** Credentials minted by the platform for one direct actor connection. */
export interface ActorConnectionCredentials {
    /** Direct actor endpoint, already carrying `?_pk=<connectionId>`. */
    websocket_url: string;
    /** Short-lived JWT bound to (app, actor, room, connectionId); appended to
     * the URL as `token=` since browsers can't set WebSocket headers. */
    token: string;
}
interface ActorsConfig {
    appId: string;
    /** Current user access token, if authenticated. Rides the WS query on the
     * proxy-fallback path so the platform proxy can authenticate the connection;
     * anonymous connects omit it. */
    getAuthToken(): string | null | undefined;
    /** Same semantics as function calls: editors with a non-prod version get the
     * draft actor script; everyone else gets the published one. */
    functionsVersion?: string;
    /** Absolute host for the proxy-fallback URL (scheme is swapped to wss, ws
     * for localhost). Resolved by {@link resolveActorsHost}. */
    host: string;
    /** Mints a direct-connect credential for one (actor, room, connection).
     * Called per connection attempt: the token's expiry is checked at upgrade,
     * so every reconnect needs a fresh one. */
    mintConnectionToken(actorName: string, room: string, connectionId: string): Promise<ActorConnectionCredentials>;
    /** @internal Ops escape hatch: "proxy" never mints (legacy path only),
     * "direct" never falls back. Default "auto". */
    transport?: "auto" | "proxy" | "direct";
    /** Called when a mint fails for a reason other than the expected
     * direct→proxy fallback (which recovers by itself). Wired to the client's
     * `options.onError`. */
    onMintError?: (error: Error) => void;
}
/**
 * The legacy platform-proxy URL, byte-for-byte what PartySocket built before
 * the direct path existed: same scheme swap (including its localhost-needs-a-
 * port quirk), case-preserved party segment, `_pk` first in the query. The
 * `handler` param is load-bearing — the proxy reads it for the actor name.
 */
export declare function buildProxyActorUrl(rawHost: string, actorName: string, instanceId: string, connectionId: string, appId: string, token: string | null | undefined, functionsVersion?: string): string;
/**
 * Absolute host for the proxy-fallback actor URL. A relative/empty `serverUrl`
 * can't be dialed (same-origin apps use a relative `/api`, so `serverUrl` is
 * often `""`), so fall back to the page origin.
 */
export declare function resolveActorsHost(serverUrl: string, browserOrigin?: string): string;
export declare function createActorsModule(config: ActorsConfig): {
    module: Record<string, (instanceId: string) => ActorRef>;
    closeAll: () => void;
};
export {};
