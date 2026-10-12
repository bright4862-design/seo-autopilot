import { WebSocket as ReconnectingWebSocket } from "partysocket";
// Heartbeat / half-open detection: the socket only reconnects on a close/error
// event, so ping periodically and force a reconnect if nothing returns in DEAD_MS.
const PING_MS = 1000;
const DEAD_MS = 3000;
// Mint responses that mean "direct can't serve this connection, the proxy can":
// 409 = legacy-family actor script, 503 = direct connections not provisioned,
// 422 = no principal (e.g. anonymous outside a browser) or an id/room only the
// proxy's looser validation accepts, 405 = a backend that predates the mint
// endpoint (its actor deploy routes catch the path via `{handler_name:path}`
// but not the POST method — and the real endpoint never 405s a POST). The
// proxy serves migrated actors too, so falling back is always safe.
const PROXY_FALLBACK_STATUSES = new Set([405, 409, 422, 503]);
// Mint responses no retry can fix (bad request / forbidden / not found): the
// connection closes instead of re-minting forever; a fresh connect() re-probes.
// 401 is deliberately absent — the auth token is re-read on every attempt, so a
// login recovers on the next retry. Disjoint from PROXY_FALLBACK_STATUSES.
const TERMINAL_MINT_STATUSES = new Set([400, 403, 404]);
/** The mint's rejection can be anything; a `Base44Error` carries a numeric
 * `.status` (absent for network failures). */
function mintErrorStatus(err) {
    const status = err && typeof err === "object"
        ? err.status
        : undefined;
    return typeof status === "number" ? status : undefined;
}
function toError(err) {
    return err instanceof Error ? err : new Error(String(err));
}
/**
 * A live connection to an actor instance. Only obtainable from
 * {@link ActorRef.connect}, so `subscribe`/`send` are always valid — the socket
 * exists for this object's whole lifetime.
 */
class Connection {
    constructor(actorName, instanceId, config, options, onClose) {
        var _a;
        this.onClose = onClose;
        this.listeners = new Set();
        this.heartbeat = null;
        this.closed = false;
        this.id = (_a = options === null || options === void 0 ? void 0 : options.id) !== null && _a !== void 0 ? _a : crypto.randomUUID();
        // Direct-first with proxy fallback, decided per connection attempt. Once a
        // mint answers with a fallback status the choice is sticky for this
        // socket's lifetime (a fresh connect() after close() probes direct again,
        // picking up actors migrated in the meantime). Any other mint failure
        // rejects, which ReconnectingWebSocket retries with backoff — except the
        // terminal statuses, which close this connection for good.
        let useProxy = config.transport === "proxy";
        const urlProvider = async () => {
            var _a;
            if (this.closed)
                throw new Error("Actor connection is closed");
            if (!useProxy) {
                try {
                    const { websocket_url, token } = await config.mintConnectionToken(actorName, instanceId, this.id);
                    const sep = websocket_url.includes("?") ? "&" : "?";
                    return `${websocket_url}${sep}token=${encodeURIComponent(token)}`;
                }
                catch (err) {
                    const status = mintErrorStatus(err);
                    const isFallback = config.transport !== "direct" &&
                        status !== undefined &&
                        PROXY_FALLBACK_STATUSES.has(status);
                    if (!isFallback) {
                        if (status !== undefined && TERMINAL_MINT_STATUSES.has(status)) {
                            // close() before notifying: ws.close() stops the redial the
                            // rethrow below would otherwise schedule, and a handler that
                            // immediately calls connect() gets a clean new connection.
                            this.close();
                        }
                        // Reported from here because the socket's error event only
                        // preserves `err.message`, never `.status`.
                        try {
                            (_a = config.onMintError) === null || _a === void 0 ? void 0 : _a.call(config, toError(err));
                        }
                        catch (_b) {
                            // an app handler must not break the dial loop or mask `err`
                        }
                        throw err;
                    }
                    useProxy = true;
                }
            }
            // Rebuilt per attempt so a login/logout is picked up on reconnect.
            return buildProxyActorUrl(config.host, actorName, instanceId, this.id, config.appId, config.getAuthToken(), config.functionsVersion);
        };
        const ws = new ReconnectingWebSocket(urlProvider);
        this.ws = ws;
        let lastMsg = Date.now();
        const bumpAlive = () => { lastMsg = Date.now(); };
        ws.addEventListener("open", bumpAlive);
        ws.addEventListener("message", (ev) => {
            bumpAlive();
            let data;
            try {
                data = JSON.parse(ev.data);
            }
            catch (_a) {
                return;
            }
            const msgType = data && typeof data === "object" ? data.type : undefined;
            if (msgType === "__pong")
                return;
            for (const listener of this.listeners)
                listener(data);
        });
        this.heartbeat = setInterval(() => {
            if (Date.now() - lastMsg > DEAD_MS) {
                bumpAlive(); // avoid a reconnect storm while the new socket comes up
                // Only kick a half-open socket (OPEN but silent). When it isn't open
                // the socket is already redialing with backoff, and reconnect() would
                // reset that backoff into a mint call every DEAD_MS.
                if (ws.readyState === ws.OPEN)
                    ws.reconnect();
                return;
            }
            try {
                // The deployed shim echoes __ping → __pong (base44-userapp-bundler
                // shim/actor.ts); without that, an idle room reconnects every DEAD_MS.
                ws.send(JSON.stringify({ type: "__ping" }));
            }
            catch (_a) {
                // not open; the watchdog above will reconnect
            }
        }, PING_MS);
    }
    subscribe(callback) {
        this.listeners.add(callback);
        return {
            unsubscribe: () => { this.listeners.delete(callback); },
        };
    }
    send(data) {
        // after close() the socket would buffer forever (unbounded enqueue)
        if (this.closed)
            return;
        this.ws.send(JSON.stringify(data));
    }
    close() {
        if (this.closed)
            return;
        this.closed = true;
        if (this.heartbeat) {
            clearInterval(this.heartbeat);
            this.heartbeat = null;
        }
        this.listeners.clear();
        this.ws.close();
        this.onClose();
    }
}
/** Handle for one actor instance: `connect()` opens the socket (idempotent). */
function makeActorRef(actorName, instanceId, config, connections) {
    let conn = null;
    return {
        connect(options) {
            if (conn)
                return conn;
            const c = new Connection(actorName, instanceId, config, options, () => {
                connections.delete(c);
                if (conn === c)
                    conn = null; // allow a fresh connect() after close
            });
            conn = c;
            connections.add(c);
            return c;
        },
    };
}
/**
 * The legacy platform-proxy URL, byte-for-byte what PartySocket built before
 * the direct path existed: same scheme swap (including its localhost-needs-a-
 * port quirk), case-preserved party segment, `_pk` first in the query. The
 * `handler` param is load-bearing — the proxy reads it for the actor name.
 */
export function buildProxyActorUrl(rawHost, actorName, instanceId, connectionId, appId, token, functionsVersion) {
    let host = rawHost.replace(/^(http|https|ws|wss):\/\//, "");
    if (host.endsWith("/"))
        host = host.slice(0, -1);
    const insecure = host.startsWith("localhost:") ||
        host.startsWith("127.0.0.1:") ||
        host.startsWith("192.168.") ||
        host.startsWith("10.") ||
        (host.startsWith("172.") &&
            host.split(".")[1] >= "16" &&
            host.split(".")[1] <= "31") ||
        host.startsWith("[::ffff:7f00:1]:");
    const query = new URLSearchParams([
        ["_pk", connectionId],
        ["app_id", appId],
        ["handler", actorName],
    ]);
    if (token)
        query.append("token", token);
    if (functionsVersion)
        query.append("fv", functionsVersion);
    return `${insecure ? "ws" : "wss"}://${host}/parties/${actorName}/${instanceId}?${query}`;
}
/**
 * Absolute host for the proxy-fallback actor URL. A relative/empty `serverUrl`
 * can't be dialed (same-origin apps use a relative `/api`, so `serverUrl` is
 * often `""`), so fall back to the page origin.
 */
export function resolveActorsHost(serverUrl, browserOrigin) {
    return serverUrl && !serverUrl.startsWith("/") ? serverUrl : browserOrigin !== null && browserOrigin !== void 0 ? browserOrigin : serverUrl;
}
export function createActorsModule(config) {
    // Live connections this client opened, so client.cleanup() can reclaim any the
    // app forgot to close() (each connection removes itself here on close).
    const connections = new Set();
    const module = new Proxy({}, {
        get(_, key) {
            // Symbols and `then` resolve to undefined (so the module isn't mistaken
            // for a thenable when awaited); any string key is an actor name.
            if (typeof key !== "string" || key === "then")
                return undefined;
            return (instanceId) => makeActorRef(key, instanceId, config, connections);
        },
    });
    return {
        module,
        closeAll: () => {
            for (const c of [...connections])
                c.close();
        },
    };
}
