import type { AxiosInstance } from "axios";
/** Options for {@link Base44Client.fetchWithAuth}. */
export interface FetchWithAuthInit extends RequestInit {
    /**
     * The `fetch` that resolves a root-relative path against your app's own
     * routes. Defaults to the global `fetch`, which does that in a browser but
     * not on a server, where a path with no origin has nothing to resolve
     * against. In Nitro pass its own, which routes a leading-slash path
     * in-process: `import { fetch } from "nitro"`.
     */
    fetch?: (input: string, init?: RequestInit) => Promise<Response>;
}
/**
 * Builds the client's `fetchWithAuth`: a `fetch` to the app's own origin that
 * carries whatever credentials this client holds.
 *
 * That is the user's access token in a browser, and from
 * `createClientFromRequest()` the full set that function reads back — so a
 * route reached this way rebuilds the caller's client, service role included.
 * The service credential is minted per request for the app as a whole, not for
 * one route, so a handler in the same worker already runs with that authority;
 * reaching it through a route hop is the privilege it would have had by
 * importing a shared function. What must never happen is a credential leaving
 * the app, and the relative-path rule, not a shorter header list, is what
 * prevents that.
 *
 * @param axios - The user-scoped instance. Its `Authorization` default is the
 * live token: it follows `setToken()` and is deleted on `logout()`, so a
 * request never carries a token the user no longer has. From
 * `createClientFromRequest()` it holds the caller's own token.
 * @param serviceRoleAxios - The service-role instance, holding the app's
 * per-request credential as its own `Authorization` default. A browser client
 * has none, so nothing is sent.
 * @internal
 */
export declare function createFetchWithAuth({ axios, serviceRoleAxios, appId, serverUrl, functionsVersion, platformHeaders, }: {
    axios: AxiosInstance;
    serviceRoleAxios: AxiosInstance;
    appId: string;
    serverUrl: string;
    functionsVersion?: string;
    platformHeaders?: Record<string, string>;
}): (path: string, init?: FetchWithAuthInit) => Promise<Response>;
