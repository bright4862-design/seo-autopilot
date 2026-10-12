import type { Connect, Logger, Plugin, ViteDevServer } from "vite";
import type { ServerResponse } from "http";
import { isBundledDev } from "./bundled-dev.js";

/**
 * Opt-in, loopback-gated dev-server endpoint that reports the last
 * build / compile / HMR error observed since the dev server started.
 *
 * `GET /__build_status` responds `200` with a JSON body:
 *   { ok: boolean, error: <scrubbed error> | null }
 *
 * The endpoint is:
 *   - dev-only (`apply: "serve"`) — it never exists in a production build;
 *   - loopback-only — requests from non-loopback addresses fall through.
 *
 * Enablement (the `BASE44_BUILD_STATUS_ENABLED` env-var check) is decided by
 * the caller in `index.ts`, which only adds this plugin to the array when the
 * endpoint is wanted — so `configureServer` here is never even reached when
 * the feature is off.
 *
 * The status is always reported in the body with HTTP `200`, even on error:
 * a `500` here would trip the preview proxy's own error path.
 *
 * Cold-start caveat (middleware dev server): errors thrown before any client
 * has connected are not sent over the HMR channel, so a boot-time transform
 * failure may briefly read `ok: true`. That window is covered server-side by
 * the existing dev_server_error_classifier. Under bundled dev the build hooks
 * and logger below observe boot failures too.
 */

const ENDPOINT = "/__build_status";

/** Max characters kept per scrubbed string field. */
const MAX_FIELD = 4000;
/** Max characters kept for the code frame. */
const MAX_FRAME = 2000;

type SendChannel = { send: (...args: unknown[]) => void };

const PATCHED = Symbol.for("base44.buildStatus.loggerPatched");
type PatchableLogger = Omit<Logger, "error"> & {
  error: Logger["error"] & { [PATCHED]?: boolean };
};

// Plugin hooks run once per environment in bundled dev; only the client's
// build is the preview. Older Vite has no `this.environment`.
function isClientEnvironment(ctx: unknown): boolean {
  const name = (ctx as { environment?: { name?: string } } | undefined)?.environment?.name;
  return name === undefined || name === "client";
}

const LOOPBACK_ADDRESSES = new Set([
  "127.0.0.1",
  "::1",
  "::ffff:127.0.0.1",
]);

function isLoopback(remoteAddress: string | undefined): boolean {
  return remoteAddress !== undefined && LOOPBACK_ADDRESSES.has(remoteAddress);
}

function clip(value: unknown, max: number): string | undefined {
  if (typeof value !== "string" || value.length === 0) return undefined;
  return value.length > max ? `${value.slice(0, max)}… [truncated]` : value;
}

/**
 * Strip absolute filesystem paths down to their basename so directory
 * structure never leaks. This is loopback-only, but the backend relays a
 * trimmed form, so scrub before it leaves this process.
 */
function stripPaths(value: string): string {
  return (
    value
      // Windows: C:\Users\foo\bar\file.ext -> file.ext
      .replace(/[A-Za-z]:\\[^\s:*?"<>|]+/g, (m) => m.split(/[\\/]/).pop() ?? m)
      // POSIX absolute: /Users/foo/bar/file.ext -> file.ext
      .replace(/\/(?:[^\s:/]+\/)+[^\s:/]+/g, (m) => m.split("/").pop() ?? m)
  );
}

function scrubString(value: unknown, max: number): string | undefined {
  const clipped = clip(value, max);
  return clipped === undefined ? undefined : stripPaths(clipped);
}

/**
 * Produce a trimmed, path-stripped, size-capped view of an HMR error
 * payload. Returns `null` when there is no error.
 */
export function scrub(err: unknown): Record<string, unknown> | null {
  if (err === null || err === undefined) return null;

  if (typeof err !== "object") {
    const message = scrubString(String(err), MAX_FIELD);
    return message === undefined ? null : { message };
  }

  const e = err as Record<string, unknown>;
  const out: Record<string, unknown> = {};

  const message = scrubString(e["message"], MAX_FIELD);
  if (message !== undefined) out["message"] = message;

  const stack = scrubString(e["stack"], MAX_FIELD);
  if (stack !== undefined) out["stack"] = stack;

  const frame = scrubString(e["frame"], MAX_FRAME);
  if (frame !== undefined) out["frame"] = frame;

  const id = scrubString(e["id"], MAX_FIELD);
  if (id !== undefined) out["id"] = id;

  const plugin = scrubString(e["plugin"], 200);
  if (plugin !== undefined) out["plugin"] = plugin;

  const loc = e["loc"];
  if (loc && typeof loc === "object") {
    const l = loc as Record<string, unknown>;
    out["loc"] = {
      file: scrubString(l["file"], MAX_FIELD),
      line: typeof l["line"] === "number" ? l["line"] : undefined,
      column: typeof l["column"] === "number" ? l["column"] : undefined,
    };
  }

  // Fall back to a stringified form if we recognised nothing useful.
  if (Object.keys(out).length === 0) {
    const message = scrubString(String(e), MAX_FIELD);
    return message === undefined ? {} : { message };
  }

  return out;
}

export function buildStatusPlugin(): Plugin {
  let lastError: unknown = null;
  let bundled = false;

  return {
    name: "base44-build-status",
    apply: "serve",
    configResolved(config) {
      bundled = isBundledDev(config);
    },
    // Bundled dev runs the rolldown build hooks on every rebuild of the client
    // environment; a build that reaches generateBundle superseded whatever error
    // was recorded before. Other environments' builds say nothing about the preview.
    buildEnd(error) {
      if (bundled && error && isClientEnvironment(this)) lastError = error;
    },
    generateBundle() {
      if (bundled && isClientEnvironment(this)) lastError = null;
    },
    configureServer(server: ViteDevServer) {
      if (bundled) {
        // Bundled dev reports build failures through the environment logger
        // (`{ error }` option) and per-client sends, never the broadcast
        // channel patched below. Any logged `{ error }` counts until the next
        // successful build: the fail-safe direction for a health endpoint.
        // Kept out of the endpoint's try so a logger surprise never unmounts it.
        try {
          const logger = server.environments.client.logger as PatchableLogger;
          if (!logger.error[PATCHED]) {
            const origError = logger.error.bind(logger);
            const patched: PatchableLogger["error"] = (msg, options) => {
              if (options?.error) lastError = options.error;
              return origError(msg, options);
            };
            patched[PATCHED] = true;
            logger.error = patched;
          }
        } catch {
          // Build failures then surface only via buildEnd; the endpoint still mounts.
        }
      }
      try {
        // Observe the HMR channel: an `error` payload records the last
        // error; a successful `update` / `full-reload` clears it. Left on in
        // bundled dev too: nothing is broadcast there, so it is inert.
        const ch = (server.hot ?? server.ws) as unknown as SendChannel | undefined;
        if (ch && typeof ch.send === "function") {
          const orig = ch.send.bind(ch);
          ch.send = (payload: unknown, ...rest: unknown[]) => {
            try {
              const p = payload as { type?: string; err?: unknown } | undefined;
              if (p?.type === "error") {
                lastError = p.err ?? null;
              } else if (p?.type === "update" || p?.type === "full-reload") {
                lastError = null;
              }
            } catch {
              // Never let bookkeeping break HMR delivery.
            }
            return orig(payload, ...rest);
          };
        }

        server.middlewares.use(
          ENDPOINT,
          (
            req: Connect.IncomingMessage,
            res: ServerResponse,
            next: Connect.NextFunction
          ) => {
            try {
              if (!isLoopback(req.socket?.remoteAddress)) {
                next();
                return;
              }
              if (req.method !== "GET") {
                next();
                return;
              }

              const body = JSON.stringify({
                ok: !lastError,
                error: scrub(lastError),
              });
              // Health lives in the body — keep 200 even on error so the
              // preview proxy doesn't treat this as a server failure.
              res.statusCode = 200;
              res.setHeader("Content-Type", "application/json");
              res.setHeader("Cache-Control", "no-store");
              res.end(body);
            } catch {
              // Fail open: a bug here must never break the dev server.
              try {
                next();
              } catch {
                // ignore
              }
            }
          }
        );
      } catch {
        // Fail open: setup errors must never break the dev server.
      }
    },
  };
}
